# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#11820: GET /code-sync/status must surface deployed-vs-source drift for
co-located managed components (stale_components) so it never reads "up to date"
while a managed component is stale. Tests the _compute_stale_components helper:
detection, TTL caching, and defensive per-component isolation."""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

import ast  # noqa: E402
import types  # noqa: E402
from unittest.mock import MagicMock  # noqa: E402

# Same shims as test_sync_status_outdated_signal.py: stub the conflicting
# multipart package and swap benign dicts in for MagicMock schema names so
# api.code_sync imports under the conftest stub regime.
if "multipart" in sys.modules and not hasattr(sys.modules["multipart"], "multipart"):
    sys.modules.pop("multipart", None)
_mp_stub = types.ModuleType("multipart")
_mp_stub.multipart = types.ModuleType("multipart.multipart")  # type: ignore[attr-defined]
sys.modules.setdefault("multipart", _mp_stub)
sys.modules.setdefault("multipart.multipart", _mp_stub.multipart)  # type: ignore[attr-defined]

_code_sync_src = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
_SCHEMA_NAMES = tuple(
    sorted(
        alias.name
        for node in ast.walk(ast.parse(_code_sync_src))
        if isinstance(node, ast.ImportFrom) and node.module == "models.schemas"
        for alias in node.names
    )
)
_schemas_stub = sys.modules.get("models.schemas")
if isinstance(_schemas_stub, MagicMock):
    for _name in _SCHEMA_NAMES:
        setattr(_schemas_stub, _name, dict)


def _reset_cache(cs) -> None:
    cs._stale_components_cache["ts"] = -1.0e9
    cs._stale_components_cache["value"] = []


async def test_flags_only_drifted_deployed_components(monkeypatch, tmp_path):
    import api.code_sync as cs

    _reset_cache(cs)
    monkeypatch.setattr(cs, "ALLOWED_COMPONENTS", {"autobot-slm-backend", "autobot_shared"})
    monkeypatch.setattr(cs, "get_default_deployed_dir", lambda c: str(tmp_path))  # exists → checked
    monkeypatch.setattr(cs, "get_default_source_dir", lambda c: str(tmp_path))

    def fake_report(src, dep, comp):
        return {"drifted_files": ["x.py"] if comp == "autobot_shared" else [], "total_compared": 1}

    monkeypatch.setattr(cs, "build_drift_report", fake_report)

    assert await cs._compute_stale_components() == ["autobot_shared"]


async def test_skips_components_not_deployed_here(monkeypatch):
    import api.code_sync as cs

    _reset_cache(cs)
    monkeypatch.setattr(cs, "ALLOWED_COMPONENTS", {"autobot-backend"})
    monkeypatch.setattr(cs, "get_default_deployed_dir", lambda c: "/nonexistent/deployed/dir")

    def _boom(*_a, **_k):  # must never be called when the dir is absent
        raise AssertionError("build_drift_report called for a non-deployed component")

    monkeypatch.setattr(cs, "build_drift_report", _boom)

    assert await cs._compute_stale_components() == []


async def test_result_is_ttl_cached(monkeypatch, tmp_path):
    import api.code_sync as cs

    _reset_cache(cs)
    monkeypatch.setattr(cs, "ALLOWED_COMPONENTS", {"autobot_shared"})
    monkeypatch.setattr(cs, "get_default_deployed_dir", lambda c: str(tmp_path))
    monkeypatch.setattr(cs, "get_default_source_dir", lambda c: str(tmp_path))
    monkeypatch.setattr(cs, "build_drift_report", lambda *a: {"drifted_files": ["x"], "total_compared": 1})

    first = await cs._compute_stale_components()
    assert first == ["autobot_shared"]

    # Within the TTL the cached value is returned even though the checker now
    # reports clean — proving /status is not re-checksumming on every poll.
    monkeypatch.setattr(cs, "build_drift_report", lambda *a: {"drifted_files": [], "total_compared": 1})
    assert await cs._compute_stale_components() == ["autobot_shared"]


async def test_failing_component_is_isolated(monkeypatch, tmp_path):
    import api.code_sync as cs

    _reset_cache(cs)
    monkeypatch.setattr(cs, "ALLOWED_COMPONENTS", {"autobot-slm-backend", "autobot_shared"})
    monkeypatch.setattr(cs, "get_default_deployed_dir", lambda c: str(tmp_path))
    monkeypatch.setattr(cs, "get_default_source_dir", lambda c: str(tmp_path))

    def flaky(src, dep, comp):
        if comp == "autobot-slm-backend":
            raise RuntimeError("checksum walk exploded")
        return {"drifted_files": ["y.py"], "total_compared": 1}

    monkeypatch.setattr(cs, "build_drift_report", flaky)

    # The exploding component is skipped, the healthy one still surfaces.
    assert await cs._compute_stale_components() == ["autobot_shared"]
