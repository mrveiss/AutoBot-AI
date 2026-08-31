#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test NPU Worker Functionality
Validates NPU worker deployment and inference capabilities

Every check here drives the *deployed* NPU worker over HTTP: health, device
enumeration, model load, model registry and a real inference round-trip. None of
it is in-process, so the module carries ``integration`` and a single autouse
precondition that skips (with a named reason) when nothing is listening on the
worker's endpoint — see ``autobot_shared/live_service_probe.py`` (#14930).

Before #14979 this was a driver script: ``NPUWorkerTester.__init__`` made the
class uncollectable by pytest, the ``test_*`` methods returned ``True``/``False``
instead of asserting, and ``run_all_tests()`` plus ``main()`` printed a summary
nothing read. Five checks that collected zero items now collect five.
"""

from __future__ import annotations

from typing import Any

import aiohttp
import pytest

from autobot_shared.live_service_probe import require_live_endpoint
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

# #14979: real HTTP against a deployed worker — excluded from the unit gate,
# selected by marker-tests.yml.
pytestmark = pytest.mark.integration

logger = get_logger(__name__)

# #1618 / SSOT: the endpoint was hard-coded as a default argument, so the suite
# probed one fixed node regardless of where the NPU worker actually runs.
NPU_WORKER_URL = config.npu_worker_url

# Module constant rather than a literal at each call site: NPU model loads are
# slow on cold hardware, so the timeout must not become the thing being measured.
NPU_REQUEST_TIMEOUT_SECONDS = 120.0

TEST_MODEL_ID = "test-phi3-mini"
TEST_MODEL_CONFIG: dict[str, str] = {
    "model": "microsoft/Phi-3-mini-4k-instruct",
    "device": "NPU",
    "precision": "INT8",
}
TEST_PROMPT = "Hello, this is a test inference request"


@pytest.fixture(autouse=True)
def _require_live_npu_worker() -> None:
    """Skip when the NPU worker is absent (#14930).

    Each test below issues real HTTP to the worker. On a runner without one the
    result was a refused connection reported as a failure — a measurement of the
    runner's inventory, not of the NPU stack.
    """
    require_live_endpoint(NPU_WORKER_URL, what="the AutoBot NPU worker")


@pytest.fixture
async def npu_session() -> Any:
    """An ``aiohttp`` session bound to the NPU worker, closed after each test."""
    timeout = aiohttp.ClientTimeout(total=NPU_REQUEST_TIMEOUT_SECONDS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        yield session


async def _get_json(session: aiohttp.ClientSession, path: str) -> Any:
    """GET *path* on the worker and return the decoded body, asserting HTTP 200."""
    async with session.get(f"{NPU_WORKER_URL}{path}") as response:
        body = await response.text()
        assert response.status == 200, f"NPU worker GET {path} returned HTTP {response.status}, body: {body[:300]}"
        return await response.json(content_type=None)


async def _load_test_model(session: aiohttp.ClientSession) -> Any:
    """Ask the worker to load the fixture model, asserting the load succeeded."""
    payload = {"model_id": TEST_MODEL_ID, "model_config": TEST_MODEL_CONFIG}
    async with session.post(f"{NPU_WORKER_URL}/models/load", json=payload) as response:
        body = await response.text()
        assert response.status == 200, (
            f"NPU worker POST /models/load returned HTTP {response.status} for "
            f"model_id={TEST_MODEL_ID} on device={TEST_MODEL_CONFIG['device']}, body: {body[:300]}"
        )
        return await response.json(content_type=None)


class TestNPUWorker:
    """The deployed NPU worker answers health, device, model and inference calls."""

    async def test_health(self, npu_session: aiohttp.ClientSession) -> None:
        """``GET /health`` reports the worker as up."""
        data = await _get_json(npu_session, "/health")
        logger.info("NPU worker health check", data=data)

        assert isinstance(data, dict), f"NPU worker /health returned {type(data).__name__}, expected a JSON object"
        assert data, "NPU worker /health returned an empty body — the worker answered but reported no state"

    async def test_device_detection(self, npu_session: aiohttp.ClientSession) -> None:
        """``GET /devices`` enumerates at least one inference device."""
        data = await _get_json(npu_session, "/devices")
        logger.info("NPU device detection", data=data)

        assert isinstance(data, dict), f"NPU worker /devices returned {type(data).__name__}, expected a JSON object"
        assert data, "NPU worker /devices returned an empty body — no inference device was enumerated"

    async def test_model_loading(self, npu_session: aiohttp.ClientSession) -> None:
        """``POST /models/load`` accepts and completes a model load."""
        data = await _load_test_model(npu_session)
        logger.info("Model loading test", data=data)

        assert isinstance(data, dict), f"NPU worker /models/load returned {type(data).__name__}, expected a JSON object"
        assert data, f"NPU worker accepted the load of {TEST_MODEL_ID} but returned an empty body"

    async def test_model_status(self, npu_session: aiohttp.ClientSession) -> None:
        """``GET /models`` lists the model once it has been loaded."""
        await _load_test_model(npu_session)
        data = await _get_json(npu_session, "/models")
        logger.info("Model status", data=data)

        assert isinstance(data, dict), f"NPU worker /models returned {type(data).__name__}, expected a JSON object"
        assert TEST_MODEL_ID in str(data), (
            f"NPU worker /models does not list {TEST_MODEL_ID} after a successful load — "
            f"the registry lost the model. Body: {str(data)[:300]}"
        )

    async def test_inference(self, npu_session: aiohttp.ClientSession) -> None:
        """``POST /inference`` returns generated output for a loaded model."""
        await _load_test_model(npu_session)

        payload = {
            "model_id": TEST_MODEL_ID,
            "input_text": TEST_PROMPT,
            "max_tokens": 50,
            "temperature": 0.7,
        }
        async with npu_session.post(f"{NPU_WORKER_URL}/inference", json=payload) as response:
            body = await response.text()
            assert response.status == 200, (
                f"NPU worker POST /inference returned HTTP {response.status} for "
                f"model_id={TEST_MODEL_ID}, body: {body[:300]}"
            )
            data = await response.json(content_type=None)

        logger.info("Inference test", data=data)
        assert isinstance(data, dict), f"NPU worker /inference returned {type(data).__name__}, expected a JSON object"
        assert data, f"NPU worker ran inference on {TEST_MODEL_ID} but returned an empty body"
