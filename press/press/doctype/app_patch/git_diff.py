# Copyright (c) 2026, Frappe and contributors
# For license information, please see license.txt

"""Build an app patch with git itself, so that images and other binary files are included.

A github.com `.patch` or `.diff` only says "Binary files differ" for a binary file,
and `git apply` cannot create the file from that.
"""

from __future__ import annotations

import base64
import re
import subprocess
import tempfile

COMMIT_HASH = re.compile(r"[0-9a-f]{40}")
TIMEOUT = 300


def compare_commits(patch_url: str) -> tuple[str, str] | None:
	"""Return (base, head) of a github.com compare URL that names two full commit hashes."""
	if "github.com/" not in patch_url or "/compare/" not in patch_url:
		return None
	reference = patch_url.split("/compare/")[-1].split("?")[0]
	reference = reference.removesuffix(".patch").removesuffix(".diff")
	base, _, head = reference.partition("...")
	if COMMIT_HASH.fullmatch(base) and COMMIT_HASH.fullmatch(head):
		return base, head
	return None


def binary_diff(repository_url: str, base: str, head: str, token: str | None = None) -> str:
	"""Fetch two commits without file contents, then diff them with binary files included."""
	with tempfile.TemporaryDirectory() as directory:
		git = GitRepository(directory, token)
		git.run("init", "--quiet")
		git.run("remote", "add", "origin", repository_url)
		# Blobs are fetched on demand, only for the files that the diff needs
		git.run("fetch", "--quiet", "--depth=1", "--filter=blob:none", "origin", base, head)
		return git.run("diff", "--binary", base, head)


class GitRepository:
	def __init__(self, directory: str, token: str | None):
		self.directory = directory
		self.options = []
		if token:
			# A header keeps the token out of the remote URL and out of git's error messages
			credentials = base64.b64encode(f"x-access-token:{token}".encode()).decode()
			self.options = ["-c", f"http.extraHeader=Authorization: Basic {credentials}"]

	def run(self, *arguments: str) -> str:
		command = ["git", *self.options, "-C", self.directory, *arguments]
		result = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT)
		if result.returncode != 0:
			raise GitDiffError(f"git {arguments[0]} failed: {result.stderr.strip()}")
		return result.stdout


class GitDiffError(Exception):
	pass
