# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Compose database variables use the per-concept names, and old values carry over (#19408, #19406).

The owner decision on #19408: ``AUTOBOT_POSTGRES_DB``, ``AUTOBOT_POSTGRES_USER``, ``SLM_POSTGRES_USER``
and ``SLM_DB_NAME`` are canonical, and the old compose names keep working for one release, so no
container connects to a different database or role. #19406: the SLM needs its own URL for
``autobot_users``, or it falls back to loopback and a role compose never creates.
"""

from __future__ import annotations

import re

import pytest
import yaml
from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
COMPOSE = REPO_ROOT / "docker-compose.yml"
LEGACY = ("AUTOBOT_DB_USER", "AUTOBOT_DB_NAME", "AUTOBOT_USERS_DB_NAME")
#: The one spelling each legacy name may appear in: the tail of a canonical chain.
ALIAS_OF = {
    "AUTOBOT_DB_USER": r"\$\{AUTOBOT_POSTGRES_USER:-\$\{AUTOBOT_DB_USER:-autobot\}\}",
    "AUTOBOT_DB_NAME": r"\$\{SLM_DB_NAME:-\$\{AUTOBOT_DB_NAME:-autobot_slm\}\}",
    "AUTOBOT_USERS_DB_NAME": r"\$\{AUTOBOT_POSTGRES_DB:-\$\{AUTOBOT_USERS_DB_NAME:-autobot_users\}\}",
}


def _slm_environment(text: str) -> dict[str, str]:
    service = yaml.safe_load(text)["services"]["autobot-slm"]
    return dict(item.split("=", 1) for item in service["environment"] if "=" in item)


def _users_url_faults(text: str) -> list[str]:
    url = _slm_environment(text).get("AUTOBOT_USERS_DATABASE_URL", "")
    if not url:
        return ["AUTOBOT_USERS_DATABASE_URL is missing from the SLM service"]
    faults = []
    if "@autobot-postgres:5432/" not in url:
        faults.append("does not point at autobot-postgres")
    if "autobot_users" not in url or "${SLM_POSTGRES_USER:-" not in url:
        faults.append("is not the SLM role on the autobot_users database")
    return faults


def _bare_legacy_uses(text: str) -> list[str]:
    """Legacy names used outside their alias chain; the deprecation report line is their other home."""
    lines = [line for line in text.splitlines() if "AUTOBOT_COMPOSE_LEGACY_DB_VARS" not in line]
    lines = [line for line in lines if not line.lstrip().startswith("#")]
    body = "\n".join(lines)
    found = []
    for name, chain in ALIAS_OF.items():
        if name in re.sub(chain, "", body):
            found.append(name)
    return found


def test_the_compose_slm_gets_a_working_users_database_url() -> None:
    assert _users_url_faults(COMPOSE.read_text(encoding="utf-8")) == []


@pytest.mark.parametrize(
    "environment",
    ["- SLM_DATA_DIR=/app/data", "- AUTOBOT_USERS_DATABASE_URL=postgresql+asyncpg://slm_app:x@127.0.0.1:5432/slm"],
    ids=["missing", "loopback-and-wrong-database"],
)
def test_a_missing_or_wrong_users_url_is_flagged(environment: str) -> None:
    text = f"services:\n  autobot-slm:\n    environment:\n      {environment}\n"
    assert _users_url_faults(text)


def test_a_legacy_name_appears_only_as_the_tail_of_its_canonical_chain() -> None:
    assert _bare_legacy_uses(COMPOSE.read_text(encoding="utf-8")) == []


def test_a_bare_legacy_use_is_flagged_and_a_chain_is_not() -> None:
    assert _bare_legacy_uses("- POSTGRES_USER=${AUTOBOT_DB_USER:-autobot}\n") == ["AUTOBOT_DB_USER"]
    assert _bare_legacy_uses("- X=${AUTOBOT_POSTGRES_USER:-${AUTOBOT_DB_USER:-autobot}}\n") == []


def test_every_legacy_name_is_reported_to_the_slm_for_its_warning() -> None:
    report = _slm_environment(COMPOSE.read_text(encoding="utf-8"))["AUTOBOT_COMPOSE_LEGACY_DB_VARS"]
    assert all(f"${{{name}:+{name}" in report for name in LEGACY), report


def test_the_shipped_env_file_sets_no_name_that_would_outrank_an_operator_alias() -> None:
    """`.env.docker` setting a canonical name would beat an operator's old name and move the connection."""
    text = (REPO_ROOT / "docker" / ".env.docker").read_text(encoding="utf-8")
    assigned = {line.split("=", 1)[0] for line in text.splitlines() if re.match(r"[A-Z_]+=", line)}
    assert not assigned & {*LEGACY, "AUTOBOT_POSTGRES_USER", "AUTOBOT_POSTGRES_DB", "SLM_POSTGRES_USER", "SLM_DB_NAME"}
