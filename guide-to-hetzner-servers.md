# Guide to Creating Hetzner Servers (Press / Frappe Cloud)

This guide documents the **complete, staged flow** for creating servers on a
Hetzner cluster in Press — every doctype involved, every stage, the console
bootstrap step, and how the UI buttons work afterwards.

It is written from a real setup on the `hel1-hetzner` cluster (Helsinki).

---

## 1. The big picture

Two parallel chains meet at **Bench**. For infrastructure we care about the
right-hand chain:

```
Cluster (Hetzner region + VPC + firewall + SSH key)
 └── Server Plan (catalog: instance_type + price, per cluster)
      └── Virtual Machine (the actual Hetzner VM)
           ├── Proxy Server   (series "n" — nginx entry point, SHARED by all)
           ├── Database Server (series "m" — MariaDB)
           └── Server          (series "f" — app server, runs gunicorn/redis)
```

Each server-create also spawns a **Press Job** ("Create Server") that runs the
Ansible setup on the new VM.

**Golden rule of cost:** ONE shared **Proxy Server** per cluster, shared by every
app/DB server. You do NOT create a proxy per customer.

---

## 2. Doctypes involved (and what each is for)

| Doctype | Role | Key fields |
|---|---|---|
| **Cluster** | A Hetzner region + its VPC, firewall, SSH key. Holds the API token. | `cloud_provider=Hetzner`, `region`, `vpc_id`, `subnet_cidr_block`, `ssh_key`, `security_group_id`, `proxy_security_group_id`, `hetzner_api_token` |
| **Server Plan** | Catalog entry: maps a Hetzner instance type to a price, scoped to a cluster. | `server_type`, `instance_type` (e.g. `cpx22`), `cluster`, `cloud_provider`, `platform`, `vcpu`, `memory`, `disk`, `price_usd`, `enabled`, `premium`, `legacy_plan` |
| **Virtual Machine** | The actual VM on Hetzner. `provision()` calls the Hetzner API. | `cloud_provider`, `cluster`, `machine_type`, `machine_image`, `series`, `status`, `instance_id`, `public_ip_address` |
| **Virtual Machine Image** | A snapshot of a set-up server, used to provision fast. **Optional but required by the desk buttons.** | `cloud_provider`, `series`, `status`, `image_id`, `virtual_machine` |
| **Proxy Server** | nginx entry point. Shared by all servers in the cluster. | `cluster`, `status`, `is_primary`, `exclude_from_auto_selection` |
| **Database Server** | MariaDB server. | `cluster`, `status`, `ram`, `plan` |
| **Server** | App server (gunicorn/redis). Links to a proxy + DB. | `cluster`, `status`, `proxy_server`, `database_server`, `plan` |
| **Press Job** | Orchestrates the async "Create Server" Ansible steps. `steps` is a JSON list. | `job_type`, `server`, `status`, `steps` |
| **Server Plan Type** | Optional grouping/pricing tier for plans. | — |

Series letters (from `Cluster.base_servers`): **`n`** = Proxy, **`m`** = Database,
**`f`** = App server.

---

## 3. Prerequisites (one-time per cluster)

Before ANY server can be created, the cluster must be fully provisioned. Verify
on `hel1-hetzner`:

- [x] `cloud_provider` = `Hetzner`, `status` = `Active`
- [x] `region` set (e.g. `hel1`)
- [x] `vpc_id` set (Hetzner network id, e.g. `12090024`)
- [x] `subnet_cidr_block` set (e.g. `10.3.0.0/16`)
- [x] `ssh_key` set and the SSH Key exists
- [x] `security_group_id` + `proxy_security_group_id` set (Hetzner firewalls)
- [x] `hetzner_api_token` set (read + write permissions)

If `vpc_id` is empty, the Hetzner provisioning didn't finish — re-save the
Cluster to re-run `after_insert` → `provision_on_hetzner()`.

---

## 4. Server Plans — CREATE THESE FIRST (no cost)

`create_server` matches a **Server Plan** by cluster + compute. Without plans,
nothing can be created.

> **CRITICAL — location availability.** A server type must be *in stock* in the
> datacenter. Pricing existing ≠ available. In **hel1** the cheap `cpx11`/`cpx31`
> line is NOT available — provisioning them throws
> `unsupported location for server type`. Only these SHARED types work in hel1:
> `cpx12`, `cpx22`, `cpx32`, `cpx42`, `cpx52`, `cpx62`.
>
> Always run **Check Machine Availability** (desk button on Cluster) or query the
> datacenter's `server_types.available` before choosing a type.

> **Shared vs Dedicated.** `ccx*` types are **Dedicated** (expensive, e.g.
> `ccx13` = €42.99/mo). `cpx*`/`cax*`/`cx*` are **Shared** (cheap). Use SHARED.

Lean shared plans for hel1 (already created in this setup):

| Plan name | server_type | instance_type | vCPU / RAM / Disk | ~€/mo |
|---|---|---|---|---|
| Hetzner Proxy hel1 | Proxy Server | `cpx12` | 1 / 2 / 40 | 11.49 |
| Hetzner DB hel1 | Database Server | `cpx22` | 2 / 4 / 80 | 19.49 |
| Hetzner App hel1 | Server | `cpx22` | 2 / 4 / 80 | 19.49 |

Server Plan uses **prompt naming** — you must set `doc.name` explicitly when
creating via script.

```python
import frappe
doc = frappe.get_doc({
    "doctype": "Server Plan",
    "title": "Hetzner App hel1",
    "server_type": "Server",            # or "Database Server" / "Proxy Server"
    "instance_type": "cpx22",           # must be AVAILABLE in the region
    "cluster": "hel1-hetzner",
    "cloud_provider": "Hetzner",
    "platform": "x86_64",
    "vcpu": 2, "memory": 4, "disk": 80,
    "price_usd": 20, "price_inr": 1800,
    "enabled": 1, "premium": 0, "legacy_plan": 0,
})
doc.name = "Hetzner App hel1"           # prompt-named doctype
doc.insert(ignore_permissions=True)
frappe.db.commit()
```

---

## 5. The staged creation flow

Order matters: **Proxy → Database → App**. The app server needs the proxy (and
optionally DB) linked on the cluster in-memory before it is created.

### Stage A — bootstrap the FIRST server via console (one time)

The first server on a fresh Hetzner cluster boots from Hetzner's **stock
`ubuntu-22.04` image** (no VM Image needed) — `get_latest_ubuntu_image()`. This
is why the bootstrap must be a console/script step, not the desk button.

```python
import frappe
frappe.set_user("Administrator")
TEAM = "cacogq3slc"                      # owning team (from your infra)
cluster = frappe.get_doc("Cluster", "hel1-hetzner")

# 1) Proxy (series n) — SHARED, one per cluster
proxy, _ = cluster.create_server(
    "Proxy Server", "POS Proxy 1",
    plan=frappe.get_doc("Server Plan", "Hetzner Proxy hel1"),
    team=TEAM, create_subscription=False,
)
frappe.db.commit()

# 2) Database (series m)
db, _ = cluster.create_server(
    "Database Server", "POS DB 1",
    plan=frappe.get_doc("Server Plan", "Hetzner DB hel1"),
    team=TEAM, create_subscription=False,
)
frappe.db.commit()

# 3) App (series f) — needs proxy + db linked on the cluster (in-memory)
cluster.proxy_server = proxy.name
cluster.database_server = db.name
app, _ = cluster.create_server(
    "Server", "POS App 1",
    plan=frappe.get_doc("Server Plan", "Hetzner App hel1"),
    team=TEAM, create_subscription=False,
)
frappe.db.commit()
```

Each call:
1. creates a **Virtual Machine** and calls the Hetzner API (real VM, real billing),
2. creates the **Server/Database Server/Proxy Server** record,
3. enqueues a **Press Job "Create Server"** that runs Ansible setup (~10–15 min).

> **The proxy needs `is_primary = 1`** for the dashboard button to find it later:
> ```python
> frappe.db.set_value("Proxy Server", proxy.name, "is_primary", 1)
> ```

### Stage B — the "Create Server" Press Job steps

The async job (`press/press/doctype/press_job/jobs/create_server.py`) runs, in
order: `Provision Server` → `Wait For Server To Start` →
`Wait For Server To Be Accessible` → volume/mount steps →
`Check Cloud Init Status` → `Update Agent` → (MariaDB steps for DB) → …

Watch it: **Press Job** list, or:
```python
frappe.db.get_value("Press Job", "<job_name>", "status")   # Running/Success/Failure
```

### Stage C — build a Virtual Machine Image (unlocks the desk buttons)

Once a server is Active, snapshot it into a **Virtual Machine Image**. After an
image exists for each series (`n`, `m`, `f`), the desk buttons work and future
servers provision in ~2 min instead of ~15.

- `create_proxy` requires an `n`-series image in the region.
- `create_servers` requires images for all series (`images_available >= 1`).

### Stage D — from now on, use the UI buttons

**Desk UI** (`/app/cluster/hel1-hetzner` → Actions):
- **Create Proxy**, **Create Servers**, **Add Images**, **Check Machine Availability**
- (These need the VM Images from Stage C.)

**Dashboard UI** (`NewServer.vue` → Servers → **Create New Server**):
- Needs: team `servers_enabled=1`, an **Active primary Proxy** in the cluster,
  and enabled plans. Does NOT need a VM Image.
- Calls `press.api.server.new({cluster, app_plan, db_plan, title})` → creates
  **App + DB** on Hetzner, sharing the existing proxy. One click.

---

## 6. Deleting / terminating a server

`Virtual Machine.terminate()` deletes the Hetzner server. For a fully clean
removal (VM + linked server record):

```python
import frappe
frappe.set_user("Administrator")
vm = frappe.get_doc("Virtual Machine", "<vm-name>")
if vm.instance_id:
    try:
        vm.disable_termination_protection()
    except Exception:
        pass
    vm.terminate()                       # deletes the Hetzner server
# series -> server doctype: n=Proxy Server, m=Database Server, f=Server
frappe.delete_doc("<Server Doctype>", "<vm-name>", force=True, ignore_permissions=True, delete_permanently=True)
frappe.delete_doc("Virtual Machine", "<vm-name>", force=True, ignore_permissions=True, delete_permanently=True)
frappe.db.commit()
```

Verify nothing is left on Hetzner (and nothing is billing):
```python
client = frappe.get_doc("Cluster", "hel1-hetzner").get_hetzner_client()
print([(s.id, s.name, s.server_type.name) for s in client.servers.get_all()])
```

A VM in `Draft` status with no `instance_id` was never created on Hetzner — just
delete the records (no Hetzner call, no billing).

---

## 7. Troubleshooting (lessons learned)

| Symptom | Cause | Fix |
|---|---|---|
| `unsupported location for server type` | Instance type not in stock in the region (e.g. `cpx11` in hel1) | Use an AVAILABLE type: `cpx12/22/32…`. Check `datacenter.server_types.available`. |
| Bill higher than expected (`€42.99`) | Used a **Dedicated** `ccx*` type | Switch to a **Shared** `cpx*` type. |
| Dashboard "Create New Server" shows nothing / errors | No Active **primary** proxy, or team `servers_enabled=0`, or no enabled plans | Provision a proxy, set `is_primary=1`, enable the feature, create plans. |
| Desk **Create Proxy/Servers** buttons throw "Image not available" | No **Virtual Machine Image** in the region | Build a VM Image (Stage C) first. |
| `Create Server` job fails at "Provision Server" in ~1s, VM stuck in `Draft` | Hetzner API rejected the create (bad type/location) | Check the type availability; re-provision. |
| Server Plan insert: "Please set the document name" | Server Plan is **prompt-named** | Set `doc.name` before `insert()`. |
| App server create throws "Please set the Proxy Server to Cluster record" | `cluster.proxy_server` not set in-memory | Set `cluster.proxy_server = <proxy>` before creating the app server. |

---

## 8. Quick reference — this cluster's facts

- Cluster: **`hel1-hetzner`** (Hetzner, region `hel1`, public, Active)
- VPC: `12090024`, subnet `10.3.0.0/16`, SSH key `Acs macPC`
- Firewalls: server `10788622`, proxy `10788623`
- Owning team: **`cacogq3slc`**
- Available SHARED types in hel1: `cpx12, cpx22, cpx32, cpx42, cpx52, cpx62`
- Plans created: `Hetzner Proxy hel1` (cpx12), `Hetzner DB hel1` (cpx22), `Hetzner App hel1` (cpx22)
- Series: `n`=Proxy, `m`=Database, `f`=App
</content>
