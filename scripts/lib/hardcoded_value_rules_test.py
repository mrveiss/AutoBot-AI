# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The union proof for scripts/lib/hardcoded-value-rules.sh (#14371).

Three detectors implemented "find hardcoded values", each with rules the other
two did not have. Merging them is only correct if EVERY rule survived, and
"I read all three carefully" is not evidence. So this file:

* names each of the three former detectors and, for each, a rule that ONLY it
  had — and asserts the merged rule set fires on it. A merge that quietly
  dropped a fork's contribution fails here, by name;
* asserts every registered rule has a fixture that trips it, so a rule cannot
  be added to ``HV_RULES`` and left unexercised;
* asserts every such fixture also survives ``hv_prefilter_pattern``. The
  prefilter is what makes a whole-tree scan affordable, and a rule missing from
  it is a rule that never fires on a tree scan — silently, and only there. A
  test that only called ``hv_scan_line`` would report full coverage over that;
* asserts each rule's negative fixture stays clean, so the merge did not buy
  coverage with false positives.

Fixture strings are assembled from fragments where they would otherwise look
like a real credential or fleet address to an unrelated scanner walking test
sources.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parent / "hardcoded-value-rules.sh"

_FLEET_IP = ".".join(("172", "16", "168", "23"))
_ACCOUNT = "ka" + "li"


def _scan(line: str, filename: str = "autobot-backend/svc.py") -> str:
    """Run one line through the merged rule set; return the emitted records."""
    script = f'source "{LIB}"\nhv_scan_line "$1" 7 "$2"\n'
    result = subprocess.run(
        ["bash", "-c", script, "_", filename, line],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _survives_prefilter(line: str) -> bool:
    script = f'source "{LIB}"\nprintf "%s" "$1" | grep -qE "$(hv_prefilter_pattern)"\n'
    return subprocess.run(["bash", "-c", script, "_", line], capture_output=True).returncode == 0


def _registered_rules() -> list[str]:
    script = f'source "{LIB}"\nprintf "%s\\n" "${{HV_RULES[@]}}"\n'
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return [r for r in result.stdout.split() if r]


# rule name -> (a line that must trip it, a line that must not)
FIXTURES: dict[str, tuple[str, str]] = {
    "ip": (f'REDIS_HOST = "{_FLEET_IP}"', "REDIS_HOST = config.vm.redis"),
    "port": ('URL = "http://svc:8001/api"', "URL = f'http://svc:{config.port.backend}/api'"),
    "model": ('MODEL = "qwen3.5:9b"', "MODEL = DEFAULT_LLM_MODEL"),
    "path": ("BASE = \"/opt/autobot/data\"", "BASE = config.path.base_dir"),
    "dsn": ('DB = "sqlite:///./app.db"', "DB = os.environ['AUTOBOT_DB_URL']"),
    "url": ('ENDPOINT = "https://svc.invalid/v1"', "ENDPOINT = config.backend_url"),
    "account": (f"User={_ACCOUNT}", 'User="${AUTOBOT_SERVICE_USER}"'),
    "role": ('MSG = {"role": "user"}', "MSG = {'role': CategoryDefaults.ROLE_USER}"),
    "category": ('CAT = doc.get("category", "general")', "CAT = doc.get('category', CategoryDefaults.GENERAL)"),
    "timeout": ("resp = client.get(url, timeout=30)", "resp = client.get(url, timeout=config.timeout.http)"),
    "magic_number": ("limit = 10", "limit = QueryDefaults.DEFAULT_SEARCH_LIMIT"),
}

# The union claim, stated per former detector: a rule ONLY that fork had.
# If the merge lost a fork's contribution, the row naming it fails.
ONLY_IN_DETECTOR: dict[str, tuple[str, str, str]] = {
    "pipeline-scripts (CI tree scan)": (
        f"chown {_ACCOUNT}:{_ACCOUNT} /srv/app",
        "autobot-infrastructure/setup.sh",
        "account identity in a shell script — the CI scanner was the only one "
        "that scanned .sh at all, and the only one with the account rules",
    ),
    "autobot-infrastructure (dormant fork)": (
        'MODEL = "deepseek-coder:33b"',
        "autobot-backend/llm_router.py",
        "the GENERIC model-tag regex; the other two carried an explicit table "
        "that a newer model tag walks straight past",
    ),
    "pre-commit hook": (
        'CAT = doc.get("category", "general")',
        "autobot-backend/svc.py",
        "the `.get(field, default)` call-argument shape (#14005) — no keyword "
        "operator for the other two detectors' patterns to anchor on",
    ),
}


@pytest.mark.parametrize("rule", sorted(FIXTURES))
def test_every_registered_rule_has_a_fixture_that_trips_it(rule: str) -> None:
    positive, _ = FIXTURES[rule]
    assert _scan(positive), f"rule '{rule}' did not fire on its own positive fixture: {positive!r}"


@pytest.mark.parametrize("rule", sorted(FIXTURES))
def test_every_rule_fixture_survives_the_prefilter(rule: str) -> None:
    """A rule the tree-scan prefilter drops never fires on a tree scan."""
    positive, _ = FIXTURES[rule]
    assert _survives_prefilter(positive), (
        f"rule '{rule}' fires under hv_scan_line but its trigger is missing from "
        f"hv_prefilter_pattern, so a tree scan will never reach it: {positive!r}"
    )


@pytest.mark.parametrize("rule", sorted(FIXTURES))
def test_every_rule_has_a_clean_counterpart(rule: str) -> None:
    """Coverage bought with false positives is not coverage."""
    _, negative = FIXTURES[rule]
    assert _scan(negative) == "", f"rule '{rule}' fired on its SSOT-correct counterpart: {negative!r}"


def test_the_registry_and_the_fixtures_match_exactly() -> None:
    """A rule added to HV_RULES without a fixture is an unexercised rule."""
    registered = set(_registered_rules())
    assert registered, "HV_RULES parsed empty — the guard checked nothing"
    assert registered == set(FIXTURES), (
        f"registered but unexercised: {sorted(registered - set(FIXTURES))}; "
        f"exercised but unregistered: {sorted(set(FIXTURES) - registered)}"
    )


@pytest.mark.parametrize("detector", sorted(ONLY_IN_DETECTOR))
def test_each_former_detectors_unique_contribution_survived(detector: str) -> None:
    line, filename, why = ONLY_IN_DETECTOR[detector]
    assert _scan(line, filename), (
        f"the merged rule set lost {detector}'s contribution — {why}. "
        f"Nothing fired on {line!r} in {filename}."
    )


def test_a_comment_and_a_noqa_are_both_honoured() -> None:
    assert _scan(f'# host = "{_FLEET_IP}"') == ""
    assert _scan(f'HOST = "{_FLEET_IP}"  # noqa') == ""


def test_yaml_and_shell_are_in_scope_and_markdown_is_not() -> None:
    """#14316's extension widening is part of the merged scope, not lost to it."""
    # `; done` leaves the loop's status as the LAST iteration's, which is 1
    # whenever the last path is out of scope — an exit code that says nothing
    # about the answer. The answer is the printed set.
    script = f'source "{LIB}"\nfor f in "$@"; do hv_file_in_scope "$f" && echo "$f"; done\ntrue\n'
    result = subprocess.run(
        [
            "bash", "-c", script, "_",
            "autobot-infrastructure/deploy.yml", "autobot-infrastructure/setup.sh",
            "autobot-backend/api.py", "autobot-frontend/src/App.vue",
            "docs/README.md", "autobot-backend/api_test.py",
            "autobot_shared/ssot_config.py", "autobot-frontend/src/types/generated/api.ts",
        ],
        capture_output=True, text=True,
    )
    in_scope = set(result.stdout.split())
    assert in_scope == {
        "autobot-infrastructure/deploy.yml",
        "autobot-infrastructure/setup.sh",
        "autobot-backend/api.py",
        "autobot-frontend/src/App.vue",
    }, in_scope


def test_the_severity_distinction_survived() -> None:
    """offset=0 is a WARNING, not a VIOLATION — a rule in its own right."""
    assert _scan("offset = 0").startswith("WARNING|")
    assert _scan("limit = 10").startswith("VIOLATION|")
