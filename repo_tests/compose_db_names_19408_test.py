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
from urllib.parse import urlsplit

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
    raw = _slm_environment(text).get("AUTOBOT_USERS_DATABASE_URL", "")
    if not raw:
        return ["AUTOBOT_USERS_DATABASE_URL is missing from the SLM service"]
    url = urlsplit(_resolve(raw, {}))
    faults = []
    if url.hostname != "autobot-postgres":
        faults.append(f"host is {url.hostname}")
    if url.username != "autobot":
        faults.append(f"role is {url.username}")
    if url.path != "/autobot_users":
        faults.append(f"database is {url.path}")
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
    [
        "- SLM_DATA_DIR=/app/data",
        "- AUTOBOT_USERS_DATABASE_URL=postgresql+asyncpg://slm_app:${P:?x}@127.0.0.1:5432/slm",
        "- AUTOBOT_USERS_DATABASE_URL=postgresql+asyncpg://autobot:${P:?x}@autobot-postgres:5432/wrong_autobot_users",
    ],
    ids=["missing", "loopback-and-wrong-database", "database-name-only-contains-it"],
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


def _resolve(value: str, env: dict[str, str]) -> str:
    """Compose's `${A:-default}`, `${A:+text}` and `${A:?error}`, innermost first; empty counts as unset.

    A `:?` variable resolves to a stand-in: these tests are about roles and databases.
    """
    inner = re.compile(r"\$\{([A-Z_]+):([-+?])([^${}]*)\}")

    def one(match: re.Match[str]) -> str:
        name, op, rest = match.groups()
        current = env.get(name, "")
        if op == "+":
            return rest if current else ""
        return current or ("required" if op == "?" else rest)

    while inner.search(value):
        value = inner.sub(one, value)
    return value


def _connection(env: dict[str, str]) -> dict[str, str]:
    """Role and database each container ends up with under *env*."""
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    pg = dict(item.split("=", 1) for item in services["autobot-postgres"]["environment"])
    slm = _slm_environment(COMPOSE.read_text(encoding="utf-8"))
    resolved = {
        "owner": _resolve(pg["POSTGRES_USER"], env),
        "slm_db": _resolve(pg["POSTGRES_DB"], env),
        "slm_url": _resolve(slm["SLM_DATABASE_URL"], env),
        "users_url": _resolve(slm["AUTOBOT_USERS_DATABASE_URL"], env),
    }
    for key in ("slm_url", "users_url"):
        url = urlsplit(resolved[key])
        assert url.hostname == "autobot-postgres", f"{key} did not resolve: {url.hostname}"
        resolved[key] = f"{url.username}{url.path}"
    return resolved


@pytest.mark.parametrize(
    ("env", "owner", "slm_db", "users_db"),
    [
        ({}, "autobot", "autobot_slm", "autobot_users"),
        ({"AUTOBOT_DB_USER": "old", "AUTOBOT_DB_NAME": "o_slm", "AUTOBOT_USERS_DB_NAME": "o_u"}, "old", "o_slm", "o_u"),
        ({"AUTOBOT_POSTGRES_USER": "new", "SLM_DB_NAME": "n_slm", "AUTOBOT_POSTGRES_DB": "n_u"}, "new", "n_slm", "n_u"),
        (
            {"AUTOBOT_DB_USER": "old", "AUTOBOT_POSTGRES_USER": "new", "AUTOBOT_DB_NAME": "o", "SLM_DB_NAME": "n"},
            "new",
            "n",
            "autobot_users",
        ),
    ],
    ids=["fresh", "old-names-carry-over", "canonical", "canonical-beats-old"],
)
def test_every_environment_keeps_the_slm_on_the_role_and_databases_compose_created(
    env: dict[str, str], owner: str, slm_db: str, users_db: str
) -> None:
    assert _connection(env) == {
        "owner": owner,
        "slm_db": slm_db,
        "slm_url": f"{owner}/{slm_db}",
        "users_url": f"{owner}/{users_db}",
    }


def test_the_resolver_handles_each_operator() -> None:
    assert _resolve("${A:-${B:-c}}", {"B": "b"}) == "b"
    assert _resolve("${A:+A }${B:+B}", {"A": "1"}) == "A "


def test_the_slm_does_not_read_a_role_compose_never_creates() -> None:
    plain = _connection({})
    assert _connection({"SLM_POSTGRES_USER": "slm_app"}) == plain


@pytest.mark.parametrize(
    ("env", "database"),
    [({}, "autobot_users"), ({"AUTOBOT_USERS_DB_NAME": "o_u"}, "o_u"), ({"AUTOBOT_POSTGRES_DB": "n_u"}, "n_u")],
    ids=["fresh", "old-name", "canonical"],
)
def test_the_database_the_slm_reads_is_the_one_postgres_is_told_to_create(env: dict[str, str], database: str) -> None:
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))["services"]
    pg = dict(item.split("=", 1) for item in services["autobot-postgres"]["environment"])
    assert _resolve(pg["AUTOBOT_POSTGRES_DB"], env) == database
    script = (REPO_ROOT / "docker" / "postgres" / "init-databases.sh").read_text(encoding="utf-8")
    assert 'users_db="${AUTOBOT_POSTGRES_DB:?' in script and 'CREATE DATABASE :"users_db";' in script
