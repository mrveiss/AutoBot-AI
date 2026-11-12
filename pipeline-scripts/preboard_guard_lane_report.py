#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the pre-board guard lane reports: junit in, one verdict out (#21359).

Split from ``preboard_guard_lane.py`` (the roots, the merge with the base, the shard metadata)
so each stays small. This module reads what the shards wrote and decides ``overall``:

* ``green``             -- every test that ran passed and nothing was skipped.
* ``green_with_skips``  -- the same, and every skip is on :data:`SKIP_ALLOWLIST`, each in one class:
  ``covered-by-suite-only`` (the lane skips it, the train's suite RUNS it) or ``equivalent-to-suite``
  (the suite skips it the same way on the same runner image, so the train is no stricter than the lane).
  The entries and their evidence live in ``preboard_guard_lane_skips.py``.
* ``red``               -- a failure, a missing shard or recorded test file, a conflict with the
  base, a skip nobody reviewed, or fewer executed tests than the floor.
* ``cancelled``         -- a job was cancelled. Never boardable.

The floor counts EXECUTED tests (passed, failed, errored). A skipped test is collected but is
evidence of nothing, so a mass skip can neither satisfy the floor nor stay unnoticed.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET  # nosec B405  # parses the junit file pytest itself wrote
from pathlib import Path
from typing import Any

import preboard_guard_lane_junit as junit
from preboard_guard_lane_skips import (  # noqa: F401  # re-exported: the lane and its guards read them from here
    COVERED_BY_SUITE_ONLY,
    EQUIVALENT_TO_SUITE,
    FOLLOW_UP,
    SKIP_ALLOWLIST,
    SKIP_CLASSES,
    AllowedSkip,
    stale_entries,
)

#: Bumped when a field of the result artifact is renamed or removed.
SCHEMA_VERSION = 2

#: Verdicts an operator may board on. Anything else is not boardable.
BOARDABLE = ("green", "green_with_skips")

#: A skip on neither list. Never accepted.
UNREVIEWED = "unreviewed"


def skip_class(nodeid: str, reason: str, allowlist: tuple[AllowedSkip, ...] = SKIP_ALLOWLIST) -> str:
    """The class of a skip of *nodeid* for *reason*: file AND reason prefix must match, else ``unreviewed``."""
    file = junit.file_of(nodeid)
    for entry in allowlist:
        dotted = entry.file[:-3].replace("/", ".")
        if file in (entry.file, dotted) and reason.startswith(entry.reason_prefix):
            return entry.skip_class
    return UNREVIEWED


def is_allowed_skip(nodeid: str, reason: str, allowlist: tuple[AllowedSkip, ...] = SKIP_ALLOWLIST) -> bool:
    """Whether a skip of *nodeid* for *reason* is a reviewed one."""
    return skip_class(nodeid, reason, allowlist) != UNREVIEWED


def _classified(raw: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Each raw skip with its class and whether it is on the allowlist."""
    rows = []
    for skip in raw:
        klass = skip_class(skip["nodeid"], skip["reason"])
        rows.append({**skip, "allowed": klass != UNREVIEWED, "skip_class": klass})
    return rows


def _absorb(meta: dict[str, Any], junit_file: Path, total: dict[str, Any]) -> list[str]:
    """Add one shard's junit to *total*; the problem when it cannot be read."""
    meta["executed"] = 0
    if not junit_file.is_file():
        return []
    try:
        parsed = junit.parse_junit(junit_file)
    except (ET.ParseError, OSError) as err:
        meta["junit_unreadable"] = True
        return [f"shard {meta.get('shard')}: junit.xml is unreadable ({err})"]
    skipped = _classified(parsed["skipped"])
    meta["executed"], meta["failed"] = parsed["executed"], len(parsed["failed"])
    total["executed"] += parsed["executed"]
    total["failed"] += parsed["failed"]
    total["skipped"] += skipped
    total["produced"] |= parsed["ran"] | {junit.file_of(s["nodeid"]) for s in skipped if s["allowed"]}
    return []


def read_shards(directory: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    """Every shard's meta, the sum of its junit file, and what could not be read."""
    metas, problems = [], []
    total: dict[str, Any] = {"executed": 0, "failed": [], "skipped": [], "produced": set()}
    for meta_path in sorted(directory.rglob("shard-meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError as err:
            problems.append(f"{meta_path.parent.name}: shard-meta.json is unreadable ({err})")
            continue
        metas.append(meta)
        problems += _absorb(meta, meta_path.parent / "junit.xml", total)
    return metas, total, problems


def _one_shard_problems(meta: dict[str, Any]) -> list[str]:
    number = meta["shard"]
    if not meta.get("merged"):
        return [f"shard {number}: the head conflicts with base {str(meta.get('base_sha'))[:12]}; nothing was tested"]
    found = []
    if int(meta["rc"]) not in (0, 1):
        found.append(f"shard {number} exited {meta['rc']}")
    if not meta.get("executed") and not meta.get("junit_unreadable"):
        found.append(f"shard {number} ran no test")
    if int(meta["rc"]) == 1 and not meta.get("failed") and not meta.get("junit_unreadable"):
        found.append(f"shard {number} exited 1 with no failed test on record")
    return found


def shard_problems(metas: list[dict[str, Any]]) -> list[str]:
    """Reasons the shards do not add up to a complete run."""
    if not metas:
        return ["no shard reported"]
    splits = {int(m["splits"]) for m in metas}
    reported = {int(m["shard"]) for m in metas}
    problems = []
    if len(splits) != 1 or reported != set(range(1, next(iter(splits)) + 1)):
        problems.append(f"shards reported {sorted(reported)} of splits {sorted(splits)}")
    if len({m.get("base_sha") for m in metas}) > 1:
        problems.append("shards tested different base commits; dispatch the lane again")
    for meta in metas:
        problems += _one_shard_problems(meta)
    return problems


def file_problems(required: list[str], produced: set[str]) -> list[str]:
    """Recorded test files that produced no executed or allowlisted-skipped test."""
    return [
        f"recorded test file produced no test (deleted, deselected, or lost to collection): {path}"
        for path in required
        if path not in produced
    ]


def guards_status(needs_result: str, problems: list[str], counts: dict[str, int], floor: int) -> str:
    """``success`` only when the job passed, no test failed, the run was complete and the floor EXECUTED.

    *counts* holds ``executed``, ``failed`` and ``allowed_skips``.
    """
    if needs_result == "cancelled":
        return "cancelled"
    if needs_result != "success" or problems or counts["failed"] or counts["executed"] < floor:
        return "failure"
    return "success_with_skips" if counts["allowed_skips"] else "success"


def lane_verdict(guards: str, types: str) -> str:
    """``cancelled`` beats everything; ``green_with_skips`` is never reported as ``green``."""
    if "cancelled" in (guards, types):
        return "cancelled"
    if types != "success" or guards not in ("success", "success_with_skips"):
        return "red"
    return "green" if guards == "success" else "green_with_skips"


def lane_facts(metas: list[dict[str, Any]]) -> dict[str, Any]:
    """What the shards recorded about the tree they tested: base, merge state, floor, roots, files."""
    first = metas[0] if metas else {}
    return {
        "base_sha": str(first.get("base_sha") or ""),
        "behind_base": int(first.get("behind_base") or 0),
        "merged": bool(metas) and all(m.get("merged") is True for m in metas),
        "floor": max([int(m.get("floor") or 0) for m in metas] or [0]),
        "roots": list(first.get("roots") or []),
        "required": sorted({f for m in metas for f in m.get("required_files") or []}),
    }


def skip_class_counts(skipped: list[dict[str, Any]]) -> dict[str, int]:
    """How many skips fall in each class, every class present (zero included)."""
    return {name: sum(1 for s in skipped if s["skip_class"] == name) for name in (*SKIP_CLASSES, UNREVIEWED)}


def guards_check(needs: dict[str, Any], metas: list[dict[str, Any]], total: dict[str, Any], read: list[str]) -> dict:
    """The ``checks.guards`` object."""
    facts = lane_facts(metas)
    problems = read + shard_problems(metas) + file_problems(facts["required"], total["produced"])
    unreviewed = [s for s in total["skipped"] if not s["allowed"]]
    if unreviewed:
        problems.append(f"{len(unreviewed)} skipped test(s) are not on the reviewed skip allowlist; see skipped_tests")
    allowed = len(total["skipped"]) - len(unreviewed)
    counts = {"executed": total["executed"], "failed": len(total["failed"]), "allowed_skips": allowed}
    status = guards_status(needs["guards"]["result"], problems, counts, facts["floor"])
    return {
        "status": status,
        "executed": total["executed"],
        "floor": facts["floor"],
        "failed": len(total["failed"]),
        "skipped": len(total["skipped"]),
        "unreviewed_skips": len(unreviewed),
        "skip_classes": skip_class_counts(total["skipped"]),
        "shards": len(metas),
        "problems": problems,
    }


def build_result(env: dict[str, str], shard_dir: Path) -> dict[str, Any]:
    """The result document. Field names are the contract documented in the workflow header."""
    metas, total, read = read_shards(shard_dir)
    needs, facts = json.loads(env["NEEDS_JSON"]), lane_facts(metas)
    guards = guards_check(needs, metas, total, read)
    types = needs["types"]["result"]
    return {
        "schema": SCHEMA_VERSION,
        "run_id": env.get("RUN_ID", ""),
        "ref": env.get("REF", ""),
        "sha": env.get("SHA", ""),
        "base_ref": env.get("BASE_REF", ""),
        "base_sha": facts["base_sha"],
        "behind_base": facts["behind_base"],
        "merged": facts["merged"],
        "overall": lane_verdict(guards["status"], types),
        "roots": facts["roots"],
        "checks": {"guards": guards, "types": {"status": types}},
        "failed_tests": total["failed"],
        "skipped_tests": total["skipped"],
    }


def _skip_lines(skipped: list[dict[str, Any]]) -> list[str]:
    """Every skipped node id, grouped by reason and marked reviewed or not."""
    groups: dict[tuple[str, str], list[str]] = {}
    for skip in skipped:
        groups.setdefault((skip["reason"], skip["skip_class"]), []).append(skip["nodeid"])
    lines = []
    for (reason, klass), nodeids in sorted(groups.items()):
        label = "NOT ON THE ALLOWLIST" if klass == UNREVIEWED else f"allowlisted, {klass}"
        lines.append(f"- {label}: {reason or '(no reason)'}")
        lines += [f"  - `{nodeid}`" for nodeid in nodeids]
    return lines


def render_lane_summary(result: dict[str, Any]) -> str:
    """The job summary: verdict, per-check status, every failed and every skipped node id."""
    guards = result["checks"]["guards"]
    classes = ", ".join(f"{name} {count}" for name, count in guards["skip_classes"].items())
    lines = [
        f"## Pre-board guard lane: {result['overall']}",
        f"`{result['sha']}` on `{result['ref']}`, merged with base `{result['base_sha']}`: {result['merged']} "
        f"({result['behind_base']} behind)",
        "",
        "| check | status |",
        "|---|---|",
        f"| guards ({guards['executed']} executed, floor {guards['floor']}, "
        f"{guards['failed']} failed, {guards['skipped']} skipped) | {guards['status']} |",
        f"| types | {result['checks']['types']['status']} |",
        "",
        f"Skips by class: {classes}. `covered-by-suite-only` is still exercised by the train's suite; "
        "`equivalent-to-suite` is skipped there too.",
        "",
    ]
    lines += [f"- lane problem: {p}" for p in guards["problems"]]
    failed = [f"- `{t['nodeid']}` ({t['kind']}): {t['message']}" for t in result["failed_tests"]]
    lines += ["", "### Failed tests", *failed, "", "### Skipped tests", *_skip_lines(result["skipped_tests"])]
    return "\n".join(lines) + "\n"


def _escape_command(text: str) -> str:
    """Workflow-command data: ``%``, CR and LF must be escaped or the line ends early."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


#: GitHub shows at most ten annotations of one level per step; the full list is in the summary.
MAX_ERROR_LINES = 9


def _error_lines(result: dict[str, Any]) -> list[str]:
    """One ``::error`` per lane problem, then per failed test, up to :data:`MAX_ERROR_LINES`."""
    texts = list(result["checks"]["guards"]["problems"])
    texts += [f"{t['nodeid']} ({t['kind']}): {t['message']}" for t in result["failed_tests"]]
    return [f"::error::{_escape_command(text)}" for text in texts[:MAX_ERROR_LINES]]


def workflow_commands(result: dict[str, Any]) -> list[str]:
    """The annotations that put the verdict on the run's page: ``overall``, skips by class, ``behind_base``."""
    guards, overall, behind = result["checks"]["guards"], result["overall"], result["behind_base"]
    classes = ", ".join(f"{name}={count}" for name, count in guards["skip_classes"].items())
    head = f"overall={overall}; behind_base={behind}; skips: {classes}; executed={guards['executed']}"
    level = "notice" if overall == "green" else "warning" if overall == "green_with_skips" else "error"
    lines = [f"::{level} title=Pre-board guard lane::{_escape_command(head)}"]
    if overall in BOARDABLE:
        if behind:
            lines.append(f"::warning::behind_base={behind}: merge the base into the head, then dispatch again to board")
        return lines
    return lines + _error_lines(result)
