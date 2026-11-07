# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""/api/embeddings reports the model actually in use and no longer fakes a model change (#19377)."""

from __future__ import annotations

import json

import pytest

import api.embeddings as emb
from api.schemas_knowledge import EmbeddingUpdate


def _body(response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_put_refuses_and_names_the_switch(monkeypatch):
    monkeypatch.setattr(emb, "active_embedding_model", lambda: "nomic-embed-text:latest")
    writes = []
    monkeypatch.setattr(emb.unified_config_manager, "set_nested", lambda *a: writes.append(a))

    response = await emb.update_embedding_settings.__wrapped__(
        EmbeddingUpdate(provider="ollama", selected_model="mxbai-embed-large:latest"), admin_check=True
    )

    assert response.status_code == 409
    assert "'nomic-embed-text:latest'" in _body(response)["message"] and "#19379" in _body(response)["message"]
    assert writes == [], "nothing is written"


@pytest.mark.asyncio
async def test_settings_and_status_report_the_resolver_model(monkeypatch):
    monkeypatch.setattr(emb, "active_embedding_model", lambda: "mxbai-embed-large:latest")
    file_copy = {"provider": "ollama", "providers": {"ollama": {"selected_model": "phi3:mini", "endpoint": "e"}}}
    monkeypatch.setattr(emb.unified_config_manager, "get_nested", lambda *a, **k: json.loads(json.dumps(file_copy)))

    settings = _body(await emb.get_embedding_settings.__wrapped__(current_user={}))
    status = _body(await emb.get_embedding_status.__wrapped__(current_user={}))

    assert settings["embedding_config"]["providers"]["ollama"]["selected_model"] == "mxbai-embed-large:latest"
    assert status["embedding_status"]["model"] == "mxbai-embed-large:latest"
