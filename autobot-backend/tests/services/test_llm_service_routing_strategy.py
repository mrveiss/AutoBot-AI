# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLMService honours ``backend.llm.routing_strategy`` (#18297).

``LLMService._select_chat_model`` used to build a ``TieredModelRouter``
(an alias of ``ComplexityRouter``) directly, so the configured strategy was
never consulted on the chat path.  It now resolves its router through the
strategy registry; these tests pin that for ``cost`` and for the default.

Loads the real ``services/llm_service.py`` under a private name, the same
way ``test_llm_service_caching.py`` does, because the harness stubs
``services.llm_service`` in sys.modules.
"""

from __future__ import annotations

import importlib.util as _ilu
import pathlib
import sys
from unittest.mock import patch

import pytest

from autobot_shared.ssot_config import config
from llm_shared.tiered_routing.complexity_router import ComplexityRouter
from llm_shared.tiered_routing.cost_router import CostRouter
from llm_shared.tiered_routing.registry import get_active_router
from llm_shared.tiered_routing.tier_config import ComplexityResult
from llm_shared.types import LLMType

# The harness stubs the llm_shared.tiered_routing package, whose catch-all
# __getattr__ would hand back a mock for ``registry``; take the real module.
routing_registry = sys.modules[get_active_router.__module__]

_BACKEND = pathlib.Path(__file__).resolve().parents[2]  # autobot-backend/
_MESSAGES = [{"role": "user", "content": "summarise the quarterly report"}]


def _load_real_module(private_name: str, relpath: str):
    """Load a real module file under a private name (no sys.modules clobber)."""
    spec = _ilu.spec_from_file_location(private_name, str(_BACKEND / relpath))
    assert spec and spec.loader
    mod = _ilu.module_from_spec(spec)
    sys.modules[private_name] = mod
    spec.loader.exec_module(mod)
    return mod


if "llm_shared.rate_limit_backoff" not in sys.modules:
    _load_real_module("llm_shared.rate_limit_backoff", "llm_shared/rate_limit_backoff.py")

LLMService = _load_real_module("_real_llm_service_18297", "services/llm_service.py").LLMService


class _NoProviderRegistry:
    """Registry stub; routing selection never reaches a provider."""


@pytest.fixture
def strategy(monkeypatch):
    """Set the routing strategy and drop the registry singleton around a test."""

    def _set(name: str) -> None:
        monkeypatch.setenv("AUTOBOT_LLM_ROUTING_STRATEGY", name)
        monkeypatch.setattr(routing_registry, "_active_router", None)
        monkeypatch.setattr(config, "chat_tiered_routing", True, raising=False)

    yield _set
    routing_registry._active_router = None


def _routed(model: str) -> tuple:
    return model, ComplexityResult(score=5.0, factors={}, tier="complex", reasoning="test")


def test_cost_strategy_routes_chat_through_cost_router(strategy):
    strategy("cost")
    svc = LLMService(registry=_NoProviderRegistry())
    assert isinstance(svc.tier_router, CostRouter)

    with patch.object(CostRouter, "route", return_value=_routed("cost-pick")) as cost_route:
        selected = svc._select_chat_model(_MESSAGES, LLMType.GENERAL)

    cost_route.assert_called_once_with(_MESSAGES)
    assert selected == "cost-pick"


def test_default_strategy_keeps_complexity_router(strategy):
    strategy("complexity")
    svc = LLMService(registry=_NoProviderRegistry())
    assert isinstance(svc.tier_router, ComplexityRouter)

    with patch.object(ComplexityRouter, "route", return_value=_routed("tier-pick")) as tier_route:
        selected = svc._select_chat_model(_MESSAGES, LLMType.GENERAL)

    tier_route.assert_called_once_with(_MESSAGES)
    assert selected == "tier-pick"


def test_service_shares_the_registry_singleton(strategy):
    strategy("cost")
    svc = LLMService(registry=_NoProviderRegistry())
    assert svc.tier_router is routing_registry.get_active_router()
