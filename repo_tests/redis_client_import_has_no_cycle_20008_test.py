# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Importing redis_client never imports redis_client back (#20008).

Three things closed the loop on the backend's path: RedisDbConfig's class-body defaults read the config
registry; get_logger built the config defaults, which read the embedding override from Redis, so the
import failed partway and the override read as unreadable; and get_logger's config load reached the
registry, which imported redis_client back. Each case runs in a fresh interpreter, because a module
imported earlier would hide the order under test.
"""

from __future__ import annotations

import subprocess
import sys

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_PROBE = """
import builtins, sys
sys.path[:0] = [{root!r}, {root!r} + "/autobot-backend"]
real = builtins.__import__
hits = []
def probe(name, globals=None, locals=None, fromlist=(), level=0):
    partial = sys.modules.get("autobot_shared.redis_client")
    if name == "autobot_shared.redis_client" and fromlist and partial and not hasattr(partial, "get_redis_client"):
        hits.append(globals.get("__name__") if globals else "?")
    return real(name, globals, locals, fromlist, level)
builtins.__import__ = probe
{body}
print("CYCLE_HITS", hits)
"""


def _hits(body: str) -> str:
    source = _PROBE.format(root=str(_ROOT), body=body)
    done = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True, timeout=180, cwd=_ROOT)
    assert done.returncode == 0, done.stderr[-1500:]
    return next(line for line in done.stdout.splitlines() if line.startswith("CYCLE_HITS"))


@pytest.mark.parametrize(
    "first", ["autobot_shared.redis_client", "constants", "config", "autobot_shared.embedding_model"]
)
def test_no_import_order_loops_back_into_redis_client(first: str) -> None:
    assert _hits(f"import {first}") == "CYCLE_HITS []"


def test_contrast_the_probe_sees_a_loop() -> None:
    planted = (
        "import types\n"
        "m = types.ModuleType('autobot_shared.redis_client'); sys.modules['autobot_shared.redis_client'] = m\n"
        "from autobot_shared.redis_client import get_redis_client\n"
    )
    done = subprocess.run(
        [
            sys.executable,
            "-c",
            _PROBE.format(root=str(_ROOT), body=f"try:\n    exec({planted!r})\nexcept ImportError:\n    pass"),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=_ROOT,
    )
    assert "CYCLE_HITS []" not in done.stdout and "CYCLE_HITS" in done.stdout, done.stdout + done.stderr[-500:]
