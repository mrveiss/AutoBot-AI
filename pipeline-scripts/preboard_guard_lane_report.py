#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""What the pre-board guard lane reports: junit in, one verdict out (#21359).

Split from ``preboard_guard_lane.py`` (the roots, the merge with the base, the shard metadata)
so each stays small. This module reads what the shards wrote and decides ``overall``:

* ``green``             -- every test that ran passed and nothing was skipped.
* ``green_with_skips``  -- the same, and every skip is on :data:`SKIP_ALLOWLIST`. The skipped
  checks are not covered by the lane; the merge train's full suite covers them.
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
from typing import Any, NamedTuple

#: Bumped when a field of the result artifact is renamed or removed.
SCHEMA_VERSION = 2

#: Verdicts an operator may board on. Anything else is not boardable.
BOARDABLE = ("green", "green_with_skips")

#: The ``type`` pytest gives the ``skipped`` element of an expected failure: it RAN.
XFAIL_TYPE = "pytest.xfail"


#: The issue that removes every allowlist entry, by moving the skipped check into a composite action.
FOLLOW_UP = "#21360"


class AllowedSkip(NamedTuple):
    """One reviewed skip: the file, the start of its reason, the text proving it exists, its follow-up."""

    file: str
    reason_prefix: str
    source_marker: str
    follow_up: str = FOLLOW_UP


#: The skips this lane accepts, each because the check is left out of the lane by design: it needs
#: a service or a binary the suite's python-shard job provides and this workflow does not.
#: ``source_marker`` is text that must stay in ``file``, so an entry cannot outlive the skip it
#: names (checked by the lane's guard test). Follow-up #21360 moves each check into a composite
#: action both workflows call; the entry for it is removed in that change. A skip not listed
#: here makes the verdict ``red``: add an entry only after reading what the test skips on.
SKIP_ALLOWLIST: tuple[AllowedSkip, ...] = (
    # #21360: promtool is installed by ci.yml's python-shard job only.
    AllowedSkip("repo_tests/promtool_rules_test.py", "promtool not found at", "promtool not found at"),
    # #21360: the real-ChromaDB tests run in their own session in ci.yml (shard 1); here they skip
    # when the library is stubbed or absent.
    AllowedSkip(
        "repo_tests/backup_embeddings_on_real_chroma_19647_test.py",
        "chromadb is stubbed, not the real library",
        "chromadb is stubbed, not the real library",
    ),
    AllowedSkip(
        "repo_tests/backup_embeddings_on_real_chroma_19647_test.py",
        "could not import 'chromadb'",
        'importorskip("chromadb")',
    ),
    AllowedSkip(
        "repo_tests/chromadb_missing_key_serving_where_18820_test.py",
        "chromadb is stubbed, not the real library",
        "chromadb is stubbed, not the real library",
    ),
    AllowedSkip(
        "repo_tests/chromadb_missing_key_serving_where_18820_test.py",
        "could not import 'chromadb'",
        'importorskip("chromadb")',
    ),
)


def _first_line(text: str | None) -> str:
    return (text or "").strip().splitlines()[0] if (text or "").strip() else ""


def file_of(nodeid: str) -> str:
    """The file part of a node id."""
    return nodeid.split("::", 1)[0]


def node_id(case: ET.Element) -> str:
    """The pytest node id of a junit ``testcase`` (xunit1 carries ``file``)."""
    name, classname, path = case.get("name", ""), case.get("classname", ""), case.get("file", "")
    if not path:
        return f"{classname}::{name}"
    module = path[:-3].replace("/", ".") if path.endswith(".py") else path
    parts = classname[len(module) + 1 :].split(".") if classname.startswith(module + ".") else []
    return "::".join([path, *parts, name])


def is_allowed_skip(nodeid: str, reason: str, allowlist: tuple[AllowedSkip, ...] = SKIP_ALLOWLIST) -> bool:
    """Whether a skip of *nodeid* for *reason* is a reviewed one (file AND reason must match)."""
    file = file_of(nodeid)
    for entry in allowlist:
        dotted = entry.file[:-3].replace("/", ".")
        if file in (entry.file, dotted) and reason.startswith(entry.reason_prefix):
            return True
    return False


def _outcome(case: ET.Element) -> str:
    """``failed`` | ``skipped`` | ``passed``. An expected failure ran, so it is not a skip."""
    if case.find("failure") is not None or case.find("error") is not None:
        return "failed"
    skipped = case.find("skipped")
    if skipped is not None and skipped.get("type") != XFAIL_TYPE:
        return "skipped"
    return "passed"


def _failures(case: ET.Element, nodeid: str) -> list[dict[str, str]]:
    found = []
    for kind in ("failure", "error"):
        element = case.find(kind)
        if element is not None:
            message = element.get("message") or element.text
            found.append({"nodeid": nodeid, "kind": kind, "message": _first_line(message)})
    return found


def parse_junit(path: Path) -> dict[str, Any]:
    """Executed count, failures, skips and the files that produced a usable test, of one junit file."""
    out: dict[str, Any] = {"executed": 0, "failed": [], "skipped": [], "produced": set()}
    for case in ET.parse(path).getroot().iter("testcase"):  # nosec B314  # our own pytest output
        nodeid, outcome = node_id(case), _outcome(case)
        if outcome == "skipped":
            reason = _first_line(case.find("skipped").get("message"))
            allowed = is_allowed_skip(nodeid, reason)
            out["skipped"].append({"nodeid": nodeid, "reason": reason, "allowed": allowed})
            if allowed:
                out["produced"].add(file_of(nodeid))
            continue
        out["executed"] += 1
        out["produced"].add(file_of(nodeid))
        out["failed"] += _failures(case, nodeid)
    return out


def _absorb(meta: dict[str, Any], junit: Path, total: dict[str, Any]) -> list[str]:
    """Add one shard's junit to *total*; the problem when it cannot be read."""
    meta["executed"] = 0
    if not junit.is_file():
        return []
    try:
        parsed = parse_junit(junit)
    except (ET.ParseError, OSError) as err:
        meta["junit_unreadable"] = True
        return [f"shard {meta.get('shard')}: junit.xml is unreadable ({err})"]
    meta["executed"], meta["failed"] = parsed["executed"], len(parsed["failed"])
    total["executed"] += parsed["executed"]
    total["failed"] += parsed["failed"]
    total["skipped"] += parsed["skipped"]
    total["produced"] |= parsed["produced"]
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
    groups: dict[tuple[str, bool], list[str]] = {}
    for skip in skipped:
        groups.setdefault((skip["reason"], skip["allowed"]), []).append(skip["nodeid"])
    lines = []
    for (reason, allowed), nodeids in sorted(groups.items()):
        lines.append(f"- {'allowlisted' if allowed else 'NOT ON THE ALLOWLIST'}: {reason or '(no reason)'}")
        lines += [f"  - `{nodeid}`" for nodeid in nodeids]
    return lines


def render_lane_summary(result: dict[str, Any]) -> str:
    """The job summary: verdict, per-check status, every failed and every skipped node id."""
    guards = result["checks"]["guards"]
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
    ]
    lines += [f"- lane problem: {p}" for p in guards["problems"]]
    failed = [f"- `{t['nodeid']}` ({t['kind']}): {t['message']}" for t in result["failed_tests"]]
    lines += ["", "### Failed tests", *failed, "", "### Skipped tests", *_skip_lines(result["skipped_tests"])]
    return "\n".join(lines) + "\n"
