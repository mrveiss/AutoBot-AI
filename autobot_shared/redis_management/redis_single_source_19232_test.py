# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One source for Redis database numbers and one for the endpoint (#19232).

Before: ``AUTOBOT_REDIS_DB_KNOWLEDGE=9`` moved ``ssot_config.RedisConfig.db_knowledge``
readers and left the canonical client on DB 1; ``get_redis_url_for_db`` read the SSOT
host while the canonical client could resolve another tier. Here the override feeds the
one table and every reader follows it, and a URL names the client's host/port/db/auth.
"""

from __future__ import annotations

import json
import os
from urllib.parse import unquote, urlparse

import pytest

from autobot_shared.redis_management import endpoint as _endpoint
from autobot_shared.redis_management import types as _types
from autobot_shared.redis_management.config import RedisConfigLoader
from autobot_shared.redis_management.connection_manager import RedisConnectionManager
from autobot_shared.redis_management.database_names import database_number
from autobot_shared.redis_management.database_overrides import apply_overrides, override_problems

#: main moves to an undeclared number, knowledge onto main's vacated one.
_OVERRIDES = {"AUTOBOT_REDIS_DB_MAIN": "12", "AUTOBOT_REDIS_DB_KNOWLEDGE": "0"}
_ENV = ("REDIS_HOST", "AUTOBOT_REDIS_HOST", "REDIS_PORT", "AUTOBOT_REDIS_PORT", "REDIS_PASSWORD")
_ENV += ("AUTOBOT_REDIS_PASSWORD", "REDIS_USERNAME", "AUTOBOT_REDIS_USERNAME", "AUTOBOT_REDIS_TLS_ENABLED")


@pytest.fixture
def overridden(monkeypatch):
    """Rebuild THE table in place from the YAML plus ``_OVERRIDES``, as process start would."""
    monkeypatch.setattr(_types, "override_source", lambda: dict(_OVERRIDES))
    rebuilt = _types._build_database_mapping()
    saved = dict(_types.DATABASE_MAPPING)
    _types.DATABASE_MAPPING.clear()
    _types.DATABASE_MAPPING.update(rebuilt)
    yield
    _types.DATABASE_MAPPING.clear()
    _types.DATABASE_MAPPING.update(saved)


def _fresh_manager(monkeypatch) -> RedisConnectionManager:
    """A new canonical manager with no backend config manager (no network I/O at init)."""
    monkeypatch.setattr(_endpoint, "get_config_manager", lambda: None)
    RedisConnectionManager.reset_instance()
    return RedisConnectionManager()


@pytest.fixture
def manager(monkeypatch):
    yield _fresh_manager(monkeypatch)
    RedisConnectionManager.reset_instance()


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for name in _ENV:
        monkeypatch.delenv(name, raising=False)
    import autobot_shared.ssot_config as ssot_config

    ssot_config.get_config.cache_clear()
    yield
    ssot_config.get_config.cache_clear()


# --- name -> number ---------------------------------------------------------------


def test_the_override_moves_main_and_knowledge_and_their_aliases(overridden):
    assert (database_number("main"), database_number("knowledge")) == (12, 0)
    assert (database_number("memory"), database_number("facts")) == (12, 0), "aliases follow their target"


def test_the_canonical_client_follows_the_override(overridden, manager):
    assert manager.resolve_db_config("main").db == 12
    assert manager.resolve_db_config("knowledge").db == 0


def test_a_yaml_entry_takes_its_number_from_the_one_table(overridden):
    endpoint = {"host": "127.0.0.1", "port": 6379}
    assert RedisConfigLoader._parse_database_config("knowledge", {"db": 1}, endpoint).db == 0


def test_the_legacy_tasks_variable_still_moves_workflows():
    moved = apply_overrides(_types.DECLARED_DATABASES, {"AUTOBOT_REDIS_DB_TASKS": "12"})
    assert moved["workflows"] == 12


def test_an_override_that_merges_two_databases_is_refused_and_named():
    """AUTOBOT_REDIS_DB_TESTING=15 (an old overlay's value) is celery_results' DB."""
    source = {"AUTOBOT_REDIS_DB_TESTING": "15"}
    assert apply_overrides(_types.DECLARED_DATABASES, source)["testing"] == _types.DECLARED_DATABASES["testing"]
    assert override_problems(_types.DECLARED_DATABASES, source) == [
        "AUTOBOT_REDIS_DB_TESTING=15 collides with celery_results"
    ]


def test_a_non_numeric_override_is_refused():
    assert override_problems(_types.DECLARED_DATABASES, {"AUTOBOT_REDIS_DB_MAIN": "zero"}) == [
        "AUTOBOT_REDIS_DB_MAIN='zero' is not a Redis database number (0-15)"
    ]


# --- host / port / auth ------------------------------------------------------------


def _assert_url_matches_client(manager, database: str) -> None:
    from autobot_shared.ssot_config import get_config

    url = urlparse(get_config().get_redis_url_for_db(database_number(database)))
    client = manager.resolve_db_config(database)
    assert (url.hostname, url.port, url.path) == (client.host, client.port, f"/{client.db}")
    password = unquote(url.password) if url.password is not None else None
    assert (url.username or None, password) == (client.username, client.password)
    assert url.scheme == ("rediss" if client.ssl else "redis")


@pytest.fixture
def _reset_after():
    yield
    RedisConnectionManager.reset_instance()


def test_url_names_the_canonical_clients_host_when_the_tiers_disagree(monkeypatch, _reset_after):
    """NetworkConstants answers before the SSOT field; the URL used to skip straight to SSOT."""
    monkeypatch.setattr(_endpoint.NetworkConstants, "REDIS_VM_IP", "10.20.30.40", raising=False)
    monkeypatch.setenv("AUTOBOT_REDIS_PASSWORD", "p@ss")  # pragma: allowlist secret
    monkeypatch.setenv("AUTOBOT_REDIS_USERNAME", "svc")
    fresh = _fresh_manager(monkeypatch)
    assert fresh.resolve_db_config("knowledge").host == "10.20.30.40"
    for database in ("main", "knowledge", "celery_broker"):
        _assert_url_matches_client(fresh, database)


def test_url_and_client_agree_on_tls(monkeypatch, _reset_after):
    monkeypatch.setenv("AUTOBOT_REDIS_TLS_ENABLED", "true")
    monkeypatch.setenv("AUTOBOT_REDIS_TLS_PORT", "6390")
    fresh = _fresh_manager(monkeypatch)
    assert fresh.resolve_db_config("main").port == 6390
    _assert_url_matches_client(fresh, "main")


@pytest.fixture
def _bare_env(monkeypatch):
    """No config-manager tier and no Redis port/TLS env, so each test names exactly what it sets."""
    monkeypatch.setattr(_endpoint, "config_manager_redis", lambda: {})
    monkeypatch.setattr(_endpoint, "_warned_env_ports", set())
    for var in ("REDIS_PORT", "AUTOBOT_REDIS_PORT", "AUTOBOT_REDIS_TLS_ENABLED", "AUTOBOT_REDIS_TLS_PORT"):
        monkeypatch.delenv(var, raising=False)


@pytest.mark.parametrize("bad", ["abc", "0", "65536", "+6390", "63_90", "\u0666\u0663\u0669\u0660"])
def test_an_unusable_env_port_warns_and_the_next_tier_answers(bad, monkeypatch, caplog, _bare_env):
    """#19232 review: a bare int() raised for every client; a refused port now falls through."""
    monkeypatch.setenv("REDIS_PORT", bad)
    monkeypatch.setenv("AUTOBOT_REDIS_PORT", "6391")
    monkeypatch.setenv("AUTOBOT_REDIS_TLS_ENABLED", "false")
    assert _endpoint.resolve_redis_endpoint().port == 6391
    monkeypatch.delenv("AUTOBOT_REDIS_PORT")
    assert _endpoint.resolve_redis_endpoint().port == int(_endpoint.NetworkConstants.REDIS_PORT)
    assert sum("REDIS_PORT" in r.getMessage() for r in caplog.records) == 1, "warned once, not per client"


def test_tls_without_a_port_or_ssot_uses_the_registered_default(monkeypatch, caplog, _bare_env):
    """main defaulted to the TLS port; the shared resolver raised there instead."""
    from autobot_shared.env_registry import REGISTRY
    from autobot_shared.ssot_tls import TLSConfig

    monkeypatch.setenv("AUTOBOT_REDIS_TLS_ENABLED", "true")
    monkeypatch.setenv("AUTOBOT_REDIS_TLS_PORT", "not-a-port")
    monkeypatch.setattr(_endpoint, "_ssot", lambda ssot=None: None)
    endpoint = _endpoint.resolve_redis_endpoint()
    assert (endpoint.tls, endpoint.port) == (True, REGISTRY["AUTOBOT_REDIS_TLS_PORT"].default)
    assert REGISTRY["AUTOBOT_REDIS_TLS_PORT"].default == TLSConfig.model_fields["redis_tls_port"].default
    assert any("no SSOT config" in r.getMessage() for r in caplog.records)


def test_url_follows_a_moved_database(overridden, manager):
    _assert_url_matches_client(manager, "knowledge")
    _assert_url_matches_client(manager, "main")


def test_network_constants_database_numbers_follow_the_override(overridden):
    from autobot_shared.network_constants import DatabaseConstants

    assert (DatabaseConstants.MAIN_DB, DatabaseConstants.KNOWLEDGE_DB) == (12, 0)
    assert DatabaseConstants.TASKS_DB == database_number("workflows")


def test_the_number_table_and_the_tuning_loader_read_one_yaml(monkeypatch):
    """One resolver: the loader's default path is exactly the table's (#19232)."""
    monkeypatch.setattr(_types, "_yaml_candidates", lambda: ["/nonexistent/redis-databases.yaml"])
    assert _types.resolve_databases_yaml() is None
    assert RedisConfigLoader._resolve_yaml_path(None) is None


def _inventory_module():
    """The standalone Ansible inventory script, loaded by path (it is not a package)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "autobot-slm-backend/ansible/inventory/dynamic/generate_inventory.py"
    spec = importlib.util.spec_from_file_location("_inventory_19232", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _shell_answers(overrides: dict) -> dict:
    """ssot-config.sh's autobot_redis_db for every declared database, under *overrides*."""
    import shutil
    import subprocess  # nosec B404  # fixed argv, no shell string from input
    from pathlib import Path

    bash = shutil.which("bash")
    assert bash, "bash is required to check the shell SSOT library"
    lib = Path(__file__).resolve().parents[2] / "autobot-infrastructure/shared/scripts/lib/ssot-config.sh"
    names = " ".join(_types.DECLARED_DATABASES)
    script = f'source "{lib}"; for n in {names}; do printf "%s=%s\\n" "$n" "$(autobot_redis_db "$n" 2>/dev/null)"; done'
    env = {"PATH": "/usr/bin:/bin", "PROJECT_ROOT": str(lib.parents[4]), **overrides}
    out = subprocess.run([bash, "-c", script], env=env, capture_output=True, text=True, check=True).stdout  # nosec B603
    return dict(line.split("=", 1) for line in out.splitlines())


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"AUTOBOT_REDIS_DB_KNOWLEDGE": "12"},
        {"AUTOBOT_REDIS_DB_MAIN": "12", "AUTOBOT_REDIS_DB_KNOWLEDGE": "0"},
        {"AUTOBOT_REDIS_DB_TASKS": "12"},
        {"AUTOBOT_REDIS_DB_TESTING": "15"},  # collides with celery_results: refused
        {"AUTOBOT_REDIS_DB_MAIN": "zero"},  # not a number: refused
        {"AUTOBOT_REDIS_DB_MAIN": "9", "AUTOBOT_REDIS_DB_TEMP": "9"},  # both refused
        {"AUTOBOT_REDIS_DB_MAIN": " 12 "},  # trimmed: accepted
        {"AUTOBOT_REDIS_DB_MAIN": "012"},  # leading zero: 12
        {"AUTOBOT_REDIS_DB_MAIN": "+12"},  # sign: refused
        {"AUTOBOT_REDIS_DB_MAIN": "16"},  # above 0..15: refused
        {"AUTOBOT_REDIS_DB_MAIN": "-1"},  # negative: refused
        {"AUTOBOT_REDIS_DB_MAIN": "18446744073709551616"},  # wraps to 0 in bash arithmetic: refused
        {"AUTOBOT_REDIS_DB_MAIN": "18446744073709551617"},  # wraps to 1: refused
        {"AUTOBOT_REDIS_DB_MAIN": "0000000000000000000007"},  # long zero padding: 7
        {"AUTOBOT_REDIS_DB_MAIN": "1_2"},  # int() would take it: refused
        {"AUTOBOT_REDIS_DB_MAIN": "\u0661\u0662"},  # non-ASCII digits: refused
        {"AUTOBOT_REDIS_DB_MAIN": ""},  # blank: no request, so no refusal either
        {"AUTOBOT_REDIS_DB_MAIN": "  "},  # whitespace only: no request
        {"AUTOBOT_REDIS_DB_WORKFLOWS": "", "AUTOBOT_REDIS_DB_TASKS": "12"},  # blank main name: legacy moves it
        {"AUTOBOT_REDIS_DB_WORKFLOWS": " ", "AUTOBOT_REDIS_DB_TASKS": "12"},
        {"AUTOBOT_REDIS_DB_TASKS": ""},  # blank legacy: no request
    ],
)
def test_python_shell_and_inventory_agree(overrides, monkeypatch):
    """One override contract, three readers: apply_overrides, ssot-config.sh, the Ansible inventory."""
    expected = {n: str(v) for n, v in apply_overrides(_types.DECLARED_DATABASES, overrides).items()}
    assert _shell_answers(overrides) == expected
    for var in [k for k in os.environ if k.startswith("AUTOBOT_REDIS_DB_")]:
        monkeypatch.delenv(var)
    for var, value in overrides.items():
        monkeypatch.setenv(var, value)
    inventory = {n: str(v) for n, v in _inventory_module().resolved_databases().items()}
    assert inventory == expected


def test_the_three_readers_share_one_upper_bound():
    from pathlib import Path

    from autobot_shared.redis_management.database_overrides import MAX_DATABASE_INDEX

    lib = Path(__file__).resolve().parents[2] / "autobot-infrastructure/shared/scripts/lib/ssot-config.sh"
    assert f"_AUTOBOT_REDIS_MAX_DB={MAX_DATABASE_INDEX}" in lib.read_text(encoding="utf-8")
    assert _inventory_module()._MAX_DATABASE_INDEX == MAX_DATABASE_INDEX


_NO_PROJECT_ROOT_PROBE = """
import builtins, os, sys
import autobot_shared.paths as paths
# ssot_config/ssot_tls resolve PROJECT_ROOT at their own import (outside redis_management, and
# raising there is theirs to fix); load them first so only redis_management's resolution is probed.
import autobot_shared.ssot_config  # noqa: F401

def _undeterminable():
    raise paths.ProjectRootUndeterminable("simulated: no project root")

paths.project_root = _undeterminable
os.environ.pop("AUTOBOT_BASE_DIR", None)
APP_YAML = "/app/config/redis-databases.yaml"
real_exists, real_open = os.path.exists, builtins.open

def _exists(path):
    path = os.path.normpath(str(path))
    if path == APP_YAML:
        return True
    if path.endswith("autobot-infrastructure/shared/config/redis-databases.yaml"):
        return False  # only the container copy is present
    return real_exists(path)

def _open(path, *args, **kwargs):
    return real_open(sys.argv[1] if os.path.normpath(str(path)) == APP_YAML else path, *args, **kwargs)

os.path.exists, builtins.open = _exists, _open
import autobot_shared.redis_management  # must not raise
from autobot_shared.redis_management import types
print(types.resolve_databases_yaml())
print(types.DECLARED_DATABASES["knowledge"])
"""


def test_import_survives_an_undeterminable_project_root_and_finds_app_config():
    """#19232 / #19350 review: path resolution never fails the import, and /app/config is found."""
    import subprocess  # nosec B404  # fixed argv
    import sys
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    real_yaml = repo / "autobot-infrastructure/shared/config/redis-databases.yaml"
    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(repo)}
    result = subprocess.run(  # nosec B603
        [sys.executable, "-c", _NO_PROJECT_ROOT_PROBE, str(real_yaml)],
        env=env,
        cwd="/",
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.split() == ["/app/config/redis-databases.yaml", "1"]


def test_the_standalone_ansible_inventory_fails_closed_without_the_yaml(monkeypatch, capsys):
    """No YAML: Redis is never queried with a guessed number, and the static fallback still answers."""
    module = _inventory_module()
    monkeypatch.setattr(module, "_DATABASES_YAML", module._DATABASES_YAML.with_name("absent.yaml"))
    with pytest.raises(module.DatabasesUnreadable):
        module.resolved_databases()

    def _never_dialled(**kwargs):
        raise AssertionError(f"Redis dialled without a database table: {kwargs}")

    monkeypatch.setattr(module.redis, "Redis", _never_dialled)
    inventory = module.AutoBotInventory()  # constructing it must not exit (#19232 review)
    assert json.loads(inventory.list_inventory()) == inventory.build_fallback_inventory()
    assert "cannot read Redis databases" in capsys.readouterr().err


def test_a_blank_override_is_no_request_and_no_warning():
    """``AUTOBOT_REDIS_DB_MAIN=`` in a .env is unset, not refused on every start (#19232 review)."""
    from autobot_shared.redis_management.database_overrides import override_problems

    blanks = {"AUTOBOT_REDIS_DB_MAIN": "", "AUTOBOT_REDIS_DB_KNOWLEDGE": "  ", "AUTOBOT_REDIS_DB_TASKS": ""}
    assert override_problems(_types.DECLARED_DATABASES, blanks) == []
