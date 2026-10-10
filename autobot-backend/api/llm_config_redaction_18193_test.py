# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""GET /api/llm/config must not return operator-set credentials from backend.llm (#18193)."""

import copy

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import llm as llm_api
from auth_middleware import check_admin_permission, get_current_user
from config import unified_config_manager
from constants.model_constants import ModelConstants

_PW = "SENTINEL-PW"  # f-string below: no literal user:pass@ in the source
_OPENAI = "SENTINEL-OPENAI-" + "KEY"
_EMBED = "SENTINEL-EMBED-" + "KEY"
_MODEL = "positive-control-model:7b"
_BACKEND_LLM = {
    "provider_type": "cloud",
    "local": {
        "provider": "ollama",
        "providers": {
            "ollama": {
                "selected_model": _MODEL,
                "models": ["alpha", "beta"],
                "endpoint": "http://ollama.example:11434/api/generate",
                "host": f"http://user:{_PW}@host:1234",
                "max_tokens": 4096,
            }
        },
    },
    "cloud": {
        "providers": {
            "openai": {"api_key": _OPENAI, "model": "gpt-x", "timeout": 30},
            "embedding": [{"name": "emb", "api_key": _EMBED, "dim": 768}],
        }
    },
}


def _admin_gate(role: str):
    """Stand-in for check_admin_permission (the suite stubs auth_middleware, #14982): 403 unless admin."""

    def gate() -> bool:
        if role != "admin":
            raise HTTPException(status_code=403, detail="Admin permission required")
        return True

    return gate


def _client(monkeypatch, tree, role: str = "admin") -> TestClient:
    def fake_get_nested(path, default=None):
        node = {"backend": {"llm": copy.deepcopy(tree)}}
        for key in path.split("."):
            if not isinstance(node, dict) or key not in node:
                return default
            node = node[key]
        return node

    monkeypatch.setattr(unified_config_manager, "get_nested", fake_get_nested)
    app = FastAPI()
    app.include_router(llm_api.router, prefix="/api/llm")
    app.dependency_overrides[get_current_user] = lambda: {"username": f"{role}-user", "role": role}
    app.dependency_overrides[check_admin_permission] = _admin_gate(role)
    return TestClient(app)


def test_config_response_carries_no_credential_sentinel(monkeypatch) -> None:
    r = _client(monkeypatch, _BACKEND_LLM).get("/api/llm/config")
    assert r.status_code == 200
    assert "SENTINEL" not in r.text, r.text


def test_config_response_keeps_every_non_secret_field(monkeypatch) -> None:
    body = _client(monkeypatch, _BACKEND_LLM).get("/api/llm/config").json()
    assert body["ollama"]["selected_model"] == _MODEL
    unified = body["unified"]
    assert unified["local"]["providers"]["ollama"]["endpoint"] == "http://ollama.example:11434/api/generate"
    assert unified["local"]["providers"]["ollama"]["host"] == "http://user:" + "*" * 10 + "@host:1234"
    assert unified["local"]["providers"]["ollama"]["max_tokens"] == 4096
    assert unified["local"]["providers"]["ollama"]["models"] == ["alpha", "beta"]
    assert unified["cloud"]["providers"]["openai"] == {"api_key": "**********", "model": "gpt-x", "timeout": 30}
    assert unified["cloud"]["providers"]["embedding"] == [{"name": "emb", "api_key": "**********", "dim": 768}]


def test_a_tree_without_credentials_is_returned_unchanged(monkeypatch) -> None:
    clean = copy.deepcopy(_BACKEND_LLM)
    clean["cloud"]["providers"]["openai"].pop("api_key")
    clean["cloud"]["providers"]["embedding"][0].pop("api_key")
    clean["local"]["providers"]["ollama"]["host"] = "http://host:1234"
    body = _client(monkeypatch, clean).get("/api/llm/config").json()
    assert body["unified"] == clean


def test_current_returns_only_model_and_provider_to_a_non_admin(monkeypatch) -> None:
    r = _client(monkeypatch, _BACKEND_LLM, role="user").get("/api/llm/current")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"model", "provider", "config"}  # LLMCurrentResponse fields: schema unchanged
    # Exactly the active model and provider; `config` is the schema-required envelope, always empty.
    assert body == {"model": ModelConstants.DEFAULT_OLLAMA_MODEL, "provider": "ollama", "config": {}}
    for leaked in ("SENTINEL", "unified", "api_key", "endpoint", "ollama.example", _MODEL):
        assert leaked not in r.text, leaked


def test_config_is_admin_only(monkeypatch) -> None:
    client = _client(monkeypatch, _BACKEND_LLM, role="user")
    r = client.get("/api/llm/config")
    assert r.status_code == 403, r.text
    assert "SENTINEL" not in r.text and _MODEL not in r.text


def test_an_admin_gets_the_redacted_body(monkeypatch) -> None:
    r = _client(monkeypatch, _BACKEND_LLM, role="admin").get("/api/llm/config")
    assert r.status_code == 200 and "SENTINEL" not in r.text
    assert r.json()["ollama"]["selected_model"] == _MODEL
