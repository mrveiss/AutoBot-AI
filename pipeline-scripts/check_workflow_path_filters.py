#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Fail when a workflow's path filter drifts from the canonical set (#12986).

The backend-Python path list was duplicated seven times across six workflows
with no source of truth. Adding a backend directory meant remembering all seven
places, and a miss was **silent**: the gate simply stopped running on the new
path. Nothing failed, the coverage just quietly shrank -- and for `api-wiring`
and `startup-import-smoke`, both required contexts, that is a blocking check
that no longer blocks anything on the paths it forgot.

`.github/filters/backend-python-paths.yml` now defines the set once. A
`changes` job's dorny/paths-filter step can load that file by path and needs no
policing. A workflow's ``on.push.paths`` / ``on.pull_request.paths`` trigger
cannot: GitHub offers no include mechanism for event path filters, so those
copies are unavoidable. This guard is what stops them being *silent*.

What it asserts, and why each assertion is phrased as a presence check
---------------------------------------------------------------------

An absent result reads as a clean result, which is the whole failure mode this
family keeps reproducing. So every lookup here proves its target exists before
it can pass:

* the canonical file parses and its key is a non-empty list of strings;
* every declared workflow file exists;
* every declared location resolves to a real ``paths:`` list in that file --
  a restructure or rename strands the declaration LOUDLY rather than exempting
  it silently;
* every declared location is a superset of the canonical set;
* every workflow whose dorny step loads the canonical file is declared here
  (reverse check: a new consumer cannot arrive undeclared);
* ``api-wiring.yml`` still has NO ``pull_request.paths`` (#12934). That absence
  is deliberate -- a path-filtered required check never reports and deadlocks
  the pull request -- and it is exactly the kind of asymmetry a later
  "tidy the filters into uniformity" pass would erase. Asserting the absence
  keeps it from being tidied back into a deadlock.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

CANONICAL_FILE = Path(".github/filters/backend-python-paths.yml")
CANONICAL_KEY = "backend-python"

WORKFLOWS = Path(".github/workflows")

# workflow filename -> event names whose `paths:` must carry the canonical set.
#
# This table is the declaration of intent. A workflow is either here, with the
# events that mean "backend Python changed", or in NOT_CONSUMERS below with the
# reason it is not. There is no third state, so nothing falls off the list by
# being forgotten.
INLINE_CONSUMERS: dict[str, tuple[str, ...]] = {
    "phase_validation.yml": ("push",),
    "security.yml": ("pull_request",),
    "ai-security-review.yml": ("pull_request",),
    "startup-import-smoke.yml": ("push",),
    "api-wiring.yml": ("push",),
    "auto-fix-generated-types.yml": ("pull_request",),
}

# Workflows that name a backend-Python directory but are deliberately NOT
# consumers of the canonical set. Recorded so a reader can see they were
# considered rather than missed.
NOT_CONSUMERS: dict[str, str] = {
    "verify-generated-types.yml": (
        "its `types` and `slm_types` filters are per-product generated-types "
        "triggers, deliberately scoped to one backend tree each; collapsing "
        "them into the canonical set would erase that split. Whether they "
        "should additionally watch autobot_shared/ is tracked separately."
    ),
}

# `paths:` on this event must stay ABSENT for these workflows (#12934).
REQUIRED_ABSENT_PATHS: dict[str, tuple[str, str]] = {
    "api-wiring.yml": (
        "pull_request",
        "#12934: a path-filtered required check never triggers, and an absent "
        "required context is treated as unsatisfied rather than passed, so the "
        "pull request is permanently blocked. The audit is gated on the "
        "`changes` job instead.",
    ),
}


def _load_yaml(path: Path) -> dict:
    """Parse *path*, or die. A file that will not parse is not a pass."""
    if not path.is_file():
        sys.exit(f"FATAL: {path} does not exist — refusing to report clean on a scope that is not there")
    try:
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        sys.exit(f"FATAL: {path} is not parseable YAML: {exc}")
    if not isinstance(parsed, dict):
        sys.exit(f"FATAL: {path} did not parse to a mapping — refusing to report clean")
    return parsed


def canonical_paths() -> list[str]:
    """The canonical set, flattened. Dies rather than returning an empty set."""
    entry = _load_yaml(CANONICAL_FILE).get(CANONICAL_KEY)
    if not isinstance(entry, list) or not entry:
        sys.exit(f"FATAL: {CANONICAL_FILE} has no non-empty '{CANONICAL_KEY}' list — nothing to enforce")
    flat = [item for item in entry if isinstance(item, str)]
    if len(flat) != len(entry):
        sys.exit(f"FATAL: '{CANONICAL_KEY}' in {CANONICAL_FILE} must be a flat list of strings")
    return flat


def _on_block(parsed: dict, path: Path) -> dict:
    """Return the workflow's `on:` mapping.

    PyYAML resolves the bare key ``on`` to the boolean ``True`` (YAML 1.1),
    so a plain ``parsed["on"]`` lookup returns nothing and every check below
    would pass over an unread file.
    """
    block = parsed.get(True, parsed.get("on"))
    if not isinstance(block, dict):
        sys.exit(f"FATAL: {path} has no usable `on:` mapping — refusing to report clean")
    return block


def _event_paths(parsed: dict, path: Path, event: str) -> list[str] | None:
    """`paths:` for *event*, or None when the event declares none."""
    block = _on_block(parsed, path).get(event)
    if not isinstance(block, dict):
        sys.exit(f"FATAL: {path} declares no `on.{event}:` mapping, but the guard's table says it should")
    paths = block.get("paths")
    if paths is None:
        return None
    if not isinstance(paths, list):
        sys.exit(f"FATAL: {path} `on.{event}.paths` is not a list")
    return [p for p in paths if isinstance(p, str)]


def _loads_canonical_file(parsed: dict) -> bool:
    """True when any dorny/paths-filter step in *parsed* reads the canonical file."""
    for job in (parsed.get("jobs") or {}).values():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if not isinstance(step, dict):
                continue
            if "dorny/paths-filter" not in str(step.get("uses", "")):
                continue
            if str((step.get("with") or {}).get("filters", "")).strip() == str(CANONICAL_FILE):
                return True
    return False


def check_inline_consumers(canonical: list[str]) -> tuple[list[str], int]:
    """Every declared inline copy must contain the whole canonical set."""
    failures: list[str] = []
    checked = 0
    for name, events in INLINE_CONSUMERS.items():
        workflow = WORKFLOWS / name
        parsed = _load_yaml(workflow)
        for event in events:
            paths = _event_paths(parsed, workflow, event)
            if paths is None:
                failures.append(f"{workflow}: `on.{event}` declares no `paths:` at all, but is a declared consumer")
                continue
            missing = [p for p in canonical if p not in paths]
            checked += 1
            if missing:
                failures.append(f"{workflow}: `on.{event}.paths` is missing {missing}")
            else:
                print(f"  OK     {workflow} on.{event}.paths carries all {len(canonical)} canonical entries")  # noqa: print
    return failures, checked


def check_required_absences() -> list[str]:
    """An absence that is load-bearing has to be asserted, not assumed."""
    failures: list[str] = []
    for name, (event, reason) in REQUIRED_ABSENT_PATHS.items():
        workflow = WORKFLOWS / name
        if _event_paths(_load_yaml(workflow), workflow, event) is not None:
            failures.append(f"{workflow}: `on.{event}.paths` must stay ABSENT. {reason}")
        else:
            print(f"  OK     {workflow} on.{event} has no `paths:` filter, as required")  # noqa: print
    return failures


def check_no_undeclared_consumer() -> list[str]:
    """A workflow that loads the canonical file must be declared, either way."""
    failures: list[str] = []
    declared = set(INLINE_CONSUMERS) | set(NOT_CONSUMERS)
    for workflow in sorted(WORKFLOWS.glob("*.yml")):
        if workflow.name in declared:
            continue
        if _loads_canonical_file(_load_yaml(workflow)):
            failures.append(
                f"{workflow}: loads {CANONICAL_FILE} but is not declared in INLINE_CONSUMERS or NOT_CONSUMERS. "
                "Add it, so its event triggers are policed too."
            )
    return failures


def check_declarations_resolve() -> list[str]:
    """Every declared workflow must exist.

    An allowlist entry naming a moved file exempts nothing and does it
    silently, so the table has to be checked against the tree.
    """
    return [
        f"{WORKFLOWS / name}: declared in this guard's table but does not exist — the table is stale"
        for name in sorted(set(INLINE_CONSUMERS) | set(NOT_CONSUMERS) | set(REQUIRED_ABSENT_PATHS))
        if not (WORKFLOWS / name).is_file()
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("filenames", nargs="*", help="ignored; the whole filter set is always checked")
    parser.parse_args(argv)

    canonical = canonical_paths()
    print(f"check-workflow-path-filters: canonical '{CANONICAL_KEY}' = {canonical}\n")  # noqa: print

    failures = check_declarations_resolve()
    if failures:  # a stale table cannot be used to judge anything else
        for failure in failures:
            print(f"  FAIL   {failure}")  # noqa: print
        return 1

    inline_failures, checked = check_inline_consumers(canonical)
    failures += inline_failures
    failures += check_required_absences()
    failures += check_no_undeclared_consumer()

    if checked == 0:
        print("\n  FAIL   0 inline path lists were checked — the guard scanned nothing")  # noqa: print
        return 1

    for name, reason in sorted(NOT_CONSUMERS.items()):
        print(f"  NOTE   {WORKFLOWS / name} is deliberately not a consumer: {reason}")  # noqa: print

    if not failures:
        print(f"\ncheck-workflow-path-filters: {checked} inline path list(s) match the canonical set")  # noqa: print
        return 0

    print(f"\ncheck-workflow-path-filters: {len(failures)} drift(s)\n")  # noqa: print
    for failure in failures:
        print(f"  FAIL   {failure}")  # noqa: print
    print(  # noqa: print
        f"\nThe canonical set lives in {CANONICAL_FILE}. GitHub has no include mechanism\n"
        "for event path filters, so a `paths:` trigger must repeat it literally —\n"
        "this guard exists so that repetition drifts LOUDLY instead of silently\n"
        "shrinking a gate's coverage.\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
