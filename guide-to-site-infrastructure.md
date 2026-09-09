# Guide to Press site infrastructure

How a site's three backing servers — **proxy**, **app**, **db** — are created, wired together, and how traffic gets routed to a site. Also covers whether/how load balancing exists today.

## The three server types, grouped by Cluster

A `Cluster` (`press/press/doctype/cluster/cluster.py`) is a region/network unit per cloud provider — it owns the VPC, subnet, security groups and SSH key for that region (`cluster.py:80-129`). On `after_insert` it provisions the network/firewalls for the chosen provider (AWS/OCI/Hetzner/DigitalOcean/Frappe Compute) (`cluster.py:263-273`).

`Cluster.base_servers` (`cluster.py:134-138`) defines the default trio to create per cluster:

```python
base_servers = {"Proxy Server": "n", "Database Server": "m", "Server": "f"}
```

`create_servers()` (`cluster.py:1475-1503`) loops over this and calls `create_server()` for each. `create_server()` (`cluster.py:2113-2253`) is the factory used for all three types:

1. Picks a plan.
2. Calls `self.create_vm(...)` (`cluster.py:2171-2185`) to create a `Virtual Machine` — the raw cloud instance abstraction (`press/press/doctype/virtual_machine/virtual_machine.py`), which dispatches to the right provider's API via `provision()` (`virtual_machine.py:514-526`).
3. Calls the matching factory on the VM — `vm.create_database_server()` (`virtual_machine.py:2547-2582`), `vm.create_server()` (`virtual_machine.py:2519-2544`), or `vm.create_proxy_server()` (`virtual_machine.py:2587-2607`) — each of which builds the corresponding doctype record with `virtual_machine: self.name` and `cluster: self.cluster`.
4. For an app `Server`, wires `server.database_server` and `server.proxy_server` (`cluster.py:2211-2220`) — this **throws if the cluster doesn't already have a proxy server**, since every app server must be paired to one.
5. Saves, creates a billing subscription, and kicks off a `Create Server` Press Job (`cluster.py:2251`).

So each server type maps to one doctype:

| # | Server type | Doctype | Runs |
|---|---|---|---|
| 1 | Proxy | `Proxy Server` (`press/press/doctype/proxy_server/`) | nginx, ProxySQL, wireguard/SSH-proxy |
| 2 | App | `Server` (`press/press/doctype/server/`) | gunicorn/bench workers |
| 3 | DB | `Database Server` (`press/press/doctype/database_server/`) | MariaDB |

Each references its `Virtual Machine`; the app `Server` additionally links `proxy_server` and `database_server`.

## Site creation → which app server it lands on

1. `Site._get_benches_for_()` (`site.py:3050-3067`) filters available benches by proxy servers valid for the site's cluster/plan.
2. `self.server = benches[0].server` (`site.py:3180`) — the app server the new site will run on is picked here.
3. `Site.create_agent_request()` (`site.py:1155-1177`):
   - `Agent(self.server).new_site(self)` (`agent.py:141`) — creates the site on the chosen app server.
   - `Agent(server.proxy_server, server_type="Proxy Server").new_upstream_file(server=self.server, site=self.name)` (`site.py:1174-1177`) — registers the domain → backend mapping in nginx on the proxy.
4. `create_dns_record()` (`press/utils/dns.py:32-66`) points the site's subdomain (CNAME/A) at the proxy server that will terminate its traffic.

## How proxy routing actually works (not a load-balanced pool)

The `Proxy Server`'s nginx does route by domain, but each site is a **static 1:1 mapping to one specific app server**, not a load-balanced pool of app servers:

- `Agent.new_upstream_file()` (`agent.py:690-702`) creates an nginx server-block keyed by the site's domain, pointing at one backend app server's private IP.
- `Server.add_upstream_to_proxy()` (`server.py:3390-3392`) registers a new app server ("upstream") with the proxy the first time it's created.
- `Agent.add_domain_to_upstream()` / `rename_upstream_site()` / `remove_upstream_file()` manage additional domains, renames, and teardown.

In this codebase, "upstream" means *one app server*, not an nginx `upstream {}` load-balanced pool. A given site's traffic always goes to the one app server (bench) it was deployed on — nginx's job is routing by `server_name`, not spreading load across app servers. (The one place a literal nginx `upstream {}` block shows up is TCP-streaming failover config — `press/playbooks/roles/nginx_conf_changes_for_tcp_streaming/tasks/main.yml:17-20` — unrelated to app request load balancing.)

## Is there a load balancer today?

**No dedicated load-balancer tier exists.** What Press has instead:

- **Multiple Proxy Servers per cluster are supported**, but each one is a *separate, independently addressable* endpoint, not a pooled/balanced tier. `create_dns_record()` (`dns.py:46-60`) checks how many active Proxy Servers exist in the cluster and, if more than one, gives the site's own DNS record pointing at whichever specific proxy server it was assigned to (falling back to `Root Domain.default_proxy_server` when there's only one). So scaling proxy capacity today means **adding more Proxy Servers and splitting sites across them by DNS**, not putting one load balancer in front of many.
- **Active/standby failover, not load distribution.** `Proxy Server` has `is_primary`/`primary` fields, and `trigger_failover()` (`proxy_server.py:325-396`) shifts a proxy's DNS to a secondary if the primary goes down. This is for availability, not for spreading concurrent load.
- **Database Server** has the analogous concept — `is_primary`/`primary` with `setup_db_replication` (`cluster.py:2144-2158, 2195-2197`) — again replication/failover, not query load balancing.

### If you need a load balancer in front of proxy servers

There's no existing doctype or hook for this — it would be new work, not a config flag. The realistic options:

1. **Cloud provider LB in front of N Proxy Servers** (e.g. Hetzner Load Balancer, AWS ALB) — terminates TLS or passes through to nginx on each Proxy Server, health-checks them, and load-balances at L4/L7. This is the standard way to horizontally scale the proxy tier without touching Press's routing model — Press still assigns each *site* to one Proxy Server (as it does today) or you'd need to also make nginx's per-site upstream mapping load-balance across multiple app servers, since right now one site == one app server anyway.
2. **DNS round-robin / weighted routing across multiple Proxy Servers**, reusing the existing `default_proxy_server` / per-site DNS record mechanism but letting `create_dns_record()` pick a proxy based on load instead of the current simple "any active proxy" logic (`dns.py:46-60`).

Either approach only helps you scale *how many sites* the proxy tier can serve — it doesn't change the fact that a single site's traffic today is pinned to one app server. Making a single site's own traffic load-balance across multiple app servers would require reworking `new_upstream_file()` to emit an nginx `upstream {}` block with multiple backends and changing how benches are assigned to sites — a bigger change than adding an LB in front of the proxy tier.
