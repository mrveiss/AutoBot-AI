# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC tests conftest — stubs heavy optional dependencies for unit tests.

The ``knowledge`` module (and its chromadb/opentelemetry chain) is not
importable in the dev/CI environment.  We install a lightweight sys.modules
stub so that any test module that lazily imports ``knowledge.get_knowledge_base``
receives a safe AsyncMock instead of an ImportError.

Tests that need specific behaviour override it with ``patch("knowledge.get_knowledge_base")``.
"""

import sys
import types
from unittest.mock import AsyncMock, MagicMock


def _make_knowledge_stub() -> types.ModuleType:
    """Return a thin module stub for the ``knowledge`` package."""
    mod = types.ModuleType("knowledge")
    mod.__path__ = []  # type: ignore[attr-defined]
    mod.__package__ = "knowledge"
    mod.get_knowledge_base = AsyncMock(return_value=MagicMock())
    return mod


# The ``knowledge`` module imports lazily but fails when attributes are accessed
# because chromadb → opentelemetry has a broken dependency in the dev venv.
# Unconditionally replace with a stub so every lazy ``from knowledge import X``
# receives our mock instead of triggering the broken chain.
sys.modules["knowledge"] = _make_knowledge_stub()


def _make_services_stub() -> types.ModuleType:
    """Return a thin stub for the ``services`` package hierarchy."""
    services_mod = types.ModuleType("services")
    services_mod.__path__ = []  # type: ignore[attr-defined]
    services_mod.__package__ = "services"

    llm_mod = types.ModuleType("services.llm_service")
    llm_mod.__package__ = "services"
    llm_mod.get_llm_service = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]

    services_mod.llm_service = llm_mod  # type: ignore[attr-defined]
    sys.modules["services"] = services_mod
    sys.modules["services.llm_service"] = llm_mod
    return services_mod


# ``services.llm_service`` is imported at module level by llc/kb/handoff_brief.py
# (merged to Dev_new_gui after issue-8238).  Stub it so the test collection
# phase does not fail when the full service stack is absent.
_make_services_stub()
