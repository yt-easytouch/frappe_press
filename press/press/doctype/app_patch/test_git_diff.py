# Copyright (c) 2026, Frappe and Contributors
# See license.txt

import os
import subprocess
import tempfile
import unittest

from press.press.doctype.app_patch.git_diff import GitDiffError, binary_diff, compare_commits

PNG = bytes(range(256)) * 4


def git(directory: str, *arguments: str) -> str:
	return subprocess.run(
		["git", "-C", directory, *arguments], capture_output=True, text=True, check=True
	).stdout.strip()


class TestBinaryDiff(unittest.TestCase):
	"""A patch built from a github.com link has no bytes for images, so Press diffs with git."""

	def setUp(self):
		self.directory = tempfile.TemporaryDirectory()
		self.source = os.path.join(self.directory.name, "source")
		os.makedirs(self.source)
		git(self.source, "init", "--quiet")
		# GitHub allows both; a local repository needs them switched on
		git(self.source, "config", "uploadpack.allowFilter", "true")
		git(self.source, "config", "uploadpack.allowAnySHA1InWant", "true")
		self.base = self.commit({"hooks.py": "app_name = 'shop'\n"})
		self.head = self.commit({"hooks.py": "app_name = 'shop'\nversion = 2\n", "logo.png": PNG})

	def tearDown(self):
		self.directory.cleanup()

	def commit(self, files: dict) -> str:
		for name, content in files.items():
			mode = "wb" if isinstance(content, bytes) else "w"
			with open(os.path.join(self.source, name), mode) as f:
				f.write(content)
		git(self.source, "add", ".")
		git(self.source, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "--quiet", "-m", "c")
		return git(self.source, "rev-parse", "HEAD")

	def test_the_patch_carries_the_image_bytes_and_applies_on_the_base_commit(self):
		patch = binary_diff(f"file://{self.source}", self.base, self.head)
		self.assertIn("GIT binary patch", patch)

		bench = os.path.join(self.directory.name, "bench")
		git(self.directory.name, "clone", "--quiet", self.source, bench)
		git(bench, "checkout", "--quiet", self.base)
		subprocess.run(["git", "-C", bench, "apply", "-"], input=patch, text=True, check=True)

		with open(os.path.join(bench, "logo.png"), "rb") as f:
			self.assertEqual(f.read(), PNG)

	def test_a_commit_missing_from_the_repository_fails_with_git_s_message(self):
		with self.assertRaisesRegex(GitDiffError, "git fetch failed"):
			binary_diff(f"file://{self.source}", self.base, "f" * 40)


class TestCompareCommits(unittest.TestCase):
	def test_a_compare_url_with_two_full_hashes_gives_both_commits(self):
		base, head = "a" * 40, "b" * 40
		url = f"https://github.com/acme/shop/compare/{base}...{head}.patch"
		self.assertEqual(compare_commits(url), (base, head))

	def test_branch_names_and_commit_urls_are_not_compared_with_git(self):
		self.assertIsNone(compare_commits("https://github.com/acme/shop/compare/develop...main.patch"))
		self.assertIsNone(compare_commits(f"https://github.com/acme/shop/commit/{'a' * 40}.patch"))
