# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import re
import typing
from typing import Any, TypedDict

import frappe
import requests
from frappe.model.document import Document

from press.agent import Agent
from press.api.client import dashboard_whitelist
from press.press.doctype.app_patch.git_diff import binary_diff, compare_commits
from press.utils.external_url import fetch_public_url

# What every unified diff has and a JSON metadata document, an HTML error page
# or a redirect body does not: a hunk header, under a header naming the file it
# applies to. `git diff --binary` carries neither, so it is matched on its own.
HUNK_HEADER = re.compile(r"^@@ -\d+(,\d+)? \+\d+(,\d+)? @@", re.MULTILINE)
FILE_HEADER = re.compile(r"^(diff --git |--- |\+\+\+ )", re.MULTILINE)
BINARY_PATCH = re.compile(r"^GIT binary patch$", re.MULTILINE)


class PatchConfig(TypedDict):
	patch: str | None
	filename: str
	patch_url: str
	build_assets: bool
	migrate_sites: bool
	patch_bench: str
	patch_all_benches: bool
	patch_latest_deploy: bool


class AgentPatchConfig(TypedDict):
	patch: str
	filename: str
	build_assets: bool
	revert: bool


if typing.TYPE_CHECKING:
	from press.press.doctype.agent_job.agent_job import AgentJob
	from press.press.doctype.app_source.app_source import AppSource


class AppPatch(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		app: DF.Link
		app_release: DF.Link
		bench: DF.Link
		build_assets: DF.Check
		filename: DF.Data
		group: DF.Link
		migrate_sites: DF.Check
		name: DF.Int | None
		patch: DF.Code
		status: DF.Literal["Not Applied", "In Process", "Failed", "Applied", "Archived"]
		team: DF.Link
		url: DF.Data | None
	# end: auto-generated types

	dashboard_fields = [  # noqa: RUF012
		"name",
		"app",
		"app_release",
		"patch",
		"filename",
		"bench",
		"group",
		"build_assets",
		"migrate_sites",
		"url",
		"status",
	]

	def validate(self):
		self.validate_bench()

	def validate_bench(self):
		if frappe.get_value("Bench", self.bench, "status") == "Active":
			return
		frappe.throw(f"Bench {self.bench} is not Active, patch cannot be applied")

	def before_insert(self):
		patches = frappe.get_all(
			"App Patch",
			fields=["name", "filename"],
			filters={"bench": self.bench, "patch": self.patch},
		)
		if not len(patches):
			return

		filename = patches[0].get("filename")
		frappe.throw(f"Patch already exists for {self.bench} by the filename {filename}")

	def after_insert(self):
		self.apply_patch()

	@dashboard_whitelist()
	def delete(self):
		super().delete()

	@dashboard_whitelist()
	def apply_patch(self):
		self.patch_app(revert=False)

	@dashboard_whitelist()
	def revert_patch(self):
		self.patch_app(revert=True)

	@frappe.whitelist()
	def delete_patch(self):
		if self.status != "Not Applied":
			frappe.throw(
				f"Cannot delete patch if status is not 'Not Applied'. Current status is '{self.status}'"
			)

		self.delete()

	def patch_app(self, revert: bool):
		server = frappe.db.get_value("Bench", self.bench, "server")
		data = dict(
			patch=self.patch,
			filename=self.filename,
			build_assets=self.build_assets,
			revert=revert,
		)
		Agent(server).patch_app(self, data)
		self.status = "In Process"
		self.save()

	@staticmethod
	def process_patch_app(agent_job: "AgentJob"):
		if not agent_job.reference_name:
			return
		request_data = json.loads(agent_job.request_data)
		app_patch = AppPatch("App Patch", agent_job.reference_name, for_update=True)

		revert = request_data.get("revert")
		if agent_job.status == "Failure" and revert:
			app_patch.status = "Applied"
		elif agent_job.status == "Failure" and not revert:
			app_patch.status = "Failed"
		elif agent_job.status == "Success" and revert:
			app_patch.status = "Not Applied"
		elif agent_job.status == "Success" and not revert:
			app_patch.status = "Applied"
		else:
			app_patch.status = "In Process"

		app_patch.save()
		if app_patch.status == "Applied" and not revert and app_patch.migrate_sites:
			frappe.enqueue_doc(app_patch.doctype, app_patch.name, "migrate_bench_sites", enqueue_after_commit=True)

	def migrate_bench_sites(self):
		"""Migrate the active sites of the patched bench, so the patch's DocType changes and patches reach them."""
		from press.press.doctype.bench.bench import Bench

		bench = Bench("Bench", self.bench)
		bench.migrate_sites([{"name": name} for name in bench.migratable_sites()])

	@frappe.whitelist()
	def revert_all_patches(self):
		# TODO: Agent job: git reset RELEASE_COMMIT --hard
		pass


def create_app_patch(
	release_group: str,
	app: str,
	team: str,
	patch_config: PatchConfig,
) -> list[Any | None]:
	app_source = frappe.get_doc("Release Group", release_group).get_app_source(app)
	patch = get_patch(patch_config, app_source)
	benches = get_benches(release_group, patch_config)
	patches = []

	for bench in benches:
		doc_dict = dict(
			doctype="App Patch",
			patch=patch,
			bench=bench,
			group=release_group,
			app=app,
			team=team,
			app_release=get_app_release(bench, app),
			url=patch_config.get("patch_url"),
			filename=patch_config.get("filename"),
			build_assets=patch_config.get("build_assets"),
			migrate_sites=patch_config.get("migrate_sites"),
		)

		app_patch: AppPatch = frappe.get_doc(doc_dict)
		app_patch.insert()
		patches.append(app_patch.name)

	return patches


def get_patch(patch_config: PatchConfig, app_source: "AppSource | None" = None) -> str:
	if patch := patch_config.get("patch"):
		validate_patch(patch)
		return patch

	patch_url = patch_config["patch_url"]
	if app_source and (commits := compare_commits(patch_url)):
		patch = binary_diff(app_source.repository_url, *commits, app_source.get_access_token())
		validate_patch(patch)
		return patch

	# Private GitHub repos reject anonymous downloads. The github.com web `.patch`
	# endpoint also ignores API tokens, so download through the authenticated
	# GitHub API instead when the source belongs to a private installation.
	if app_source and app_source.github_installation_id and "github.com/" in patch_url:
		patch = download_private_github_patch(patch_url, app_source)
	else:
		patch = fetch_public_url(github_compare_diff_url(patch_url))

	validate_patch(patch)
	return patch


def download_private_github_patch(patch_url: str, app_source: "AppSource") -> str:
	api_url = github_patch_api_url(patch_url, app_source)
	if not api_url:
		# Not a compare/commit URL we can translate; try the raw URL as-is.
		return fetch_public_url(patch_url)

	headers = {
		"Authorization": f"token {app_source.get_access_token()}",
		# One combined diff. A `.patch` is one diff per commit, and a commit from a branch
		# merged into the range fails on files that changed after the branch started.
		"Accept": "application/vnd.github.diff",
	}
	response = requests.get(api_url, headers=headers)
	response.raise_for_status()
	return response.text


def github_compare_diff_url(patch_url: str) -> str:
	"""Ask github.com for the combined `.diff` of a compare range instead of its `.patch` series."""
	if "github.com/" in patch_url and "/compare/" in patch_url and patch_url.endswith(".patch"):
		return patch_url.removesuffix(".patch") + ".diff"
	return patch_url


def validate_patch(patch: str):
	"""Refuse anything that is not a unified diff.

	This is not what makes fetching a URL safe — `fetch_public_url` is. It
	matters because that check resolves the host and then connects, and a name
	that answers differently in between still lands wherever it likes. Whatever
	comes back is stored in `patch`, which the dashboard reads back, so it is
	worth making the body parse as a diff before it gets that far.

	Read the text and nothing else. Handing it to `git apply --check` or
	`patch --dry-run` to find out would be running untrusted input to validate
	untrusted input.
	"""
	if BINARY_PATCH.search(patch):
		return

	if not (FILE_HEADER.search(patch) and HUNK_HEADER.search(patch)):
		frappe.throw(
			"This does not look like a patch. Expected a unified diff, "
			"with a file header and at least one @@ hunk.",
			frappe.ValidationError,
		)


def get_last_patch_head(release_group: str, app: str, bench: str | None = None) -> str | None:
	"""Return the head commit of the last applied patch for an app, on one bench if given."""
	filters = {"group": release_group, "app": app, "status": "Applied"}
	if bench:
		filters["bench"] = bench
	patches = frappe.get_all("App Patch", filters, ["url", "filename"], order_by="creation desc")
	# Skip a patch whose name gives no commit, rather than fall back to the deployed one
	for patch in patches:
		if head := parse_patch_head(patch.url or "") or parse_patch_head(patch.filename or ""):
			return head
	return None


# A file name that ends in a commit, e.g. "etpos-7cf1daf-e518ede.patch"
FILENAME_HEAD = re.compile(r"[-_]([0-9a-f]{7,40})\.(?:patch|diff)$")


def parse_patch_head(reference: str) -> str | None:
	"""Extract the head commit from a compare/commit patch url or filename."""
	reference = (reference or "").strip()
	if "/commit/" in reference:
		segment = reference.split("/commit/")[-1]
	elif "..." in reference:
		segment = reference.split("...")[-1]
	elif match := FILENAME_HEAD.search(reference):
		return match.group(1)
	else:
		return None

	# A commit hash has no dot or slash; drop any extension or trailing path.
	head = segment.split(".")[0].split("/")[0].strip()
	return head or None


def github_patch_api_url(patch_url: str, app_source: "AppSource") -> str | None:
	"""Translate a github.com compare/commit `.patch` URL into its GitHub API URL."""
	reference = patch_url.strip()
	for suffix in (".patch", ".diff"):
		if reference.endswith(suffix):
			reference = reference[: -len(suffix)]

	api_base = f"https://api.github.com/repos/{app_source.repository_owner}/{app_source.repository}"
	if "/compare/" in reference:
		return f"{api_base}/compare/{reference.split('/compare/')[-1]}"
	if "/commit/" in reference:
		return f"{api_base}/commits/{reference.split('/commit/')[-1]}"
	return None


def get_benches(release_group: str, patch_config: PatchConfig) -> list[str]:
	patch_all_benches = patch_config.get("patch_all_benches")
	patch_latest_deploy = patch_config.get("patch_latest_deploy")

	if not patch_all_benches and not patch_latest_deploy:
		return [patch_config["patch_bench"]]

	if patch_latest_deploy:
		latest_deploy_candidate = frappe.db.get_value(
			"Deploy Candidate",
			filters={"group": release_group},
			order_by="creation desc",
			pluck="name",
		)
		return frappe.get_all(
			"Bench",
			filters={"status": "Active", "group": release_group, "candidate": latest_deploy_candidate},
			pluck="name",
		)

	return frappe.get_all(
		"Bench",
		filters={"status": "Active", "group": release_group},
		pluck="name",
	)


def get_app_release(bench: str, app: str) -> str:
	return frappe.get_all(
		"Bench App",
		fields=["release"],
		filters={"parent": bench, "app": app},
		pluck="release",
	)[0]
