# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for NPU pipeline dispatch hook in ProviderRegistry (MVA-1099).

Covers:
- Oversized model routes to PipelineDispatcher
- Single-worker-sized model routes normally (no pipeline)
- Latency guard: high-latency pair falls back to single-worker

These tests import ProviderRegistry directly via file path to bypass the
top-level conftest.py llm_shared stub, which prevents importing the real
module for tests that exercise the registry logic.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Bootstrap: load real provider_registry module without triggering the
# conftest.py stub that replaces the entire llm_shared package.
# ---------------------------------------------------------------------------


def _load_module_from_file(name: str, path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _bootstrap_provider_registry():
    import os

    backend = os.path.join(os.path.dirname(__file__), "..")

    # Minimal stubs for provider_registry's top-level imports that are heavy
    # or absent in the test venv.
    for heavy in [
        "autobot_shared",
        "autobot_shared.ssot_config",
        "autobot_shared.logging_manager",
        "prepared_facts",
    ]:
        if heavy not in sys.modules:
            stub = types.ModuleType(heavy)
            sys.modules[heavy] = stub

    # ssot_config.config must be an object with attribute access
    cfg_stub = sys.modules.setdefault("autobot_shared.ssot_config", types.ModuleType("autobot_shared.ssot_config"))
    if not hasattr(cfg_stub, "config"):
        cfg_stub.config = MagicMock()

    # logging_manager.get_logger must return a real logger (pytest captures it)
    import logging

    log_stub = sys.modules["autobot_shared.logging_manager"]
    if not hasattr(log_stub, "get_logger"):
        log_stub.get_logger = logging.getLogger

    # prepared_facts.ProviderRuntimeFact
    pf_stub = sys.modules["prepared_facts"]
    if not hasattr(pf_stub, "ProviderRuntimeFact"):
        pf_stub.ProviderRuntimeFact = MagicMock()

    # llm_shared.model_param_registry
    mp_name = "llm_shared.model_param_registry"
    if mp_name not in sys.modules:
        mp_stub = types.ModuleType(mp_name)
        mp_stub.apply_model_defaults = lambda model, provider, kw: kw
        mp_stub.apply_prompt_prefix = lambda model, msgs: None
        sys.modules[mp_name] = mp_stub

    # llm_shared.models.LLMRequest (lightweight stub)
    lm_name = "llm_shared.models"
    if lm_name not in sys.modules:
        lm_stub = types.ModuleType(lm_name)
        lm_stub.LLMRequest = MagicMock  # tests use MagicMock(spec=...) anyway
        sys.modules[lm_name] = lm_stub

    # llm_shared.base_provider.BaseProvider
    bp_name = "llm_shared.base_provider"
    if bp_name not in sys.modules:
        bp_stub = types.ModuleType(bp_name)
        bp_stub.BaseProvider = object
        sys.modules[bp_name] = bp_stub

    # Ensure the llm_shared package stub won't shadow what we're about to load.
    # We keep it (to avoid breaking other imports) but patch provider_registry in.
    module_path = os.path.join(backend, "llm_shared", "provider_registry.py")
    mod = _load_module_from_file("llm_shared.provider_registry", module_path)
    # Also attach to llm_shared package if a stub exists there.
    if "llm_shared" in sys.modules:
        sys.modules["llm_shared"].provider_registry = mod  # type: ignore[attr-defined]
    return mod


_pr_mod = _bootstrap_provider_registry()
ProviderRegistry = _pr_mod.ProviderRegistry
_NPU_POOL_PROVIDER_NAME = _pr_mod._NPU_POOL_PROVIDER_NAME


# ---------------------------------------------------------------------------
# Load real pipeline_dispatcher module
# ---------------------------------------------------------------------------


def _bootstrap_pipeline_dispatcher():
    import os

    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "services",
        "npu_pipeline",
        "pipeline_dispatcher.py",
    )
    return _load_module_from_file("services.npu_pipeline.pipeline_dispatcher", path)


_pd_mod = _bootstrap_pipeline_dispatcher()
WorkerNode = _pd_mod.WorkerNode
WorkerState = _pd_mod.WorkerState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(model_bytes: int):
    req = MagicMock()
    req.metadata = {"npu_model_bytes": model_bytes}
    req.model_name = "test-model"
    req.messages = []
    return req


def _make_worker(worker_id: str, vram_bytes: int, online: bool = True):
    w = WorkerNode(worker_id=worker_id, vram_bytes=vram_bytes)
    if not online:
        w.state = WorkerState.OFFLINE
    return w


def _make_dispatcher(workers, hop_latency_ms: float = 2.5):
    disp = MagicMock()
    disp.workers = workers

    async def _sim_transfer(src, dst):
        return hop_latency_ms

    disp._simulate_layer_transfer = _sim_transfer
    return disp


def _make_provider(name: str):
    p = MagicMock()
    p.provider_name = name
    return p


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestNpuPipelineRouting(unittest.IsolatedAsyncioTestCase):

    def _make_registry_with_npu_provider(self, dispatcher):
        registry = ProviderRegistry()
        npu_provider = _make_provider(_NPU_POOL_PROVIDER_NAME)
        registry._check_health_cached = AsyncMock(return_value=True)
        registry._providers[_NPU_POOL_PROVIDER_NAME] = npu_provider
        registry._fallback_chain = [_NPU_POOL_PROVIDER_NAME]
        registry.set_npu_pipeline_dispatcher(dispatcher, enabled=True)
        registry.enrich_request = lambda req, name: req
        return registry, npu_provider

    async def test_oversized_model_routes_to_pipeline(self):
        """Model bytes > max single-worker VRAM → PipelineDispatcher returned."""
        workers = [
            _make_worker("w0", vram_bytes=8 * (1024**3)),
            _make_worker("w1", vram_bytes=8 * (1024**3)),
        ]
        dispatcher = _make_dispatcher(workers, hop_latency_ms=2.5)
        registry, _ = self._make_registry_with_npu_provider(dispatcher)

        request = _make_request(model_bytes=16 * (1024**3))
        result = await registry.get_provider_for_request(
            provider_name=_NPU_POOL_PROVIDER_NAME,
            request=request,
        )
        self.assertIs(result, dispatcher)

    async def test_single_worker_sized_model_routes_normally(self):
        """Model bytes ≤ max single-worker VRAM → regular provider returned."""
        workers = [
            _make_worker("w0", vram_bytes=16 * (1024**3)),
            _make_worker("w1", vram_bytes=16 * (1024**3)),
        ]
        dispatcher = _make_dispatcher(workers, hop_latency_ms=2.5)
        registry, npu_provider = self._make_registry_with_npu_provider(dispatcher)

        request = _make_request(model_bytes=8 * (1024**3))
        result = await registry.get_provider_for_request(
            provider_name=_NPU_POOL_PROVIDER_NAME,
            request=request,
        )
        self.assertIs(result, npu_provider)

    async def test_latency_fallback_fires_on_high_latency_pair(self):
        """High hop latency exceeds threshold → _should_use_npu_pipeline returns False."""
        workers = [
            _make_worker("w0", vram_bytes=8 * (1024**3)),
            _make_worker("w1", vram_bytes=8 * (1024**3)),
        ]
        # hop=600 ms, baseline=200 ms, multiplier=2.0 → threshold=400 ms < 600 ms
        dispatcher = _make_dispatcher(workers, hop_latency_ms=600.0)
        registry, npu_provider = self._make_registry_with_npu_provider(dispatcher)

        request = _make_request(model_bytes=16 * (1024**3))
        should_pipeline = await registry._should_use_npu_pipeline(request, baseline_ttft_ms=200.0)
        self.assertFalse(should_pipeline)

    async def test_pipeline_disabled_skips_pipeline(self):
        """npu_pipeline_enabled=False → regular provider returned even for oversized model."""
        workers = [_make_worker("w0", 8 * (1024**3)), _make_worker("w1", 8 * (1024**3))]
        dispatcher = _make_dispatcher(workers)
        registry, npu_provider = self._make_registry_with_npu_provider(dispatcher)
        registry._npu_pipeline_enabled = False

        request = _make_request(model_bytes=16 * (1024**3))
        result = await registry.get_provider_for_request(
            provider_name=_NPU_POOL_PROVIDER_NAME,
            request=request,
        )
        self.assertIs(result, npu_provider)

    async def test_no_npu_model_bytes_skips_pipeline(self):
        """Request without npu_model_bytes metadata → route normally."""
        workers = [_make_worker("w0", 8 * (1024**3)), _make_worker("w1", 8 * (1024**3))]
        dispatcher = _make_dispatcher(workers)
        registry, npu_provider = self._make_registry_with_npu_provider(dispatcher)

        req = MagicMock()
        req.metadata = {}
        req.model_name = "test"
        req.messages = []

        result = await registry.get_provider_for_request(
            provider_name=_NPU_POOL_PROVIDER_NAME,
            request=req,
        )
        self.assertIs(result, npu_provider)


if __name__ == "__main__":
    unittest.main()
