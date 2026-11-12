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
* ``merge``     -- the member head merged with the current tip of the base, as a local commit
  that is never pushed: the state a pull request's merge ref gives the suite.
* ``durations`` -- ``.test_durations`` restricted to the roots, so the shard plugin balances the
  lane's own tests instead of the whole suite's.
* ``meta``      -- what one shard records: its exit code, the merge state, the floor and the
  recorded test files it was expected to cover, derived from the tree it tested.
* ``summarize`` -- the machine-readable result and its job summary.
"""

from __future__ import annotations

import argparse
import configparser
import json
import math
import os
import re
import subprocess  # nosec B404  # git, argv list, no shell
import sys
from pathlib import Path
from typing import Any

# The repository root (autobot_shared, tools) and this directory (the report module, not a package).
for _entry in (str(Path(__file__).resolve().parent.parent), str(Path(__file__).resolve().parent)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import preboard_guard_lane_report as report  # noqa: E402

from autobot_shared.paths import scrubbed_git_env  # noqa: E402
from tools.lint._comment_syntax import code_lines  # noqa: E402

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

#: The suite's own record of the tests it runs, one node id per entry.
DURATIONS_FILE = ".test_durations"

#: Share of the recorded lane tests the lane must still EXECUTE. The record is regenerated
#: periodically, so the tree can drift from it; the ratio only has to separate "drifted" from
#: "ran the wrong thing or nothing".
FLOOR_RATIO = 0.9

#: The branch names the ``base`` input may carry.
BASE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")

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


def lane_base_commit(base_ref: str) -> dict[str, str]:
    """Fetch *base_ref*; name its tip and how many commits the head lacks from it."""
    if not BASE_REF_PATTERN.fullmatch(base_ref) or ".." in base_ref:
        raise SystemExit(f"base {base_ref!r} is not a plain branch name")
    _git("fetch", "--no-tags", "origin", f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}")
    tip = f"refs/remotes/origin/{base_ref}"
    return {"base_sha": _git("rev-parse", tip), "behind_base": _git("rev-list", "--count", f"HEAD..{tip}")}


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


def merge_base_into_head(base_ref: str) -> dict[str, str]:
    """The head merged with the base tip: ``base_sha``, ``behind_base`` and ``merged`` (true | false)."""
    info = lane_base_commit(base_ref)
    merged = _merge_or_conflict(info["base_sha"])
    return {**info, "merged": "true" if merged else "false"}


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


def _summarize(args: argparse.Namespace) -> int:
    result = report.build_result(dict(os.environ), Path(args.shards))
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    markdown = report.render_lane_summary(result)
    Path(args.markdown).write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    return 0 if result["overall"] in report.BOARDABLE else 1


def _write_meta(args: argparse.Namespace) -> None:
    meta = build_meta(Path.cwd(), args.shard, args.splits, args.rc, dict(os.environ))
    Path(args.out).write_text(json.dumps(meta) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("roots")
    merge = sub.add_parser("merge")
    merge.add_argument("--base-ref", required=True)
    sub.add_parser("durations").add_argument("--out", required=True)
    meta = sub.add_parser("meta")
    meta.add_argument("--shard", type=int, required=True)
    meta.add_argument("--splits", type=int, required=True)
    meta.add_argument("--rc", type=int, default=None)
    meta.add_argument("--out", required=True)
    summarize = sub.add_parser("summarize")
    for flag in ("--shards", "--out", "--markdown"):
        summarize.add_argument(flag, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path.cwd()
    if args.command == "roots":
        sys.stdout.write("\n".join(guard_roots(root)) + "\n")
    elif args.command == "merge":
        sys.stdout.write("".join(f"{k}={v}\n" for k, v in merge_base_into_head(args.base_ref).items()))
    elif args.command == "durations":
        Path(args.out).write_text(json.dumps(lane_durations(root, guard_roots(root))) + "\n", encoding="utf-8")
    elif args.command == "meta":
        _write_meta(args)
    else:
        return _summarize(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
