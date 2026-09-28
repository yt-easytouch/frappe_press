# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

from datetime import datetime

import frappe
from frappe.utils import add_days, add_to_date, get_datetime, getdate, now_datetime

from press.utils.user import is_desk_user

SIZE_FIELDS = ("database_size", "public_size", "private_size")


@frappe.whitelist()
def get_site_backups(period: str = "Today") -> list[dict]:
	"""One row per site with its backups in the period, for the Backup Monitor page."""
	if not is_desk_user():
		frappe.throw("Only Press administrators can open the Backup Monitor", frappe.PermissionError)

	start, end = get_period_range(period)
	backups = get_backups_by_site(start, end)
	return [site_backup_row(site, backups.get(site.name, [])) for site in get_sites()]


def get_period_range(period: str) -> tuple[datetime, datetime]:
	now = now_datetime()
	today = get_datetime(getdate(now))
	ranges = {
		"Today": (today, now),
		"Yesterday": (add_days(today, -1), today),
		"Last 24 Hours": (add_to_date(now, hours=-24), now),
		"Last 7 Days": (add_days(today, -6), now),
	}
	if period not in ranges:
		frappe.throw(f"Unknown period: {period}")
	return ranges[period]


def get_sites() -> list[dict]:
	return frappe.get_all(
		"Site",
		{"status": ("!=", "Archived")},
		["name", "host_name", "status", "server", "group"],
		order_by="name asc",
	)


def get_backups_by_site(start: datetime, end: datetime) -> dict[str, list[dict]]:
	backups = frappe.get_all(
		"Site Backup",
		{"creation": ("between", [start, end]), "physical": 0},
		["site", "status", "offsite", "creation", *SIZE_FIELDS],
		order_by="creation desc",
	)
	by_site = {}
	for backup in backups:
		by_site.setdefault(backup.site, []).append(backup)
	return by_site


def site_backup_row(site: dict, backups: list[dict]) -> dict:
	successful = [backup for backup in backups if backup.status == "Success"]
	latest_success = successful[0] if successful else None
	return {
		"site": site.name,
		"host_name": site.host_name or site.name,
		"site_status": site.status,
		"server": site.server,
		"group": site.group,
		"backup_status": backup_status(backups, successful),
		"backups": len(backups),
		"successful": len(successful),
		"last_backup_on": backups[0].creation if backups else None,
		"last_success_on": latest_success.creation if latest_success else None,
		"offsite": bool(latest_success and latest_success.offsite),
		"size": backup_size(latest_success) if latest_success else 0,
	}


def backup_status(backups: list[dict], successful: list[dict]) -> str:
	if successful:
		return "Backed Up"
	if not backups:
		return "Missing"
	if any(backup.status in ("Pending", "Running") for backup in backups):
		return "In Progress"
	return "Failed"


def backup_size(backup: dict) -> int:
	return sum(int(backup.get(field) or 0) for field in SIZE_FIELDS)
