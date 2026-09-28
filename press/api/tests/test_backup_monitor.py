# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_days, now_datetime

from press.api.backup_monitor import get_site_backups
from press.press.doctype.site.test_site import create_test_site
from press.press.doctype.site_backup.test_site_backup import create_test_site_backup
from press.press.doctype.team.test_team import create_test_team


class TestBackupMonitor(FrappeTestCase):
	def setUp(self):
		self.site = create_test_site(subdomain="breadshop")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()

	def row(self, period="Today"):
		return next(row for row in get_site_backups(period) if row["site"] == self.site.name)

	def test_site_with_a_successful_backup_today_is_backed_up(self):
		create_test_site_backup(self.site.name, status="Success")

		row = self.row()

		self.assertEqual(row["backup_status"], "Backed Up")
		self.assertEqual(row["successful"], 1)
		self.assertTrue(row["offsite"])

	def test_site_without_any_backup_today_is_missing(self):
		row = self.row()

		self.assertEqual(row["backup_status"], "Missing")
		self.assertIsNone(row["last_backup_on"])

	def test_site_with_only_failed_backups_today_is_failed(self):
		create_test_site_backup(self.site.name, status="Failure", offsite=False)

		self.assertEqual(self.row()["backup_status"], "Failed")

	def test_backup_from_yesterday_counts_for_yesterday_and_not_today(self):
		create_test_site_backup(self.site.name, creation=add_days(now_datetime(), -1), status="Success")

		self.assertEqual(self.row("Yesterday")["backup_status"], "Backed Up")
		self.assertEqual(self.row("Today")["backup_status"], "Missing")

	def test_archived_sites_are_not_listed(self):
		self.site.db_set("status", "Archived")

		sites = [row["site"] for row in get_site_backups()]

		self.assertNotIn(self.site.name, sites)

	def test_customer_without_desk_access_cannot_open_the_backup_monitor(self):
		frappe.set_user(create_test_team().user)

		with self.assertRaises(frappe.PermissionError) as context:
			get_site_backups()

		self.assertIn("Only Press administrators can open the Backup Monitor", str(context.exception))
