# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18094: the users-DB DSNs resolve in one place (``user_management.config``).

``Settings.slm_users_database_url`` / ``autobot_users_database_url`` used to be literal
``os.getenv(URL, "<literal DSN>")``; they now take ``get_*_db_config().url``, so the
``*_POSTGRES_*`` parts are honoured when the URL var is unset. Pinned here: all four
env combinations for each setting, that ``config.py`` really sources both fields from the
resolver (importing ``config`` builds ``Settings()`` and writes key files, so it is read as
source, not imported), and that ``repr`` never shows the password.
"""

import ast
import importlib.util  # noqa: E402
from pathlib import Path

import pytest

# tests/ stubs the `user_management` package, so load the real module by file (the pattern
# other SLM tests use for stubbed packages).
_SPEC = importlib.util.spec_from_file_location(
    "user_management_config_under_test_18094", Path(__file__).resolve().parents[1] / "user_management" / "config.py"
)
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
DatabaseConfig, get_autobot_db_config, get_slm_db_config = (
    _mod.DatabaseConfig,
    _mod.get_autobot_db_config,
    _mod.get_slm_db_config,
)

_CONFIG_PY = Path(__file__).resolve().parent.parent / "config.py"

#: setting name -> (resolver, URL var, parts prefix, default database)
_CASES = {
    "slm_users_database_url": (get_slm_db_config, "SLM_USERS_DATABASE_URL", "SLM_POSTGRES", "slm_users"),
    "autobot_users_database_url": (
        get_autobot_db_config,
        "AUTOBOT_USERS_DATABASE_URL",
        "AUTOBOT_POSTGRES",
        "autobot_users",
    ),
}
_URL = "postgresql+asyncpg://urluser:urlpw@url-host:6000/url_db"  # pragma: allowlist secret


def _clear(monkeypatch: pytest.MonkeyPatch, url_var: str, prefix: str) -> None:
    for var in [url_var] + [f"{prefix}_{part}" for part in ("HOST", "PORT", "DB", "USER", "PASSWORD")]:
        monkeypatch.delenv(var, raising=False)


def _set_parts(monkeypatch: pytest.MonkeyPatch, prefix: str) -> str:
    for part, value in (("HOST", "parts-host"), ("PORT", "6543"), ("DB", "parts_db"), ("USER", "partsuser")):
        monkeypatch.setenv(f"{prefix}_{part}", value)
    monkeypatch.setenv(f"{prefix}_PASSWORD", "partspw")
    return "postgresql+asyncpg://partsuser:partspw@parts-host:6543/parts_db"  # pragma: allowlist secret


@pytest.mark.parametrize("setting", sorted(_CASES))
def test_no_env_gives_the_historic_literal_dsn(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    resolver, url_var, prefix, database = _CASES[setting]
    _clear(monkeypatch, url_var, prefix)
    assert resolver().url == f"postgresql+asyncpg://slm_app@127.0.0.1:5432/{database}"


@pytest.mark.parametrize("setting", sorted(_CASES))
def test_url_only_is_used_verbatim(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    resolver, url_var, prefix, _ = _CASES[setting]
    _clear(monkeypatch, url_var, prefix)
    monkeypatch.setenv(url_var, _URL)
    assert resolver().url == _URL


@pytest.mark.parametrize("setting", sorted(_CASES))
def test_parts_only_build_the_dsn(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    resolver, url_var, prefix, _ = _CASES[setting]
    _clear(monkeypatch, url_var, prefix)
    expected = _set_parts(monkeypatch, prefix)
    assert resolver().url == expected


@pytest.mark.parametrize("setting", sorted(_CASES))
def test_url_wins_over_parts(monkeypatch: pytest.MonkeyPatch, setting: str) -> None:
    resolver, url_var, prefix, _ = _CASES[setting]
    _clear(monkeypatch, url_var, prefix)
    _set_parts(monkeypatch, prefix)
    monkeypatch.setenv(url_var, _URL)
    assert resolver().url == _URL


@pytest.mark.parametrize("setting", sorted(_CASES))
def test_settings_field_is_sourced_from_the_resolver(setting: str) -> None:
    resolver = _CASES[setting][0].__name__
    tree = ast.parse(_CONFIG_PY.read_text(encoding="utf-8"))
    values = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name) and n.target.id == setting
    ]
    assert len(values) == 1, f"{setting} not declared exactly once in config.py"
    value = values[0]
    assert isinstance(value, ast.Attribute) and value.attr == "url"
    assert isinstance(value.value, ast.Call) and value.value.func.id == resolver


def test_database_config_repr_does_not_expose_the_password() -> None:
    config = DatabaseConfig(url="postgresql+asyncpg://slm_app:s3cr3t-pw@127.0.0.1:5432/slm_users")
    for rendered in (repr(config), str(config)):
        assert "s3cr3t-pw" not in rendered
        assert "127.0.0.1:5432/slm_users" in rendered


# --- #19320: the SLM's role on the user-management DB is SLM_POSTGRES_USER -----------------------


def _clear_roles(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("AUTOBOT_USERS_DATABASE_URL", "SLM_POSTGRES_USER", "AUTOBOT_POSTGRES_USER"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(_mod, "_WARNED", set())


def test_slm_role_on_users_db_reads_the_canonical_slm_var(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_roles(monkeypatch)
    monkeypatch.setenv("SLM_POSTGRES_USER", "slm_role")
    monkeypatch.setenv("AUTOBOT_POSTGRES_USER", "backend_role")
    assert get_autobot_db_config().url.startswith("postgresql+asyncpg://slm_role@")


def test_slm_role_on_users_db_honours_the_deprecated_alias(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_roles(monkeypatch)
    monkeypatch.setenv("AUTOBOT_POSTGRES_USER", "legacy_role")
    with caplog.at_level("WARNING"):
        assert get_autobot_db_config().url.startswith("postgresql+asyncpg://legacy_role@")
    assert "deprecated" in caplog.text


def test_a_role_conflict_warns_once_and_names_no_value(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_roles(monkeypatch)
    monkeypatch.setenv("SLM_POSTGRES_USER", "slm_app")
    monkeypatch.setenv("AUTOBOT_POSTGRES_USER", "autobot_app")
    with caplog.at_level("WARNING"):
        urls = [get_autobot_db_config().url for _ in range(3)]
    assert all(u.startswith("postgresql+asyncpg://slm_app@") for u in urls)
    conflicts = [r for r in caplog.records if "differ" in r.getMessage()]
    assert len(conflicts) == 1
    assert "slm_app" not in conflicts[0].getMessage() and "autobot_app" not in conflicts[0].getMessage()


def test_the_deprecation_warning_fires_once_per_process(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_roles(monkeypatch)
    monkeypatch.setenv("AUTOBOT_POSTGRES_USER", "legacy_role")
    with caplog.at_level("WARNING"):
        for _ in range(3):
            get_autobot_db_config()
    assert len([r for r in caplog.records if "deprecated" in r.getMessage()]) == 1


@pytest.mark.parametrize(("legacy", "expected"), [("legacy_role", "legacy_role"), (None, "slm_app")])
def test_an_empty_canonical_role_falls_through(monkeypatch: pytest.MonkeyPatch, legacy, expected) -> None:
    _clear_roles(monkeypatch)
    monkeypatch.setenv("SLM_POSTGRES_USER", "")
    if legacy:
        monkeypatch.setenv("AUTOBOT_POSTGRES_USER", legacy)
    assert get_autobot_db_config().url.startswith(f"postgresql+asyncpg://{expected}@")


def test_compose_legacy_names_warn_once_and_list_each_name(monkeypatch, caplog) -> None:
    """#19408: compose reports the deprecated names; fleet hosts never set this variable."""
    caplog.set_level("WARNING")
    monkeypatch.setattr(_mod, "_WARNED", set())
    monkeypatch.setenv("AUTOBOT_USERS_DATABASE_URL", "postgresql+asyncpg://h:5432/d")
    monkeypatch.setenv("AUTOBOT_COMPOSE_LEGACY_DB_VARS", "AUTOBOT_DB_USER AUTOBOT_DB_NAME ")
    _mod.get_autobot_db_config()
    _mod.get_autobot_db_config()
    warnings = [r.getMessage() for r in caplog.records if "Deprecated compose" in r.getMessage()]
    assert len(warnings) == 1 and "AUTOBOT_DB_USER, AUTOBOT_DB_NAME" in warnings[0]


def test_no_compose_report_means_no_warning(monkeypatch, caplog) -> None:
    monkeypatch.setattr(_mod, "_WARNED", set())
    monkeypatch.setenv("AUTOBOT_USERS_DATABASE_URL", "postgresql+asyncpg://h:5432/d")
    monkeypatch.delenv("AUTOBOT_COMPOSE_LEGACY_DB_VARS", raising=False)
    _mod.get_autobot_db_config()
    assert not [r for r in caplog.records if "Deprecated compose" in r.getMessage()]
