# Copyright (c) 2026, Frappe and Contributors
# See license.txt

import json
import unittest
from unittest.mock import MagicMock, patch

import frappe

from press.press.doctype.app_patch import app_patch
from press.press.doctype.app_patch.app_patch import AppPatch

PROCESS_PATCH_APP = AppPatch.process_patch_app


def finish_patch_job(status: str, migrate_sites: bool, revert: bool = False):
	"""Run the Patch App callback on a fake job and App Patch; return the patch and the enqueue mock."""
	patch_doc = MagicMock(doctype="App Patch", migrate_sites=migrate_sites)
	patch_doc.name = 7
	job = frappe._dict(reference_name=7, status=status, request_data=json.dumps({"revert": revert}))
	with patch.object(app_patch, "AppPatch", return_value=patch_doc), patch.object(frappe, "enqueue_doc") as enqueue:
		PROCESS_PATCH_APP(job)
	return patch_doc, enqueue


class TestMigrateSitesAfterPatch(unittest.TestCase):
	"""The "Migrate all sites after applying patch" box migrates the bench once the patch applies."""

	def test_an_applied_patch_with_the_box_ticked_queues_the_bench_migration(self):
		patch_doc, enqueue = finish_patch_job("Success", migrate_sites=True)
		self.assertEqual(patch_doc.status, "Applied")
		enqueue.assert_called_once_with("App Patch", 7, "migrate_bench_sites", enqueue_after_commit=True)

	def test_an_applied_patch_without_the_box_migrates_nothing(self):
		_, enqueue = finish_patch_job("Success", migrate_sites=False)
		enqueue.assert_not_called()

	def test_a_failed_patch_migrates_nothing(self):
		patch_doc, enqueue = finish_patch_job("Failure", migrate_sites=True)
		self.assertEqual(patch_doc.status, "Failed")
		enqueue.assert_not_called()

	def test_a_reverted_patch_migrates_nothing(self):
		patch_doc, enqueue = finish_patch_job("Success", migrate_sites=True, revert=True)
		self.assertEqual(patch_doc.status, "Not Applied")
		enqueue.assert_not_called()

	def test_the_migration_covers_the_sites_that_a_failed_update_does_not_block(self):
		bench = MagicMock()
		bench.migratable_sites.return_value = ["a.example.com", "b.example.com"]
		patch_doc = MagicMock(bench="bench-1")
		with patch("press.press.doctype.bench.bench.Bench", return_value=bench) as bench_class:
			AppPatch.migrate_bench_sites(patch_doc)
		bench_class.assert_called_once_with("Bench", "bench-1")
		bench.migrate_sites.assert_called_once_with([{"name": "a.example.com"}, {"name": "b.example.com"}])
