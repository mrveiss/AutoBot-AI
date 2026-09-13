#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15309 — a watchdog scheduled nowhere and a watchdog that ran and found
nothing are indistinguishable from the outside. Both self-hosted runners had
no watchdog: the only entry that scheduled ``scripts/runner-watchdog.sh`` was
an untracked cron line on a host that no longer ran a runner, and its log
redirect was unwritable there anyway — so the gap produced zero signal for
months.

This module cannot observe a live host (no CI job here can SSH to the runner
fleet, and even a self-hosted job checking itself proves nothing about the
*other* runner). What it CAN verify from the repo is the half that must stay
true for the host-side schedule to even be installable:

- ``scripts/runner-watchdog-inventory.yaml`` (the SSOT for which runners are
  expected to have the watchdog scheduled) lists at least one runner — a
  "reach floor" (see ``check_mcp_tool_permission_coverage.py`` for the same
  pattern): an inventory silently emptied by a bad edit must fail loudly, not
  read as "nothing to check".
- Every inventory entry has a non-empty ``name`` and ``service``, and the
  ``service`` matches GitHub's own runner-installer naming convention for
  that ``name`` (``actions.runner.<owner>-<repo>.<name>.service``) — the
  literal-drifted-from-reality shape that made fault #2 of #15309 possible.
- The systemd templates the inventory's own doc points operators at
  (``scripts/systemd/runner-watchdog@.service`` /
  ``.timer``) exist and are tracked, so "install the watchdog" has something
  concrete to install rather than a description of what someone should write.
- No inventory entry's ``verified`` date has gone stale past
  ``max_verified_age_days`` — the SSOT is only trustworthy if someone keeps
  re-confirming it against ``gh api repos/:owner/:repo/actions/runners``, and
  a doc nobody revisits is exactly how fault #2 happened the first time.

WHY A REQUIRED CHECK AND NOT ONLY A TEST. The direction of failure here is
the same as every other audit `code-quality.yml` runs with `--audit`: an
inventory entry silently deleted, or a `verified` date nobody bumps, makes
this scan find FEWER problems, not more — it goes greener by doing nothing.
`repo_tests/runner_watchdog_schedule_test.py` imports these functions rather
than restating the rule (same shape as `code_quality_guard_reach_test.py`).

What this module cannot do, and does not claim to: prove the watchdog is
actually running on a given host, or that today's inventory still matches
`gh api .../actions/runners`. Those are host-observable facts; the staleness
floor is the mechanism that forces a human back to that command periodically
rather than letting the check quietly cover for a fact GitHub already
contradicts.
"""

from __future__ import annotations

import argparse
import datetime
import logging
import pathlib
import re
import sys

import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

logger = logging.getLogger(__name__)

#: Repo-relative path of this checker, quoted in the messages that ask for an edit.
SELF_REL = "tools/lint/check_runner_watchdog_schedule.py"

INVENTORY_PATH = _REPO_ROOT / "scripts" / "runner-watchdog-inventory.yaml"
SERVICE_TEMPLATE_PATH = _REPO_ROOT / "scripts" / "systemd" / "runner-watchdog@.service"
TIMER_TEMPLATE_PATH = _REPO_ROOT / "scripts" / "systemd" / "runner-watchdog@.timer"

#: At least one runner must be listed, or the whole audit asserts nothing
#: (#15309's own reach-floor requirement). Both currently-registered runners
#: (Little-Slave, Second-Little-Slave) are listed today, so 1 is a floor, not
#: a target -- raise it if the fleet grows and this should track headcount.
INVENTORY_FLOOR = 1

#: Read by check_code_quality_guard_reach.py --audit (registered in
#: _GUARDED_CHECKERS there). This checker's real inputs are all UNDER
#: tools/lint/** or repo_tests/** except the inventory itself and the
#: systemd templates it verifies exist -- those three are the ones that
#: need their own filter entry, or a PR touching only one of them would
#: skip code-quality and this audit would never re-run on the exact
#: change it exists to catch (#14550/#14551's shape).
GUARD_INPUT_PATHS = (
    "scripts/runner-watchdog-inventory.yaml",
    "scripts/systemd/runner-watchdog@.service",
    "scripts/systemd/runner-watchdog@.timer",
)

#: actions.runner.<owner>-<repo-with-dashes>.<runner-name>.service -- the
#: naming convention GitHub's own runner installer uses, and the one
#: scripts/systemd/runner-watchdog@.service assumes when it derives
#: SERVICE_NAME from the instance name.
_SERVICE_NAME_RE = re.compile(r"^actions\.runner\.[A-Za-z0-9]+-[A-Za-z0-9-]+\.(?P<runner>[^.]+)\.service$")


def _rel(path: pathlib.Path) -> str:
    """repo-relative for messages when possible; falls back to the raw path
    for fixtures (tests) that legitimately live outside the repo tree."""
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def load_inventory(path: pathlib.Path = INVENTORY_PATH) -> dict:
    """Parse the inventory YAML. Raises on missing/unparseable file -- a
    missing SSOT is not "zero runners to check", it is a broken check."""
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not parse to a mapping")
    return data


def _check_templates(service_template: pathlib.Path, timer_template: pathlib.Path) -> list[str]:
    """Both systemd templates must exist -- an inventory entry is an
    instruction to install THESE files; missing either leaves "schedule the
    watchdog" with nothing concrete to run (#15309)."""
    problems: list[str] = []
    if not service_template.is_file():
        problems.append(
            f"{_rel(service_template)} is missing. The inventory tells an "
            "operator which runners need the watchdog scheduled; this template is what they "
            "install. Without it, 'schedule the watchdog' has nothing concrete to run (#15309)."
        )
    if not timer_template.is_file():
        problems.append(f"{_rel(timer_template)} is missing (see above; same requirement).")
    return problems


def _check_service_name(idx: int, name: str, service: object) -> list[str]:
    """The service string must both be a valid unit name AND name the SAME
    runner as its own entry -- the exact literal-drifted-from-reality shape
    that let #15309 fault #2 target a decommissioned runner unnoticed."""
    if not service or not isinstance(service, str):
        return [f"runners[{idx}] ('{name}'): missing or empty 'service'."]

    match = _SERVICE_NAME_RE.match(service)
    if not match:
        return [
            f"runners[{idx}] ('{name}'): service '{service}' does not match "
            "actions.runner.<owner>-<repo>.<runner-name>.service."
        ]
    if match.group("runner") != name:
        return [
            f"runners[{idx}]: service names runner '{match.group('runner')}' but the "
            f"entry's own name is '{name}' -- this is exactly the literal-drifted-from-"
            "reality shape that let #15309 fault #2 target a decommissioned runner unnoticed."
        ]
    return []


def _check_verified_date(
    idx: int, name: str, verified: object, max_age_days: int | None, today: datetime.date
) -> list[str]:
    """`verified` must be a real ISO date within `max_age_days` of today --
    the mechanism that forces periodic re-confirmation against `gh api
    .../actions/runners` rather than trusting a doc nobody revisits."""
    if not verified or not isinstance(verified, str):
        return [f"runners[{idx}] ('{name}'): missing or empty 'verified' date."]

    try:
        verified_date = datetime.date.fromisoformat(verified)
    except ValueError:
        return [f"runners[{idx}] ('{name}'): 'verified' is not an ISO date: '{verified}'."]

    if max_age_days is None:
        return []
    age = (today - verified_date).days
    if age <= max_age_days:
        return []
    return [
        f"runners[{idx}] ('{name}'): 'verified' is {age} days old, past the "
        f"{max_age_days}-day floor. Re-confirm against `gh api "
        "repos/:owner/:repo/actions/runners` and bump the date, or this entry "
        "may be describing a runner that no longer exists (#15309)."
    ]


def _check_entry(
    idx: int, entry: object, seen_names: set[str], max_age_days: int | None, today: datetime.date
) -> tuple[str | None, list[str]]:
    """Validate one inventory entry. Returns (name if counted, problems)."""
    if not isinstance(entry, dict):
        return None, [f"runners[{idx}] is not a mapping: {entry!r}"]

    name = entry.get("name")
    if not name or not isinstance(name, str):
        return None, [f"runners[{idx}]: missing or empty 'name'."]

    problems: list[str] = []
    if name in seen_names:
        problems.append(f"runners: duplicate entry for '{name}'.")

    problems.extend(_check_service_name(idx, name, entry.get("service")))
    problems.extend(_check_verified_date(idx, name, entry.get("verified"), max_age_days, today))
    return name, problems


def audit(
    inventory_path: pathlib.Path = INVENTORY_PATH,
    service_template: pathlib.Path = SERVICE_TEMPLATE_PATH,
    timer_template: pathlib.Path = TIMER_TEMPLATE_PATH,
    today: datetime.date | None = None,
) -> tuple[int, list[str]]:
    """Returns (runners reached, problems). Empty problems == pass."""
    problems = _check_templates(service_template, timer_template)
    today = today or datetime.date.today()

    try:
        data = load_inventory(inventory_path)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        problems.append(f"could not load {_rel(inventory_path)}: {exc}")
        return 0, problems

    runners = data.get("runners")
    if not isinstance(runners, list):
        problems.append(f"{_rel(inventory_path)}: 'runners' is missing or not a list.")
        return 0, problems

    max_age_days = data.get("max_verified_age_days")
    if not isinstance(max_age_days, int) or max_age_days <= 0:
        problems.append(
            f"{_rel(inventory_path)}: 'max_verified_age_days' must be a positive "
            "integer -- it is what forces periodic re-confirmation against "
            "`gh api repos/:owner/:repo/actions/runners` (#15309)."
        )
        max_age_days = None

    seen_names: set[str] = set()
    reached = 0
    for idx, entry in enumerate(runners):
        name, entry_problems = _check_entry(idx, entry, seen_names, max_age_days, today)
        problems.extend(entry_problems)
        if name:
            reached += 1
            seen_names.add(name)

    if reached < INVENTORY_FLOOR:
        problems.append(
            f"only {reached} runner(s) reached the inventory, below the floor of {INVENTORY_FLOOR}. "
            f"A scan of an emptied {_rel(inventory_path)} would otherwise pass "
            "having asserted nothing (#15309)."
        )

    return reached, problems


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="verify the runner-watchdog inventory and its systemd templates",
    )
    args = parser.parse_args(argv)

    if not args.audit:
        parser.error("nothing to do — pass --audit")

    reached, problems = audit()
    scope = f"{reached} runner(s) in the watchdog inventory"

    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nRunner watchdog schedule audit FAILED over %s (#15309).", scope)
        return 1
    logger.info("Runner watchdog schedule audit clean over %s (#15309).", scope)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
