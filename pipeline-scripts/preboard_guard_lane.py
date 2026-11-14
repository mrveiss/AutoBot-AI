#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane's one definition of what it runs and what it tests (#21359).

``.github/workflows/dispatch-preboard-guards.yml`` is dispatched on a member PR's head before
it boards a merge train (#18499, AC4). The workflow holds no test root, no count and no
verdict logic: it asks this module (and ``preboard_guard_lane_report`` for the verdict).

* ``roots``     -- the test roots the lane runs. :data:`GUARD_ROOTS` is the only place they are
  written, and each must also be a ``testpaths`` entry of ``pytest.ini``: a root the suite
  stopped collecting fails the lane instead of being run on its own. :data:`PRODUCT_ROOTS`
  are the roots it leaves to the suite; together the two must name every ``testpaths`` entry.
* ``resolve``   -- the tip of the base branch, resolved ONCE per run by the first job; every other job
  merges that exact commit, so no two jobs of one run can test different bases.
* ``merge``     -- the member head merged with the pinned base commit, as a local commit
  that is never pushed: the state a pull request's merge ref gives the suite.
* ``durations`` -- ``.test_durations`` restricted to the roots, so the shard plugin balances the
  lane's own tests instead of the whole suite's.
* ``meta``      -- what one shard records: its exit code, the merge state, the floor and the
  recorded test files it was expected to cover, derived from the tree it tested.
* ``types-meta`` -- what the types job records: the merge state and the base commit it tested.
* ``changed-tests`` -- the test files the head adds or changes (#21509), split by who runs them: the
  guard shards already run the guard roots in full; the ``own-tests`` job runs the rest, so a member's
  own new tests execute before the train instead of first inside it.
* ``added-headers`` -- the files the head ADDS (or renames or copies into place) in the license-header check's
  scope, judged on the committed text at the dispatched head: one without the header fails the lane (#21535).
  The check is the shared ``lacks_header`` of ``tools/lint/check_spdx_header.py``, which the train content gate
  also calls, so what a train rejects after boarding the lane rejects before it.
* ``summarize`` -- the machine-readable result and its job summary.
"""

from __future__ import annotations

import argparse
import configparser
import fnmatch
import json
import math
import os
import re
import subprocess  # nosec B404  # git, argv list, no shell
import sys
from pathlib import Path
from typing import Any, Callable

# The repository root (autobot_shared, tools) and this directory (the report module, not a package).
for _entry in (str(Path(__file__).resolve().parent.parent), str(Path(__file__).resolve().parent)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import preboard_guard_lane_report as report  # noqa: E402

from autobot_shared.paths import scrubbed_git_env  # noqa: E402
from tools.lint._comment_syntax import code_lines  # noqa: E402
from tools.lint.check_spdx_header import lacks_header  # noqa: E402

#: The guard and tooling trees, as named in pytest.ini's ``testpaths``. The only copy of this list.
GUARD_ROOTS = (
    "repo_tests",
    "pipeline-scripts",
    "tools",
    "autobot_shared",
    "scripts",
    "autobot-infrastructure/shared/scripts/hooks",
    "autobot-infrastructure/shared/scripts/monitoring",
    ".claude/skills/claims-audit",
    "autobot-infrastructure/shared/tests",
)

#: The roots left to the suite: product test trees, which are not guards. The two backends run in
#: their own interpreters and cost most of the rest of the suite; the others are product packages.
PRODUCT_ROOTS = (
    "autobot-backend",
    "autobot-slm-backend",
    "autobot-tts-worker",
    "libs",
    "plugins/core-plugins",
)

#: The product root that runs under the SLM interpreter, and the product roots that run in the backend one.
SLM_ROOT = "autobot-slm-backend"
OWN_TEST_ROOTS = tuple(r for r in PRODUCT_ROOTS if r != SLM_ROOT)

#: Prefixes pytest.ini's ``addopts --ignore`` leaves uncollected: a test file there never runs.
IGNORED_PREFIXES = ("autobot-slm-backend/ansible/", "autobot-npu-worker/resources/")

#: Where a changed test file runs. ``guarded`` files belong to the guard shards, which run their roots in full.
OWN_GROUPS = ("main", "slm", "guarded", "uncollected")

#: ``--diff-filter`` letters: every file a head changes (test selection), and the files it brings in under a path.
CHANGED_FILTER = "ACMR"
ARRIVED_FILTER = "ACR"

#: The suite's own record of the tests it runs, one node id per entry.
DURATIONS_FILE = ".test_durations"

#: Share of the recorded lane tests the lane must still EXECUTE. The record is regenerated
#: periodically, so the tree can drift from it; the ratio only has to separate "drifted" from
#: "ran the wrong thing or nothing".
FLOOR_RATIO = 0.9

#: The branch names the ``base`` input may carry.
BASE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

#: A full commit id: what the first job pins and every other job is handed.
BASE_SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")

#: Identity of the local merge commit. It is never pushed; git only needs a name on it.
MERGE_IDENTITY = ("-c", "user.name=preboard-lane", "-c", "user.email=preboard-lane@users.noreply.invalid")


def testpaths(root: Path) -> list[str]:
    """The entries of pytest.ini's ``testpaths``, comments removed."""
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(root / "pytest.ini", encoding="utf-8")
    if not parser.has_option("pytest", "testpaths"):
        raise SystemExit("pytest.ini declares no testpaths; the lane cannot tell what the suite collects")
    return [cl.text.strip() for cl in code_lines(parser.get("pytest", "testpaths")) if cl.text.strip()]


def guard_roots(root: Path) -> list[str]:
    """:data:`GUARD_ROOTS`, each proven to be a suite root that exists."""
    declared = set(testpaths(root))
    problems = [r for r in GUARD_ROOTS if r not in declared or not (root / r).is_dir()]
    if problems:
        raise SystemExit(f"guard roots {problems} are not collected by pytest.ini testpaths or do not exist")
    return list(GUARD_ROOTS)


def _record(root: Path) -> dict[str, float]:
    return json.loads((root / DURATIONS_FILE).read_text(encoding="utf-8"))


def lane_durations(root: Path, roots: list[str]) -> dict[str, float]:
    """The part of ``.test_durations`` that sits under *roots*."""
    prefixes = tuple(f"{r}/" for r in roots)
    return {node: seconds for node, seconds in _record(root).items() if node.startswith(prefixes)}


def required_files(root: Path, roots: list[str]) -> list[str]:
    """Recorded test files under *roots* that exist in the tested tree: each must produce a test."""
    files = {node.split("::", 1)[0] for node in lane_durations(root, roots)}
    return sorted(f for f in files if (root / f).is_file())


def floor_for(root: Path, ratio: float = FLOOR_RATIO) -> int:
    """The executed-test floor. Refuses when the record says nothing about the roots."""
    recorded = len(lane_durations(root, guard_roots(root)))
    if recorded < 1:
        raise SystemExit(f"{DURATIONS_FILE} records no test under {list(GUARD_ROOTS)}; no floor can be derived")
    return max(1, math.floor(recorded * ratio))


def _run_git(*args: str) -> subprocess.CompletedProcess:
    argv, env = ["git", *args], scrubbed_git_env()
    return subprocess.run(argv, capture_output=True, text=True, timeout=300, env=env)  # nosec B603 B607


def _git(*args: str) -> str:
    done = _run_git(*args)
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def resolve_base_sha(base_ref: str) -> str:
    """Fetch *base_ref* and name its tip. Run once per lane run; every job then uses this commit."""
    if not BASE_REF_PATTERN.fullmatch(base_ref) or ".." in base_ref:
        raise SystemExit(f"base {base_ref!r} is not a plain branch name")
    _git("fetch", "--no-tags", "origin", f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}")
    return _git("rev-parse", f"refs/remotes/origin/{base_ref}")


def pinned_base_commit(base_sha: str) -> dict[str, str]:
    """Fetch the pinned commit itself (never the branch tip); name it and how many commits the head lacks."""
    if not BASE_SHA_PATTERN.fullmatch(base_sha):
        raise SystemExit(f"pinned base {base_sha!r} is not a full commit id; the first job did not resolve one")
    done = _run_git("fetch", "--no-tags", "origin", base_sha)
    if done.returncode != 0:
        raise SystemExit(f"pinned base {base_sha} cannot be fetched: {done.stderr.strip()}")
    if _git("rev-parse", "--verify", f"{base_sha}^{{commit}}") != base_sha:
        raise SystemExit(f"fetched commit is not the pinned base {base_sha}")
    return {"base_sha": base_sha, "behind_base": _git("rev-list", "--count", f"HEAD..{base_sha}")}


def _merge_or_conflict(tip: str) -> bool:
    """Merge *tip* into HEAD as a local commit. ``False`` only for a content conflict."""
    done = _run_git(*MERGE_IDENTITY, "merge", "--no-ff", "--no-edit", tip)
    if done.returncode == 0:
        return True
    conflicted = _run_git("diff", "--name-only", "--diff-filter=U").stdout.strip()
    _run_git("merge", "--abort")
    if not conflicted:
        raise SystemExit(f"git merge of {tip} failed without a conflict: {done.stderr.strip() or done.stdout.strip()}")
    return False


def merge_base_into_head(base_sha: str) -> dict[str, str]:
    """The head merged with the pinned base: ``base_sha``, ``behind_base`` and ``merged`` (true | false)."""
    info = pinned_base_commit(base_sha)
    merged = _merge_or_conflict(info["base_sha"])
    return {**info, "merged": "true" if merged else "false"}


def python_file_patterns(root: Path) -> list[str]:
    """The file-name patterns pytest.ini collects (``python_files``)."""
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(root / "pytest.ini", encoding="utf-8")
    patterns = parser.get("pytest", "python_files", fallback="").split()
    if not patterns:
        raise SystemExit("pytest.ini declares no python_files; the lane cannot tell which files are tests")
    return patterns


def _under(path: str, roots: tuple[str, ...]) -> bool:
    return any(path.startswith(f"{r}/") for r in roots)


def group_of(path: str, patterns: list[str]) -> str | None:
    """Where the test file *path* runs (one of :data:`OWN_GROUPS`), or ``None`` for a file that is no test."""
    if not path.endswith(".py") or not any(fnmatch.fnmatchcase(path.rsplit("/", 1)[-1], p) for p in patterns):
        return None
    if path.startswith(IGNORED_PREFIXES):
        return "uncollected"
    if _under(path, GUARD_ROOTS):
        return "guarded"
    if path.startswith(f"{SLM_ROOT}/"):
        return "slm"
    return "main" if _under(path, OWN_TEST_ROOTS) else "uncollected"


def select_own_tests(paths: list[str], patterns: list[str], exists: Callable[[str], bool]) -> dict[str, list[str]]:
    """Group the changed *paths* that are test files and still *exist* in the tested tree."""
    groups: dict[str, list[str]] = {name: [] for name in OWN_GROUPS}
    for path in sorted(set(paths)):
        group = group_of(path, patterns)
        if group is not None and exists(path):
            groups[group].append(path)
    return groups


def changed_paths(base_sha: str, head_sha: str, kinds: str = CHANGED_FILTER) -> list[str]:
    """Files of the *kinds* (``--diff-filter`` letters) the head has relative to the merge base (three-dot diff)."""
    for sha in (base_sha, head_sha):
        if not BASE_SHA_PATTERN.fullmatch(sha):
            raise SystemExit(f"{sha!r} is not a full commit id")
    out = _git("diff", "--name-only", "-z", f"--diff-filter={kinds}", f"{base_sha}...{head_sha}")
    return [p for p in out.split("\0") if p]


def write_own_tests(root: Path, base_sha: str, head_sha: str, out_dir: Path) -> dict[str, int]:
    """Write one ``<group>.txt`` per group (a path per line) into *out_dir*; return the counts."""
    paths, patterns = changed_paths(base_sha, head_sha), python_file_patterns(root)
    groups = select_own_tests(paths, patterns, lambda p: (root / p).is_file())
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, files in groups.items():
        (out_dir / f"{name}.txt").write_text("".join(f"{f}\n" for f in files), encoding="utf-8")
    return {name: len(files) for name, files in groups.items()}


def _changed_tests(root: Path, args: argparse.Namespace) -> None:
    counts = write_own_tests(root, args.base_sha, args.head_sha, Path(args.out_dir))
    sys.stdout.write("".join(f"{name}={count}\n" for name, count in counts.items()))
    if not counts["main"] and not counts["slm"]:
        sys.stderr.write("no changed test files\n")
    if counts["guarded"]:
        sys.stderr.write(f"{counts['guarded']} changed test file(s) in the guard roots run in the guard shards\n")
    if counts["uncollected"]:
        sys.stderr.write(f"::notice::{counts['uncollected']} changed test file(s) the suite does not collect\n")


def headerless_additions(base_sha: str, head_sha: str) -> list[str]:
    """Files the head brings in that are in the header check's scope and whose COMMITTED text at it has no header.

    Read with ``git show <head>:<path>``, never from the working tree, which the lane has changed by merging the base.
    A file the head only modifies is not judged: a header it already lacked is not this head's addition.
    """
    return [
        path
        for path in changed_paths(base_sha, head_sha, ARRIVED_FILTER)
        if lacks_header(Path(path), lambda path=path: _git("show", f"{head_sha}:{path}"))
    ]


def _added_headers(args: argparse.Namespace) -> int:
    pinned_base_commit(args.base_sha)  # the base may not be in the branch's history: fetch it by id first
    missing = headerless_additions(args.base_sha, args.head_sha)
    for path in missing:
        sys.stderr.write(f"{path}: added without the SPDX/Apache-2.0 license header\n")
    if missing:
        sys.stderr.write(f"::error::{len(missing)} added file(s) lack the license header; add it and commit\n")
        return 1
    sys.stdout.write("added files with the license header: all\n")
    return 0


def build_meta(root: Path, shard: int, splits: int, rc: int | None, env: dict[str, str]) -> dict[str, Any]:
    """What one shard records. ``rc`` is ``None`` when the head conflicted and no test ran."""
    roots = guard_roots(root)
    return {
        "shard": shard,
        "splits": splits,
        "rc": rc,
        "merged": env.get("MERGED") == "true",
        "base_sha": env.get("BASE_SHA", ""),
        "behind_base": int(env.get("BEHIND_BASE") or 0),
        "floor": floor_for(root),
        "roots": roots,
        "required_files": required_files(root, roots),
    }


def build_types_meta(env: dict[str, str]) -> dict[str, Any]:
    """What the types job records: the merge state and the base commit it tested."""
    return {"merged": env.get("MERGED") == "true", "base_sha": env.get("BASE_SHA", "")}


def _summarize(args: argparse.Namespace) -> int:
    result = report.build_result(dict(os.environ), Path(args.shards), Path(args.types))
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    markdown = report.render_lane_summary(result)
    Path(args.markdown).write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    sys.stdout.write("\n".join(report.workflow_commands(result)) + "\n")
    return 0 if result["overall"] in report.BOARDABLE else 1


def _write_meta(args: argparse.Namespace) -> None:
    meta = build_meta(Path.cwd(), args.shard, args.splits, args.rc, dict(os.environ))
    Path(args.out).write_text(json.dumps(meta) + "\n", encoding="utf-8")


def _write_types_meta(args: argparse.Namespace) -> None:
    Path(args.out).write_text(json.dumps(build_types_meta(dict(os.environ))) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("roots")
    merge = sub.add_parser("merge")
    merge.add_argument("--base-sha", required=True)
    sub.add_parser("resolve").add_argument("--base-ref", required=True)
    sub.add_parser("types-meta").add_argument("--out", required=True)
    sub.add_parser("durations").add_argument("--out", required=True)
    meta = sub.add_parser("meta")
    meta.add_argument("--shard", type=int, required=True)
    meta.add_argument("--splits", type=int, required=True)
    meta.add_argument("--rc", type=int, default=None)
    meta.add_argument("--out", required=True)
    own = sub.add_parser("changed-tests")
    for flag in ("--base-sha", "--head-sha", "--out-dir"):
        own.add_argument(flag, required=True)
    added = sub.add_parser("added-headers")
    for flag in ("--base-sha", "--head-sha"):
        added.add_argument(flag, required=True)
    summarize = sub.add_parser("summarize")
    for flag in ("--shards", "--types", "--out", "--markdown"):
        summarize.add_argument(flag, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path.cwd()
    if args.command == "roots":
        sys.stdout.write("\n".join(guard_roots(root)) + "\n")
    elif args.command == "resolve":
        sys.stdout.write(f"base_sha={resolve_base_sha(args.base_ref)}\n")
    elif args.command == "merge":
        sys.stdout.write("".join(f"{k}={v}\n" for k, v in merge_base_into_head(args.base_sha).items()))
    elif args.command == "types-meta":
        _write_types_meta(args)
    elif args.command == "durations":
        Path(args.out).write_text(json.dumps(lane_durations(root, guard_roots(root))) + "\n", encoding="utf-8")
    elif args.command == "meta":
        _write_meta(args)
    elif args.command == "changed-tests":
        _changed_tests(root, args)
    elif args.command == "added-headers":
        return _added_headers(args)
    else:
        return _summarize(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
