#!/usr/bin/env python3
"""Build an App Patch file that applies on a bench whose Patch App job failed.

Works for any app. Diffs FROM..TO in a clone of the app's repository and leaves
out the files that the bench's asset build rewrote: the failed job output names
them, and the ones that look like build output are dropped. Names the file
<app>-<from7>-<to7>.patch, so that Press reads TO as the bench head next time.

    make_patch.py --repo /tmp/etpos --app etpos --from e518ede --to 2471497 --job-output job.txt
"""

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

# Found on past failures; the job output finds the rest.
KNOWN_GENERATED = {
	"etpos": ["etpos/public/pos-app/*", "etpos/www/*.html"],
}
BUILD_OUTPUT_EXTENSIONS = (".html", ".js", ".mjs", ".css", ".map", ".json")
HASHED_NAME = re.compile(r"[.-][A-Za-z0-9_-]{8,}\.(?:js|mjs|css|map)$")
FAILED_PATH = re.compile(r"^error: (?:patch failed: )?(.+?)(?::\d+)?(?:: (?:patch does not apply|already exists in working directory|does not exist in index|No such file or directory))?$")


def git(repo: Path, *args: str) -> str:
	return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def resolve(repo: Path, ref: str) -> str:
	return git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}").strip()


def split_files(diff: str) -> list[str]:
	return [part for part in re.split(r"(?m)^(?=diff --git )", diff) if part.startswith("diff --git ")]


def path_of(block: str) -> str:
	return block.split("\n", 1)[0].split(" b/", 1)[-1]


def failed_paths(job_output: str) -> set[str]:
	"""Paths that `git apply` named in the failed job output."""
	return {match.group(1) for line in job_output.splitlines() if (match := FAILED_PATH.match(line.strip()))}


def looks_generated(path: str) -> bool:
	"""A file a build writes: under public/ or www/ with a web extension, or with a hashed name."""
	in_build_folder = "/public/" in f"/{path}" or "/www/" in f"/{path}"
	return bool(HASHED_NAME.search(path)) or (in_build_folder and path.endswith(BUILD_OUTPUT_EXTENSIONS))


def excluded_patterns(app: str, job_output: str, extra: list[str]) -> list[str]:
	failed = failed_paths(job_output)
	source = sorted(path for path in failed if not looks_generated(path))
	if source:
		print("These failed in the job but look like source, so they stay in the patch.")
		print("If the job used the wrong FROM, that explains them; if not, the bench has local edits:")
		for path in source:
			print(f"  {path}")
	return KNOWN_GENERATED.get(app, []) + sorted(path for path in failed if looks_generated(path)) + extra


def is_excluded(path: str, patterns: list[str]) -> bool:
	return any(fnmatch.fnmatch(path, pattern) for pattern in patterns)


def check_applies(repo: Path, head: str, patch: Path) -> None:
	"""Apply the patch to a clean worktree at FROM, so a broken diff never reaches the bench."""
	worktree = Path(git(repo, "rev-parse", "--git-common-dir").strip()).resolve().parent / ".patch-check"
	git(repo, "worktree", "add", "--detach", "--force", str(worktree), head)
	try:
		subprocess.run(["git", "-C", str(worktree), "apply", "--check", str(patch.resolve())], check=True)
	finally:
		git(repo, "worktree", "remove", "--force", str(worktree))


def parse_arguments() -> argparse.Namespace:
	parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
	source = parser.add_mutually_exclusive_group(required=True)
	source.add_argument("--repo", type=Path, help="clone of the app's repository, with both commits")
	source.add_argument("--diff-file", type=Path, help="FROM...TO diff, e.g. from the GitHub compare API, when no clone")
	parser.add_argument("--app", required=True, help="app name in Press, used for the file name")
	parser.add_argument("--from", dest="head", required=True, help="commit the bench is on now")
	parser.add_argument("--to", dest="target", required=True, help="commit to patch the bench to")
	parser.add_argument("--job-output", type=Path, help="output of the failed Patch App job")
	parser.add_argument("--exclude", action="append", default=[], help="extra glob to leave out")
	parser.add_argument("--out-dir", type=Path, default=Path("."))
	return parser.parse_args()


def read_diff(arguments: argparse.Namespace) -> tuple[str, str, str]:
	"""The FROM..TO diff and both commits, from a clone or from a diff file."""
	if arguments.diff_file:
		return arguments.diff_file.read_text(), arguments.head, arguments.target
	head, target = resolve(arguments.repo, arguments.head), resolve(arguments.repo, arguments.target)
	return git(arguments.repo, "diff", "--binary", f"{head}..{target}"), head, target


def main() -> None:
	arguments = parse_arguments()
	diff, head, target = read_diff(arguments)
	job_output = arguments.job_output.read_text() if arguments.job_output else ""
	patterns = excluded_patterns(arguments.app, job_output, arguments.exclude)

	blocks = split_files(diff)
	kept = [block for block in blocks if not is_excluded(path_of(block), patterns)]
	if not kept:
		sys.exit(f"Nothing left to patch between {head[:7]} and {target[:7]}")

	output = arguments.out_dir / f"{arguments.app}-{head[:7]}-{target[:7]}.patch"
	output.write_text("".join(kept))
	if arguments.repo:
		check_applies(arguments.repo, head, output)
	else:
		print("No clone, so git apply --check did not run.")
	print(f"{output}: {len(kept)} of {len(blocks)} files. Left out:")
	for block in blocks:
		if block not in kept:
			print(f"  {path_of(block)}")


if __name__ == "__main__":
	main()
