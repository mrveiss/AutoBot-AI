#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-board guard lane's one definition of what it runs and what it reports (#21359).

``.github/workflows/dispatch-preboard-guards.yml`` is dispatched on a member PR's head before
it boards a merge train (#18499, AC4). The workflow holds no test root, no count and no
verdict logic: it asks this module.

* ``roots``   -- the test roots the lane runs. :data:`GUARD_ROOTS` is the only place they are
  written, and each must also be a ``testpaths`` entry of ``pytest.ini``: a root the suite
  stopped collecting fails the lane instead of being run on its own.
* ``floor``   -- the fewest tests the lane may collect. Derived from ``.test_durations``, the
  suite's own record of what it ran, so it follows the tree instead of a number written here.
* ``base``    -- the merge base with the base branch and how far behind it the head is.
* ``summarize`` -- the machine-readable result (see :func:`build_result`) and its job summary.

The result is green only when every check succeeded, every shard reported, and at least the
floor was collected. A lane that ran nothing, or a shard that never reported, is red.
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
import xml.etree.ElementTree as ET  # nosec B405  # parses the junit file pytest itself wrote
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402
from tools.lint._comment_syntax import code_lines  # noqa: E402

#: The guard trees, as named in pytest.ini's ``testpaths``. The only copy of this list.
GUARD_ROOTS = ("repo_tests", "pipeline-scripts")

#: The suite's own record of the tests it runs, one node id per entry.
DURATIONS_FILE = ".test_durations"

#: Share of the recorded guard tests the lane must still collect. The record is regenerated
#: periodically, so the tree can drift from it; the ratio only has to separate "drifted" from
#: "ran the wrong thing or nothing".
FLOOR_RATIO = 0.9

#: Bumped when a field of the result artifact is renamed or removed.
SCHEMA_VERSION = 1

#: The branch names the ``base`` input may carry.
BASE_REF_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


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


def recorded_count(root: Path, roots: list[str]) -> int:
    """How many node ids of ``.test_durations`` sit under *roots*."""
    record = json.loads((root / DURATIONS_FILE).read_text(encoding="utf-8"))
    prefixes = tuple(f"{r}/" for r in roots)
    return sum(1 for node in record if node.startswith(prefixes))


def floor_for(root: Path, ratio: float = FLOOR_RATIO) -> int:
    """The collected-test floor. Refuses when the record says nothing about the roots."""
    recorded = recorded_count(root, guard_roots(root))
    if recorded < 1:
        raise SystemExit(f"{DURATIONS_FILE} records no test under {list(GUARD_ROOTS)}; no floor can be derived")
    return max(1, math.floor(recorded * ratio))


def _git(*args: str) -> str:
    argv, env = ["git", *args], scrubbed_git_env()
    done = subprocess.run(argv, capture_output=True, text=True, timeout=300, env=env)  # nosec B603 B607
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {done.stderr.strip()}")
    return done.stdout.strip()


def lane_base_commit(base_ref: str) -> dict[str, str]:
    """Fetch *base_ref* and name the merge base and how many commits the head lacks."""
    if not BASE_REF_PATTERN.fullmatch(base_ref) or ".." in base_ref:
        raise SystemExit(f"base {base_ref!r} is not a plain branch name")
    _git("fetch", "--no-tags", "origin", f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}")
    tip = f"refs/remotes/origin/{base_ref}"
    return {
        "base_sha": _git("merge-base", "HEAD", tip),
        "behind_base": _git("rev-list", "--count", f"HEAD..{tip}"),
    }


def _first_line(text: str | None) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


def node_id(case: ET.Element) -> str:
    """The pytest node id of a junit ``testcase`` (xunit1 carries ``file``)."""
    name, classname, path = case.get("name", ""), case.get("classname", ""), case.get("file", "")
    if not path:
        return f"{classname}::{name}"
    module = path[:-3].replace("/", ".") if path.endswith(".py") else path
    parts = classname[len(module) + 1 :].split(".") if classname.startswith(module + ".") else []
    return "::".join([path, *parts, name])


def parse_junit(path: Path) -> dict[str, Any]:
    """Counts, failed and skipped tests of one junit file."""
    out: dict[str, Any] = {"collected": 0, "failed": [], "skipped": []}
    for case in ET.parse(path).getroot().iter("testcase"):  # nosec B314  # our own pytest output
        out["collected"] += 1
        for kind in ("failure", "error"):
            found = case.find(kind)
            if found is not None:
                message = found.get("message") or found.text
                out["failed"].append({"nodeid": node_id(case), "kind": kind, "message": _first_line(message)})
        skipped = case.find("skipped")
        if skipped is not None:
            out["skipped"].append({"nodeid": node_id(case), "reason": _first_line(skipped.get("message"))})
    return out


def read_shards(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every shard's meta (exit code, shard, splits) and the sum of its junit file."""
    metas, total = [], {"collected": 0, "failed": [], "skipped": []}
    for meta_path in sorted(directory.rglob("shard-meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        metas.append(meta)
        junit = meta_path.parent / "junit.xml"
        if junit.is_file():
            parsed = parse_junit(junit)
            meta["collected"], meta["failed"] = parsed["collected"], len(parsed["failed"])
            total["collected"] += parsed["collected"]
            total["failed"] += parsed["failed"]
            total["skipped"] += parsed["skipped"]
    return metas, total


def shard_problems(metas: list[dict[str, Any]]) -> list[str]:
    """Reasons the shards do not add up to a complete run."""
    if not metas:
        return ["no shard reported"]
    splits = {int(m["splits"]) for m in metas}
    reported = {int(m["shard"]) for m in metas}
    problems = []
    if len(splits) != 1 or reported != set(range(1, next(iter(splits)) + 1)):
        problems.append(f"shards reported {sorted(reported)} of splits {sorted(splits)}")
    problems += [f"shard {m['shard']} exited {m['rc']}" for m in metas if int(m["rc"]) not in (0, 1)]
    problems += [f"shard {m['shard']} collected no test" for m in metas if not m.get("collected")]
    problems += [
        f"shard {m['shard']} exited 1 with no failed test on record"
        for m in metas
        if int(m["rc"]) == 1 and not m.get("failed")
    ]
    return problems


def guards_status(needs_result: str, problems: list[str], collected: int, floor: int) -> str:
    """``success`` only when the job passed AND the run was complete AND at least the floor ran."""
    if needs_result == "cancelled":
        return "cancelled"
    if needs_result != "success" or problems or collected < floor:
        return "failure"
    return "success"


def lane_verdict(statuses: list[str]) -> str:
    if "cancelled" in statuses:
        return "cancelled"
    return "green" if statuses and all(s == "success" for s in statuses) else "red"


def _checks(needs: dict[str, Any], metas: list[dict[str, Any]], total: dict[str, Any], floor: int) -> dict[str, Any]:
    problems = shard_problems(metas)
    guards = guards_status(needs["guards"]["result"], problems, total["collected"], floor)
    return {
        "guards": {
            "status": guards,
            "collected": total["collected"],
            "floor": floor,
            "failed": len(total["failed"]),
            "skipped": len(total["skipped"]),
            "shards": len(metas),
            "problems": problems,
        },
        "types": {"status": needs["types"]["result"]},
    }


def build_result(env: dict[str, str], shard_dir: Path, floor: int, roots: list[str]) -> dict[str, Any]:
    """The result document. Field names are the contract documented in the workflow header."""
    metas, total = read_shards(shard_dir)
    checks = _checks(json.loads(env["NEEDS_JSON"]), metas, total, floor)
    return {
        "schema": SCHEMA_VERSION,
        "run_id": env.get("RUN_ID", ""),
        "ref": env.get("REF", ""),
        "sha": env.get("SHA", ""),
        "base_ref": env.get("BASE_REF", ""),
        "base_sha": env.get("BASE_SHA", ""),
        "behind_base": int(env.get("BEHIND_BASE") or 0),
        "overall": lane_verdict([checks["guards"]["status"], checks["types"]["status"]]),
        "roots": roots,
        "checks": checks,
        "failed_tests": total["failed"],
        "skipped_tests": total["skipped"],
    }


def render_lane_summary(result: dict[str, Any]) -> str:
    """The job summary: verdict, per-check status, every failed node id."""
    guards = result["checks"]["guards"]
    lines = [
        f"## Pre-board guard lane: {result['overall']}",
        f"`{result['sha']}` on `{result['ref']}`, base `{result['base_sha']}` ({result['behind_base']} behind)",
        "",
        "| check | status |",
        "|---|---|",
        f"| guards ({guards['collected']} collected, floor {guards['floor']}, "
        f"{guards['failed']} failed, {guards['skipped']} skipped) | {guards['status']} |",
        f"| types | {result['checks']['types']['status']} |",
    ]
    lines += [f"- lane problem: {p}" for p in guards["problems"]]
    failed = [f"- `{t['nodeid']}` ({t['kind']}): {t['message']}" for t in result["failed_tests"]]
    lines += ["", "### Failed tests", *failed]
    return "\n".join(lines) + "\n"


def _summarize(args: argparse.Namespace) -> int:
    root = Path.cwd()
    result = build_result(dict(os.environ), Path(args.shards), floor_for(root), guard_roots(root))
    Path(args.out).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    markdown = render_lane_summary(result)
    Path(args.markdown).write_text(markdown, encoding="utf-8")
    sys.stdout.write(markdown)
    return 0 if result["overall"] == "green" else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("roots")
    sub.add_parser("floor")
    base = sub.add_parser("base")
    base.add_argument("--base-ref", required=True)
    summarize = sub.add_parser("summarize")
    for flag in ("--shards", "--out", "--markdown"):
        summarize.add_argument(flag, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    root = Path.cwd()
    if args.command == "roots":
        sys.stdout.write("\n".join(guard_roots(root)) + "\n")
    elif args.command == "floor":
        sys.stdout.write(f"{floor_for(root)}\n")
    elif args.command == "base":
        sys.stdout.write("".join(f"{k}={v}\n" for k, v in lane_base_commit(args.base_ref).items()))
    else:
        return _summarize(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
