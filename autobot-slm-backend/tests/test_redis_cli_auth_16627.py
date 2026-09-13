# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16627 / #16625: the SLM's replication and backup run ``redis-cli`` as the canonical
user with the canonical credential, sent on stdin rather than in any argv.
"""

import ast
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SLM = Path(__file__).resolve().parents[1]
_ROOT = _SLM.parent
sys.path.insert(0, str(_ROOT))

_spec = importlib.util.spec_from_file_location("_redis_cli_auth_16627", _SLM / "services" / "redis_cli_auth.py")
_mod = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
# @dataclass resolves the class's module through sys.modules, so register it first
# (same idiom as autobot-slm-backend/conftest.py).
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)  # type: ignore[union-attr]

#: A stand-in value; the point is only that it never shows up in a command string.
_SAMPLE = "stdin-only-sample-value"


@pytest.fixture
def canonical(monkeypatch):
    def _set(value, username=None):
        redis = SimpleNamespace(password=value, username=username)
        monkeypatch.setattr(_mod, "ssot_config", SimpleNamespace(redis=redis))

    return _set


def test_no_credential_means_plain_redis_cli(canonical):
    canonical(None)
    auth = _mod.redis_cli_auth()
    assert auth.stdin is None
    assert auth.remote("PING") == "redis-cli PING"


def test_the_credential_goes_on_stdin_and_never_into_the_command(canonical):
    canonical(_SAMPLE)
    auth = _mod.redis_cli_auth()
    remote = auth.remote("INFO replication")
    assert _SAMPLE not in remote
    assert auth.stdin == f"{_SAMPLE}\n".encode()
    assert remote.startswith("IFS= read -r REDISCLI_AUTH && export REDISCLI_AUTH && ")
    assert remote.endswith("redis-cli --user default INFO replication")


def test_one_read_serves_several_commands(canonical):
    canonical(_SAMPLE)
    remote = _mod.redis_cli_auth().remote("INFO keyspace", "DBSIZE")
    assert remote.count("read -r REDISCLI_AUTH") == 1
    assert remote.count("redis-cli --user default ") == 2


def test_the_configured_username_is_used_and_shell_quoted(canonical):
    canonical(_SAMPLE, "ops user")
    assert "redis-cli --user 'ops user' PING" in _mod.redis_cli_auth().remote("PING")


def test_an_explicit_value_wins_and_an_explicit_empty_one_means_no_auth(canonical):
    canonical("canonical-sample")
    assert _mod.redis_cli_auth(_SAMPLE).stdin == f"{_SAMPLE}\n".encode()
    assert _mod.redis_cli_auth("").stdin is None


# --- replication and backup no longer grep a config file or put it in argv -----------

_CALLERS = ["services/replication.py", "services/backup.py"]


def _string_parts(rel: str) -> list[str]:
    tree = ast.parse((_SLM / rel).read_text(encoding="utf-8"))
    return [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]


@pytest.mark.parametrize("rel", _CALLERS)
def test_the_config_file_grep_is_gone(rel):
    assert not any("grep -E '^requirepass'" in s for s in _string_parts(rel))


@pytest.mark.parametrize("rel", _CALLERS)
def test_no_command_carries_the_credential_as_an_env_assignment(rel):
    assert not any("REDISCLI_AUTH=" in s for s in _string_parts(rel)), "it must travel on stdin"


@pytest.mark.parametrize("rel", _CALLERS)
def test_both_build_their_redis_cli_commands_through_the_helper(rel):
    assert "redis_cli_auth(" in (_SLM / rel).read_text(encoding="utf-8")


def test_every_caller_uses_the_argument_free_canonical_lookup():
    for rel in ("services/replication.py", "api/stateful.py"):
        tree = ast.parse((_SLM / rel).read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_get_redis_password"
        ]
        assert calls, rel
        assert all(not c.args and not c.keywords for c in calls), f"{rel} still passes node arguments"
