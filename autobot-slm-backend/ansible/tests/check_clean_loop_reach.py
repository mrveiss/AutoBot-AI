#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The clean.yml loop guard must prove what it exercised (#15824).

`ansible-playbook` exits 0 when a play matches no hosts -- it prints
"Could not match supplied host pattern" and moves on. So does a play whose task
list is empty. A guard whose only signal is the exit status therefore reports
success for a run that tested nothing, which is indistinguishable from a run
that tested everything and found nothing wrong.

tests/playbooks/test_clean_yml_loops.yml writes one receipt per scenario naming
the host it templated, the role clean.yml files it ran, and whether the shared
wrong-node gate actually executed. This asserts a floor against those receipts.

The floor is bound to reach -- scenarios, hosts, role files, gate executed --
never to findings. "Found no problems" must never be able to satisfy it; only
"ran the scenarios" can.
"""

import json
import sys
from pathlib import Path

MIN_SCENARIOS = 2
MIN_HOSTS = 2
MIN_ROLE_CLEAN_RUNS = 7

_RECEIPT_GLOB = "clean-loop-reach-*.json"
_TRUE = {"true", "yes", "1"}


def _is_true(value: object) -> bool:
    """Ansible renders mapping values as strings; accept both shapes."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUE


def load_receipts(receipt_dir: Path) -> list[dict]:
    """Return every scenario receipt found, newest layout only."""
    if not receipt_dir.is_dir():
        raise SystemExit(
            f"NO RECEIPT DIRECTORY: {receipt_dir}\n"
            "  The playbook writes one receipt per scenario. No directory means the\n"
            "  playbook never ran, and an unrun guard must never report success."
        )

    receipts = []
    for path in sorted(receipt_dir.glob(_RECEIPT_GLOB)):
        receipts.append(json.loads(path.read_text(encoding="utf-8")))
    return receipts


def _scenario_problems(receipt: dict) -> list[str]:
    """Return every reach failure in one scenario receipt."""
    name = receipt.get("scenario", "<unnamed>")
    problems = []
    if not receipt.get("host"):
        problems.append(f"{name}: no host recorded -- the play matched nothing")
    if not receipt.get("roles_exercised"):
        problems.append(f"{name}: ran zero role clean.yml files")
    if not _is_true(receipt.get("gate_fact_observed")):
        problems.append(
            f"{name}: the shared wrong-node gate never ran -- " "clean_wrong_node_dir.yml set no fact on this host"
        )
    if not _is_true(receipt.get("inventory_sourced")):
        problems.append(
            f"{name}: role facts did not come from the inventory -- "
            "the play fell back to literals, so group_vars/all.yml was never exercised"
        )
    return problems


def check_floor(receipts: list[dict]) -> list[str]:
    """Return every floor violation across the whole run."""
    problems = []
    hosts = {r.get("host") for r in receipts if r.get("host")}
    role_runs = sum(len(r.get("roles_exercised") or []) for r in receipts)

    if len(receipts) < MIN_SCENARIOS:
        problems.append(f"scenarios run: {len(receipts)} < {MIN_SCENARIOS}")
    if len(hosts) < MIN_HOSTS:
        problems.append(f"distinct hosts templated: {len(hosts)} < {MIN_HOSTS}")
    if role_runs < MIN_ROLE_CLEAN_RUNS:
        problems.append(f"role clean.yml runs: {role_runs} < {MIN_ROLE_CLEAN_RUNS}")

    for receipt in receipts:
        problems.extend(_scenario_problems(receipt))
    return problems


def _report(receipts: list[dict]) -> None:
    """Print what each scenario reached."""
    for receipt in receipts:
        roles = receipt.get("roles_exercised") or []
        print(
            f"  {receipt.get('scenario', '<unnamed>')}: "
            f"host={receipt.get('host') or '<none>'} "
            f"roles={len(roles)} "
            f"gate_ran={_is_true(receipt.get('gate_fact_observed'))} "
            f"from_inventory={_is_true(receipt.get('inventory_sourced'))}"
        )


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} <receipt-directory>")

    receipts = load_receipts(Path(sys.argv[1]).resolve())
    print(f"clean.yml loop guard reach ({len(receipts)} scenario receipts):")
    _report(receipts)

    problems = check_floor(receipts)
    if problems:
        print("\nREACH FLOOR NOT MET -- this guard did not exercise enough to mean anything:")
        for problem in problems:
            print(f"  - {problem}")
        print(
            "\n  A green result here would say 'no wrong-node regression' on the strength\n"
            "  of scenarios that never ran (#15824)."
        )
        return 1

    print("\nOK: reach floor met.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
