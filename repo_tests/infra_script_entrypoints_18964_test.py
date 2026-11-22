# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The #18964 entry-point wrappers load by file path, and the KB dimension fix fails loudly (#19034 review).

- ``fix_kb_dimensions.py`` / ``utilities/fix_settings_loading.py`` import a sibling module; loaded by
  path from another directory with no PYTHONPATH, the sibling must still resolve.
- ``kb_dimension_utility.fix_dimensions`` holds no Redis client (the wipe is an approved proposal, #21383),
  and ``main`` turns a failure into a non-zero exit code.
"""

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import types

import pytest
from repo_tests._paths import repo_root

SCRIPTS = repo_root() / "autobot-infrastructure" / "shared" / "scripts"
_LOAD_BY_PATH = (
    "import importlib.util, sys; p = sys.argv[1]; "
    "s = importlib.util.spec_from_file_location('entry_under_test', p); "
    "m = importlib.util.module_from_spec(s); s.loader.exec_module(m); print('main' in vars(m))"
)


@pytest.mark.parametrize("rel", ["fix_kb_dimensions.py", "utilities/fix_settings_loading.py"])
def test_wrapper_loads_by_path_from_another_directory(rel, tmp_path):
    out = subprocess.run(
        [sys.executable, "-I", "-c", _LOAD_BY_PATH, str(SCRIPTS / rel)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr[-2000:]
    assert out.stdout.strip() == "True"


@pytest.fixture
def kb_dim(monkeypatch):
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        "kb_dimension_utility_under_test", SCRIPTS / "kb_dimension_utility.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_fix_never_touches_redis_and_initialises_the_kb_only(kb_dim, monkeypatch):
    """#21383: the destructive Redis cleanup moved to the approved wipe; the fix itself holds no Redis client."""
    assert not hasattr(kb_dim, "get_redis_client")

    async def no_kb():
        return None

    monkeypatch.setitem(sys.modules, "knowledge_factory", types.SimpleNamespace(get_knowledge_base_async=no_kb))
    with pytest.raises(RuntimeError, match="Knowledge base unavailable"):
        asyncio.run(kb_dim.fix_dimensions())


def test_main_exit_code_reflects_the_outcome(kb_dim, monkeypatch):
    async def bad():
        return False

    monkeypatch.setattr(kb_dim, "fix_dimensions", bad)
    assert kb_dim.main([]) == 1

    async def ok():
        return True

    monkeypatch.setattr(kb_dim, "fix_dimensions", ok)
    assert kb_dim.main([]) == 0


def test_request_wipe_flags_route_to_the_proposal_not_the_fix(kb_dim, monkeypatch):
    asked = []

    async def fake_request(dry_run):
        asked.append(dry_run)
        return True

    async def boom():
        raise AssertionError("the fix must not run for a wipe request")

    monkeypatch.setattr(kb_dim.kb_wipe_cli, "request_wipe", fake_request)
    monkeypatch.setattr(kb_dim, "fix_dimensions", boom)
    assert kb_dim.main(["--request-wipe"]) == 0
    assert kb_dim.main(["--dry-run"]) == 0
    assert asked == [False, True]
