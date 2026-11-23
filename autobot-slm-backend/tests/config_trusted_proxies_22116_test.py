# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Comma-separated list env vars must reach Settings as lists (#22116).

Runs in a SUBPROCESS: the root conftest stubs ``config`` in sys.modules, and a
fresh interpreter also mirrors the real failure (``settings = Settings()`` at
import crashed the service).
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _BACKEND_ROOT.parent
CSV = "127.0.0.1,::1, 198.51.100.5 ,"
EXPECTED = ["127.0.0.1", "::1", "198.51.100.5"]
FIELDS = [("SLM_TRUSTED_PROXIES", "trusted_proxies"), ("SLM_CORS_ORIGINS", "cors_origins")]


def _load_settings(tmp_path: Path, env: dict) -> dict:
    """Import real config in a clean interpreter; return both list fields."""
    base = {k: v for k, v in os.environ.items() if k not in dict(FIELDS)}
    base.update(
        PYTHONPATH=os.pathsep.join([str(_REPO_ROOT), str(_BACKEND_ROOT)]),
        PYTHONDONTWRITEBYTECODE="1",
        SLM_DATA_DIR=str(tmp_path / "data"),
        SLM_CONFIG_DIR=str(tmp_path / "config"),
        **env,
    )
    code = (
        "import json, config; s = config.settings; "
        "print(json.dumps({'trusted_proxies': s.trusted_proxies, "
        "'cors_origins': s.cors_origins}))"
    )
    proc = subprocess.run([sys.executable, "-c", code], env=base, capture_output=True, text=True, cwd=tmp_path)
    assert proc.returncode == 0, proc.stderr[-1500:]
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.mark.parametrize("env,field", FIELDS)
def test_csv_env_parses_to_list(tmp_path, env, field):
    assert _load_settings(tmp_path, {env: CSV})[field] == EXPECTED


@pytest.mark.parametrize("env,field", FIELDS)
def test_json_array_env_still_accepted(tmp_path, env, field):
    value = json.dumps(["127.0.0.1", "::1"])
    assert _load_settings(tmp_path, {env: value})[field] == ["127.0.0.1", "::1"]


def test_unset_keeps_default(tmp_path):
    got = _load_settings(tmp_path, {})
    assert "127.0.0.1" in got["trusted_proxies"] and "::1" in got["trusted_proxies"]
    assert isinstance(got["cors_origins"], list) and got["cors_origins"]


@pytest.mark.parametrize("env,field", FIELDS)
def test_blank_env_keeps_the_default_not_an_empty_list(tmp_path, env, field):
    default = _load_settings(tmp_path, {})[field]
    assert _load_settings(tmp_path, {env: "  "})[field] == default != []


def test_bracketed_ipv6_is_split_as_csv_not_refused(tmp_path):
    got = _load_settings(tmp_path, {"SLM_TRUSTED_PROXIES": "[::1],198.51.100.5"})
    assert got["trusted_proxies"] == ["[::1]", "198.51.100.5"]
