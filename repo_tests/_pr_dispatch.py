# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared reading of the workflow files for the dispatch-only guards (#20825).

A pull request gets CI only when the PR coordinator dispatches it, so the guards that hold that shape
share one reader: the triggers of a workflow in all three YAML forms, the coordinator's dispatch
contract, and the strings a workflow evaluates (never its comments).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterator, List, Set

import yaml
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ACTIONS = REPO_ROOT / ".github" / "actions"
FILTERS = REPO_ROOT / ".github" / "filters"

#: The pins every dispatched run carries. The names are the PR coordinator's (dev-skills scripts/pr-coordinator,
#: `dispatch_workflow`: inputs[pr_number], inputs[head_sha], inputs[base_sha]); a rename here breaks every dispatch.
PINS = ("pr_number", "head_sha", "base_sha")

#: What the coordinator dispatches itself (its SUITE_WORKFLOWS + META_WORKFLOWS). Their pins are REQUIRED.
COORDINATOR_DISPATCHED = (
    "ci.yml",
    "no-commit-trailers.yml",
    "pr-blocking-findings.yml",
    "pr-template-check.yml",
    "pr-issue-validation.yml",
    "pr-structure.yml",
)

#: Events a pull request must never start a run through, and a branch the events below may name.
PR_EVENTS = frozenset({"pull_request", "pull_request_target", "pull_request_review", "pull_request_review_comment"})
PROTECTED_BRANCHES = frozenset({"main", "release"})


def load(path: Path) -> Dict[Any, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def workflow_files() -> List[Path]:
    return sorted(WORKFLOWS.glob("*.yml"))


def action_files() -> List[Path]:
    return sorted(ACTIONS.glob("*/action.yml"))


def triggers(doc: Dict[Any, Any]) -> Dict[str, Any]:
    """``on:`` as a mapping name -> config, whatever form it was written in (YAML reads a bare ``on`` as True)."""
    raw = doc.get(True) if True in doc else doc.get("on")
    if raw is None:
        return {}
    if isinstance(raw, str):
        return {raw: None}
    if isinstance(raw, list):
        return {str(name): None for name in raw}
    return {str(name): config for name, config in raw.items()}


def dispatch_inputs(doc: Dict[Any, Any]) -> Dict[str, Any]:
    config = triggers(doc).get("workflow_dispatch")
    return dict((config or {}).get("inputs") or {}) if isinstance(config, dict) else {}


def trigger_violations(doc: Dict[Any, Any]) -> List[str]:
    """Why this workflow could start a run for a pull request (or for a non-protected branch push)."""
    found: List[str] = []
    events = triggers(doc)
    for name in sorted(PR_EVENTS & set(events)):
        found.append(f"subscribes to `{name}`")
    push = events.get("push", False)
    if push is not False:
        config = push or {}
        if config.get("tags"):
            return found                              # a tag push is no pull request's branch
        branches = config.get("branches")
        if not branches:
            found.append("`push` without `branches:` fires for every branch, pull request branches included")
        else:
            wild = sorted(str(b) for b in branches if str(b) not in PROTECTED_BRANCHES)
            if wild:
                found.append(f"`push` names non-protected branch(es) {wild}")
    return found


def strings(node: Any) -> Iterator[str]:
    """Every string a workflow or action evaluates or runs. Comments are not YAML data, so they never appear."""
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield from strings(key)
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)


def satellite_keys() -> Set[str]:
    keys: Set[str] = set()
    for name in ("satellite-paths.yml", "satellite-paths-ignore.yml"):
        keys |= set(load(FILTERS / name))
    return keys
