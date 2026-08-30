# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15309 — exercises the exact functions ``code-quality`` calls
(``tools/lint/check_runner_watchdog_schedule.py --audit``) rather than
paraphrasing the rule. See that module's docstring for what it checks and why.
"""

from __future__ import annotations

import datetime
import importlib.util
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = REPO_ROOT / "tools" / "lint" / "check_runner_watchdog_schedule.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_runner_watchdog_schedule", _CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


# --------------------------------------------------------------------------
# The real, tracked inventory + templates must pass today
# --------------------------------------------------------------------------


def test_real_inventory_and_templates_pass_clean():
    reached, problems = checker.audit()
    assert problems == []
    assert reached >= checker.INVENTORY_FLOOR


def test_real_inventory_lists_both_currently_registered_runners():
    data = checker.load_inventory()
    names = {entry["name"] for entry in data["runners"]}
    # mrveiss confirmed both online via `gh api .../actions/runners` (#15309
    # comment, 2026-08-29). A rename or removal here without a matching
    # inventory update is exactly what the staleness floor exists to catch.
    assert {"Little-Slave", "Second-Little-Slave"} <= names


# --------------------------------------------------------------------------
# Reach floor: an emptied inventory must fail, not pass having asserted nothing
# --------------------------------------------------------------------------


def test_empty_runner_list_fails_the_reach_floor(tmp_path):
    inventory = tmp_path / "inv.yaml"
    inventory.write_text("runners: []\nmax_verified_age_days: 120\n", encoding="utf-8")

    reached, problems = checker.audit(inventory_path=inventory)

    assert reached == 0
    assert any("floor" in p for p in problems)


def test_missing_inventory_file_fails_rather_than_reads_as_zero_runners(tmp_path):
    missing = tmp_path / "does-not-exist.yaml"

    reached, problems = checker.audit(inventory_path=missing)

    assert reached == 0
    assert problems  # a missing SSOT is a failure, not "nothing to check"


def test_missing_systemd_templates_fail(tmp_path):
    reached, problems = checker.audit(
        service_template=tmp_path / "missing.service",
        timer_template=tmp_path / "missing.timer",
    )
    joined = "\n".join(problems)
    assert "missing.service" in joined
    assert "missing.timer" in joined


# --------------------------------------------------------------------------
# Service-name / runner-name drift (#15309 fault #2's exact shape)
# --------------------------------------------------------------------------


def test_service_name_naming_a_different_runner_than_the_entry_fails(tmp_path):
    inventory = tmp_path / "inv.yaml"
    inventory.write_text(
        textwrap.dedent("""
            max_verified_age_days: 120
            runners:
              - name: Little-Slave
                service: actions.runner.mrveiss-AutoBot-AI.MV-Stealth-VM.service
                verified: "2026-08-29"
            """),
        encoding="utf-8",
    )

    reached, problems = checker.audit(inventory_path=inventory, today=datetime.date(2026, 8, 30))

    assert reached == 1
    assert any("MV-Stealth-VM" in p and "Little-Slave" in p for p in problems)


def test_service_name_not_matching_the_installer_convention_fails(tmp_path):
    inventory = tmp_path / "inv.yaml"
    inventory.write_text(
        textwrap.dedent("""
            max_verified_age_days: 120
            runners:
              - name: Little-Slave
                service: not-a-systemd-unit-name
                verified: "2026-08-29"
            """),
        encoding="utf-8",
    )

    reached, problems = checker.audit(inventory_path=inventory, today=datetime.date(2026, 8, 30))

    assert any("does not match" in p for p in problems)


# --------------------------------------------------------------------------
# Staleness floor: an unrenewed verification date must fail
# --------------------------------------------------------------------------


def test_stale_verified_date_fails(tmp_path):
    inventory = tmp_path / "inv.yaml"
    inventory.write_text(
        textwrap.dedent("""
            max_verified_age_days: 30
            runners:
              - name: Little-Slave
                service: actions.runner.mrveiss-AutoBot-AI.Little-Slave.service
                verified: "2020-01-01"
            """),
        encoding="utf-8",
    )

    reached, problems = checker.audit(inventory_path=inventory, today=datetime.date(2026, 8, 30))

    assert any("days old" in p for p in problems)


def test_verified_date_within_the_floor_passes(tmp_path):
    inventory = tmp_path / "inv.yaml"
    inventory.write_text(
        textwrap.dedent("""
            max_verified_age_days: 30
            runners:
              - name: Little-Slave
                service: actions.runner.mrveiss-AutoBot-AI.Little-Slave.service
                verified: "2026-08-15"
            """),
        encoding="utf-8",
    )

    reached, problems = checker.audit(inventory_path=inventory, today=datetime.date(2026, 8, 30))

    assert problems == []
    assert reached == 1


def test_duplicate_runner_names_fail(tmp_path):
    inventory = tmp_path / "inv.yaml"
    inventory.write_text(
        textwrap.dedent("""
            max_verified_age_days: 120
            runners:
              - name: Little-Slave
                service: actions.runner.mrveiss-AutoBot-AI.Little-Slave.service
                verified: "2026-08-29"
              - name: Little-Slave
                service: actions.runner.mrveiss-AutoBot-AI.Little-Slave.service
                verified: "2026-08-29"
            """),
        encoding="utf-8",
    )
    reached, problems = checker.audit(inventory_path=inventory, today=datetime.date(2026, 8, 30))
    assert any("duplicate" in p for p in problems)
