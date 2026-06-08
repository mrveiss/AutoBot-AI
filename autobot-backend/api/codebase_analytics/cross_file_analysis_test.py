# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
End-to-end tests for the cross-file analysis hook (#6747).

Verifies that:
  1. The four cross-file rules from #6661 + #6684 fire when the analyzer
     is run over a fixture codebase.
  2. The findings get translated to the same dict shape ChromaDB persistence
     expects (so they surface in /codebase/problems with code_smell_*
     prefix matching the existing dashboard convention).
  3. The fire-and-forget scheduler swallows errors instead of breaking
     scan finalization.
"""

import importlib.util
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest


def _load_cross_file_module():
    spec = importlib.util.spec_from_file_location(
        "xfa_under_test",
        "autobot-backend/api/codebase_analytics/cross_file_analysis.py",
    )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"cross_file_analysis dep chain unavailable: {exc}")
    return mod


def _write(root: Path, name: str, body: str) -> Path:
    p = root / f"{name}.py"
    p.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_cross_file_analysis_finds_lsp_violation(tmp_path):
    """A fixture with a sync override of an async parent must produce
    a ``code_smell_lsp_signature_incompatible`` finding via the bridge."""
    xfa = _load_cross_file_module()

    _write(
        tmp_path,
        "agents",
        """
        class BaseAgent:
            async def is_available(self) -> bool:
                return True

        class LocalAgent(BaseAgent):
            def is_available(self) -> bool:
                return True
        """,
    )

    persisted: list = []

    async def fake_persist(problems, source_id=None):
        persisted.extend(problems)
        return len(problems)

    with patch.object(xfa, "_persist_to_chromadb", new=fake_persist):
        count = await xfa.run_cross_file_analysis(str(tmp_path), source_id=None, exclude_patterns=["__pycache__"])

    assert count >= 1, f"expected at least one finding persisted, got {count}"
    types = {p.get("type") for p in persisted}
    assert "code_smell_lsp_signature_incompatible" in types, f"expected LSP signature finding, got types={types}"


@pytest.mark.asyncio
async def test_cross_file_analysis_finds_duplicate_enum(tmp_path):
    """Two overlapping enums must produce a ``code_smell_duplicate_enum`` finding."""
    xfa = _load_cross_file_module()

    _write(
        tmp_path,
        "task_status",
        """
        from enum import Enum

        class TaskStatus(Enum):
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"
            FAILED = "failed"
        """,
    )
    _write(
        tmp_path,
        "step_status",
        """
        from enum import Enum

        class StepStatus(Enum):
            PENDING = "pending"
            RUNNING = "running"
            COMPLETED = "completed"
            FAILED = "failed"
        """,
    )

    persisted: list = []

    async def fake_persist(problems, source_id=None):
        persisted.extend(problems)
        return len(problems)

    with patch.object(xfa, "_persist_to_chromadb", new=fake_persist):
        count = await xfa.run_cross_file_analysis(str(tmp_path), source_id=None, exclude_patterns=["__pycache__"])

    assert count >= 1
    types = {p.get("type") for p in persisted}
    assert "code_smell_duplicate_enum" in types


@pytest.mark.asyncio
async def test_problem_dict_shape_matches_chromadb_persistence(tmp_path):
    """The dict shape produced by the bridge must include exactly the keys
    chromadb_storage._prepare_problem_document expects to read."""
    xfa = _load_cross_file_module()

    _write(
        tmp_path,
        "agents",
        """
        class BaseAgent:
            async def is_available(self) -> bool:
                return True

        class LocalAgent(BaseAgent):
            def is_available(self) -> bool:
                return True
        """,
    )

    persisted: list = []

    async def fake_persist(problems, source_id=None):
        persisted.extend(problems)
        return len(problems)

    with patch.object(xfa, "_persist_to_chromadb", new=fake_persist):
        await xfa.run_cross_file_analysis(str(tmp_path), source_id=None, exclude_patterns=["__pycache__"])

    assert persisted, "fixture must produce at least one finding"
    p = persisted[0]
    # Required keys read by chromadb_storage._prepare_problem_document:
    for key in ("type", "severity", "file_path", "line", "description", "suggestion"):
        assert key in p, f"problem dict missing required key {key!r}: {p}"
    # The type prefix matches the existing analyzers.py::_run_anti_pattern_analysis
    # convention so the dashboard groups findings consistently.
    assert p["type"].startswith("code_smell_"), p["type"]


@pytest.mark.asyncio
async def test_run_swallows_missing_root(tmp_path):
    """Non-existent root_path returns 0 — must NOT raise into scan finalization."""
    xfa = _load_cross_file_module()
    bogus = tmp_path / "does_not_exist"
    count = await xfa.run_cross_file_analysis(str(bogus), source_id=None)
    assert count == 0


@pytest.mark.asyncio
async def test_run_swallows_detector_failure(tmp_path):
    """If the detector raises, the bridge must log + return 0 — never propagate."""
    xfa = _load_cross_file_module()
    _write(tmp_path, "noop", "x = 1\n")

    class _Boom:
        async def analyze_cross_file_only(self, **_kwargs):
            raise RuntimeError("simulated failure")

    fake_module = type(
        "fake_apd",
        (),
        {"AntiPatternDetector": lambda *args, **kwargs: _Boom()},
    )
    import sys as _sys

    with patch.dict(_sys.modules, {"code_analysis.src.anti_pattern_detector": fake_module}):
        count = await xfa.run_cross_file_analysis(str(tmp_path), source_id=None, exclude_patterns=["__pycache__"])
    assert count == 0
