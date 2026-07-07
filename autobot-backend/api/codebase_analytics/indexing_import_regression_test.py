# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Regression test: indexing endpoint resolves clone path via source_paths (#11129).

Guards against the ImportError that occurred when _make_clone_path was removed
from endpoints/sources.py (Task-2 dedupe) but indexing.py still imported it from
there.  The fix imports make_clone_path from api.codebase_analytics.source_paths.
"""
import importlib
import sys
import types
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _install_light_stubs():
    """Insert the minimum sys.modules stubs needed so indexing.py can be
    imported without a running database / Redis / Ollama stack."""
    stubs = {}

    def _stub(name, **attrs):
        m = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules.setdefault(name, m)
        stubs[name] = sys.modules[name]
        return m

    # autobot_shared
    _stub("autobot_shared")
    _stub("autobot_shared.logging_manager", get_logger=lambda n: MagicMock())
    _stub("autobot_shared.security")
    _stub("autobot_shared.security.path_validator", validate_path=lambda p, **kw: p)

    # constants
    _stub("constants")
    _stub("constants.path_constants", PATH=MagicMock())

    return stubs


def _remove_stubs(stubs):
    for k in stubs:
        sys.modules.pop(k, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_make_clone_path_importable_from_source_paths():
    """Public helper must live in source_paths, not endpoints/sources."""
    from api.codebase_analytics.source_paths import make_clone_path  # noqa: PLC0415

    result = make_clone_path("abc123")
    assert result.endswith("abc123"), f"Unexpected path: {result}"
    assert "code-sources" in result


def test_indexing_module_imports_cleanly():
    """Importing the indexing endpoint module must not raise ImportError.

    Specifically guards that _make_clone_path is NOT referenced (it was deleted
    from endpoints/sources.py by the Task-2 dedupe refactor).
    """
    stubs = _install_light_stubs()
    try:
        # Force a fresh import (in case a prior test already loaded it)
        for key in list(sys.modules):
            if "codebase_analytics.endpoints.indexing" in key:
                del sys.modules[key]

        mod = importlib.import_module("api.codebase_analytics.endpoints.indexing")
        assert hasattr(mod, "_validate_and_get_path"), "Expected _validate_and_get_path in indexing module"
    finally:
        _remove_stubs(stubs)


@pytest.mark.asyncio
async def test_validate_and_get_path_sets_clone_path_via_make_clone_path(monkeypatch):
    """_validate_and_get_path fills in clone_path using make_clone_path when
    the source has no clone_path set yet (the no-clone_path branch, line ~117)."""
    stubs = _install_light_stubs()
    try:
        # Ensure a fresh import so monkeypatches apply cleanly
        for key in list(sys.modules):
            if "codebase_analytics.endpoints.indexing" in key:
                del sys.modules[key]

        from api.codebase_analytics.endpoints.indexing import (  # noqa: PLC0415
            IndexCodebaseRequest,
            _validate_and_get_path,
        )
        from api.codebase_analytics import source_paths  # noqa: PLC0415
        from api.codebase_analytics import source_storage  # noqa: PLC0415
        from api.codebase_analytics.source_models import CodeSource, SourceStatus  # noqa: PLC0415

        source = CodeSource(id="src-001", name="acme-site", repo="acme/site")
        assert source.clone_path is None  # precondition

        async def fake_get_source(sid):
            return source

        saved = {}

        async def fake_save(src):
            saved["src"] = src

        monkeypatch.setattr(source_storage, "get_source", fake_get_source)
        monkeypatch.setattr(source_storage, "save_source", fake_save)

        # The clone directory does not exist on disk → expect _SyncNeeded sentinel
        from api.codebase_analytics.endpoints.indexing import _SyncNeeded  # noqa: PLC0415

        req = IndexCodebaseRequest(source_id="src-001")
        result = await _validate_and_get_path(req)

        # clone_path must have been populated via make_clone_path (not the old private helper)
        assert source.clone_path is not None, "clone_path should be set after _validate_and_get_path"
        assert source.clone_path == source_paths.make_clone_path("src-001")
        assert source.status == SourceStatus.SYNCING
        assert isinstance(result, _SyncNeeded)
    finally:
        _remove_stubs(stubs)
