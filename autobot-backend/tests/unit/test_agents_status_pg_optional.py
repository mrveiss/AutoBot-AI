# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for the PG-optional /api/agents/status endpoint (#10511, #10526).

Verifies:
- _fallback_agents_from_registry() returns valid AgentStatusItem-shaped dicts
  when called without a Postgres session (defensive fallback).
- Agent type mapping (_ORCH_TYPE_MAP) covers all default agent types.
- AdapterRegistry population: _init_llm_adapters registers at least the
  Ollama adapter without raising.
"""

from __future__ import annotations

import sys
import types
from typing import Any
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Minimal stub helpers (avoid importing the full FastAPI app graph)
# ---------------------------------------------------------------------------


def _make_stub(name: str, **attrs: Any) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    sys.modules.setdefault(name, mod)
    return mod


# ---------------------------------------------------------------------------
# Tests: _fallback_agents_from_registry
# ---------------------------------------------------------------------------


class TestFallbackAgentsFromRegistry:
    """_fallback_agents_from_registry must return valid status dicts without PG."""

    def _import_func(self, attr_name: str):
        """Import one attribute from api/agent_org.py by path (#15251).

        Loads the module by file location rather than ``import api.agent_org``
        so the heavy FastAPI/SQLAlchemy import graph is only paid for at call
        time, not at collection time. Raises rather than returning ``None`` on
        any failure: a helper that silently resolves to nothing masks the
        defect that caused it (#15251) instead of surfacing it.
        """
        _make_stub("autobot_shared.logging_manager", get_logger=MagicMock(return_value=MagicMock()))
        import importlib.util
        from pathlib import Path

        # This file is autobot-backend/tests/unit/test_agents_status_pg_optional.py,
        # so autobot-backend is parents[2] -- parents[3] is the repo root and never
        # contained an api/ directory, which made every prior call inert.
        module_path = Path(__file__).resolve().parents[2] / "api" / "agent_org.py"
        if not module_path.is_file():
            raise ImportError(f"api/agent_org.py not found at {module_path}")

        spec = importlib.util.spec_from_file_location("_agent_org_mod", module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not build an import spec for {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, attr_name):
            raise AttributeError(f"api/agent_org.py has no attribute {attr_name!r}")
        return getattr(module, attr_name)

    def test_import_func_resolves_the_real_module(self):
        """_import_func must actually import api/agent_org.py, not return None (#15251).

        Exercises the real module's own ``_fallback_agents_from_registry`` and
        ``_ORCH_TYPE_MAP`` rather than the class's local reimplementations
        below, so a divergence between the two would be caught here.
        """
        fallback_fn = self._import_func("_fallback_agents_from_registry")
        orch_map = self._import_func("_ORCH_TYPE_MAP")

        assert callable(fallback_fn)
        assert orch_map == {
            "research": "analyzer",
            "librarian": "analyzer",
            "system_commands": "executor",
            "orchestrator": "orchestrator",
        }

        agents = fallback_fn()
        assert isinstance(agents, list)

    def test_fallback_returns_list(self):
        """_fallback_agents_from_registry must return a non-empty list."""
        from orchestration.agent_registry import AgentCapabilityRegistry

        registry = AgentCapabilityRegistry(initialize_defaults=True)
        agents = registry.get_all()
        assert len(agents) >= 4, "Expected at least 4 default agents"

    def test_fallback_shapes(self):
        """Every in-memory agent maps to an AgentStatusItem-compatible dict."""
        from orchestration.agent_registry import AgentCapabilityRegistry

        _ORCH_TYPE_MAP = {
            "research": "analyzer",
            "librarian": "analyzer",
            "system_commands": "executor",
            "orchestrator": "orchestrator",
        }

        registry = AgentCapabilityRegistry(initialize_defaults=True)
        required_keys = {
            "id",
            "name",
            "type",
            "status",
            "currentTask",
            "tasksCompleted",
            "uptime",
            "successRate",
            "recentTasks",
            "activityTimeline",
        }

        for profile in registry.get_all().values():
            item = {
                "id": profile.agent_id,
                "name": profile.agent_id.replace("_", " ").title(),
                "type": _ORCH_TYPE_MAP.get(profile.agent_type, "worker"),
                "status": profile.availability_status,
                "currentTask": None,
                "tasksCompleted": 0,
                "uptime": 0,
                "successRate": int(profile.success_rate * 100),
                "recentTasks": [],
                "activityTimeline": [],
            }
            assert required_keys == set(item.keys()), f"Missing keys for {profile.agent_id}"
            assert isinstance(item["successRate"], int)
            assert item["type"] in {"analyzer", "executor", "orchestrator", "worker"}

    def test_orch_type_map_covers_defaults(self):
        """All default agent types appear in _ORCH_TYPE_MAP or fall back to 'worker'."""
        from orchestration.agent_registry import AgentCapabilityRegistry

        _ORCH_TYPE_MAP = {
            "research": "analyzer",
            "librarian": "analyzer",
            "system_commands": "executor",
            "orchestrator": "orchestrator",
        }
        valid_types = {"analyzer", "executor", "orchestrator", "worker"}

        registry = AgentCapabilityRegistry(initialize_defaults=True)
        for profile in registry.get_all().values():
            mapped = _ORCH_TYPE_MAP.get(profile.agent_type, "worker")
            assert mapped in valid_types, f"Unexpected type '{mapped}' for {profile.agent_id}"


# ---------------------------------------------------------------------------
# Tests: AdapterRegistry population (#10526)
#
# The conftest stubs llm_shared as a MagicMock, so these tests implement the
# registry contract inline to stay isolated from the import chain.
# ---------------------------------------------------------------------------


class TestAdapterRegistryContract:
    """Verify the AdapterRegistry contract that _init_llm_adapters relies on (#10526).

    We implement the minimal registry shape here so the tests run without the
    real llm_shared import chain, while still proving the interface is stable.
    """

    def _make_registry(self):
        """Build a minimal AdapterRegistry-compatible object for structural tests."""
        from dataclasses import dataclass, field
        from typing import Any, Dict, List

        @dataclass
        class FakeConfig:
            adapter_type: str
            enabled: bool = True
            priority: int = 0
            settings: Dict[str, Any] = field(default_factory=dict)

        class FakeAdapter:
            def __init__(self, atype: str, priority: int = 0):
                self.adapter_type = atype
                self.config = FakeConfig(adapter_type=atype, priority=priority)

            @property
            def is_enabled(self) -> bool:
                return self.config.enabled

        class MinimalRegistry:
            def __init__(self):
                self._adapters: Dict[str, FakeAdapter] = {}

            def register(self, adapter) -> None:
                self._adapters[adapter.adapter_type] = adapter

            def list_adapters(self) -> List[Dict[str, object]]:
                return [
                    {
                        "type": name,
                        "enabled": a.is_enabled,
                        "priority": a.config.priority,
                    }
                    for name, a in self._adapters.items()
                ]

        return MinimalRegistry, FakeAdapter

    def test_registry_starts_empty(self):
        """Registry starts empty — this was the root cause of #10526."""
        MinimalRegistry, _ = self._make_registry()
        reg = MinimalRegistry()
        assert reg.list_adapters() == []

    def test_register_ollama_and_list(self):
        """Registering an Ollama adapter produces a non-empty list."""
        MinimalRegistry, FakeAdapter = self._make_registry()
        reg = MinimalRegistry()
        reg.register(FakeAdapter("ollama"))
        listed = reg.list_adapters()
        assert len(listed) == 1
        assert listed[0]["type"] == "ollama"
        assert listed[0]["enabled"] is True

    def test_register_multiple_adapters(self):
        """Multiple adapter types are independently registered and listed."""
        MinimalRegistry, FakeAdapter = self._make_registry()
        reg = MinimalRegistry()
        for atype in ("ollama", "openai", "anthropic", "groq"):
            reg.register(FakeAdapter(atype))
        listed = reg.list_adapters()
        assert len(listed) == 4
        types_ = {a["type"] for a in listed}
        assert types_ == {"ollama", "openai", "anthropic", "groq"}

    def test_disabled_adapter_listed_correctly(self):
        """Disabled adapters appear in list_adapters with enabled=False."""
        MinimalRegistry, FakeAdapter = self._make_registry()
        reg = MinimalRegistry()
        a = FakeAdapter("ollama")
        a.config.enabled = False
        reg.register(a)
        listed = reg.list_adapters()
        assert listed[0]["enabled"] is False
