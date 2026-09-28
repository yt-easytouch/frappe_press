# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

import random

import frappe


def sync_setup_wizard_status():
	sites = frappe.get_all(
		"Site",
		{
			"status": "Active",
			"setup_wizard_complete": False,
			"is_standby": False,
			"domain": ("in", ("erpnext.com", "frappe.cloud", "frappehr.com", "frappedesk.com")),
		},
		pluck="name",
	)

	for site_name in random.sample(sites, k=min(20, len(sites))):
		site = frappe.get_doc("Site", site_name)
		try:
			site.is_setup_wizard_complete()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
