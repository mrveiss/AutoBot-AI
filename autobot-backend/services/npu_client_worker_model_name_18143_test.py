# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#18143: the NPU client sends the worker a model name the worker loads (else it answers a mock)."""

import ast
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock

import pytest

WORKER_SETTINGS = (
    Path(__file__).resolve().parents[2] / "autobot-npu-worker/resources/windows-npu-worker/app/worker_settings.py"
)


def _supported_models() -> set:
    """Read SUPPORTED_MODELS from the worker module's source (it is not importable here)."""
    tree = ast.parse(WORKER_SETTINGS.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") == "SUPPORTED_MODELS":
            return {k.value for k in node.value.keys}
    raise AssertionError("SUPPORTED_MODELS not found")


@pytest.mark.asyncio
async def test_request_model_is_one_the_worker_loads(monkeypatch):
    from autobot_shared import egress_allowlist
    from services import npu_client

    # #17576: the request is egress-guarded, so the fake worker origin must be an internal one.
    monkeypatch.setattr(egress_allowlist, "_ssot_service_urls", lambda: ["http://worker"])
    egress_allowlist.reset_internal_origin_state()
    seen = {}

    @asynccontextmanager
    async def _post(url, **kw):
        seen.update(kw["params"])
        yield MagicMock(status=500)

    session = MagicMock(post=_post)
    client = npu_client.NPUClient.__new__(npu_client.NPUClient)
    client.base_url = "http://worker"

    async def _get_session():
        return session

    client._get_session = _get_session
    monkeypatch.setattr(npu_client, "active_embedding_model", lambda: "nomic-embed-text:latest")
    await client.generate_embeddings(["x"])
    assert seen["model_name"] in _supported_models()
    assert "nomic-embed-text:latest" not in _supported_models()  # contrast: the raw name falls to the mock path
