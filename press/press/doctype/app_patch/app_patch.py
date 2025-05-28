# Copyright (c) 2024, Frappe and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import typing
from typing import TypedDict

import frappe
import requests
from frappe.model.document import Document

from press.agent import Agent
from press.api.client import dashboard_whitelist


class PatchConfig(TypedDict):
	patch: str | None
	filename: str
	patch_url: str
	build_assets: bool
	patch_bench: str | None
	patch_all_benches: bool
	patch_latest_deploy: bool


class AgentPatchConfig(TypedDict):
	patch: str
	filename: str
	build_assets: bool
	revert: bool


if typing.TYPE_CHECKING:
	from press.press.doctype.agent_job.agent_job import AgentJob


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
		request_data = json.loads(agent_job.request_data)
		app_patch = frappe.get_doc("App Patch", agent_job.reference_name, for_update=True)

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

	@frappe.whitelist()
	def revert_all_patches(self):
		# TODO: Agent job: git reset RELEASE_COMMIT --hard
		pass


def create_app_patch(
	release_group: str,
	app: str,
	team: str,
	patch_config: PatchConfig,
) -> list[str]:
	patch,file_name = get_patch(app,team , patch_config)
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
			filename=file_name,
			build_assets=patch_config.get("build_assets"),
		)

		app_patch: AppPatch = frappe.get_doc(doc_dict)
		app_patch.insert()
		patches.append(app_patch.name)

	return patches

def get_patch(app, team, patch_config: PatchConfig) -> str:
    file_name = patch_config.get("filename")
    if patch_config.get("release"):
        
        # Get App Release details
        app_releases = frappe.db.get_all(
            "App Release",
            filters={"name": patch_config.get("release"), "team": team},
            fields=["hash", "source"],
            order_by="creation desc",
            limit=1
        )
        if not app_releases:
            frappe.throw("❌ App Release not found.")
        app_release = app_releases[0]
        
        file_name = f"{app_release['hash']}.patch"

        # Get GitHub access token from Team
        github_access_token = frappe.db.get_value(
            "Team",
            {"name": team},
            "github_access_token"
        )
        if not github_access_token:
            frappe.throw("❌ GitHub token not found for the team.")

        # Get repository info from App Source
        app_sources = frappe.db.get_all(
            "App Source",
            filters={"name": app_release["source"], "app": app},
            fields=["repository", "repository_owner"],
            limit=1
        )
        if not app_sources:
            frappe.throw("❌ App source not found.")
        app_source = app_sources[0]

        # Construct GitHub patch URL
        url = f"https://api.github.com/repos/{app_source['repository_owner']}/{app_source['repository']}/commits/{app_release['hash']}"
        headers = {
            "Authorization": f"token {github_access_token}",
            "Accept": "application/vnd.github.v3.patch",
        }

        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return response.text , file_name
        else:
            frappe.throw(f"❌ Git Failed with status {response.status_code}: {response.text}")

    else:
        # Use manual patch or patch_url
        if patch := patch_config.get("patch"):
            return patch , file_name

        patch_url = patch_config.get("patch_url")
        if not patch_url:
            frappe.throw("❌ No patch or patch URL provided.")

        response = requests.get(patch_url)
        if response.status_code == 200:
            return response.text , file_name
        else:
            frappe.throw(f"❌ Failed to fetch patch from URL: {response.status_code}")



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
