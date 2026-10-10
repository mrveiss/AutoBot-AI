# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""GET /api/llm/config must not return operator-set credentials from backend.llm (#18193)."""

import copy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import llm as llm_api
from auth_middleware import get_current_user
from config import unified_config_manager

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


def _client(monkeypatch, tree) -> TestClient:
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
    app.dependency_overrides[get_current_user] = lambda: {"username": "plain-user"}
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


def test_current_response_is_redacted_too_and_keeps_its_controls(monkeypatch) -> None:
    r = _client(monkeypatch, _BACKEND_LLM).get("/api/llm/current")
    assert r.status_code == 200
    assert "SENTINEL" not in r.text, r.text
    body = r.json()
    assert body["config"]["ollama"]["selected_model"] == _MODEL
    assert body["config"]["unified"]["cloud"]["providers"]["openai"]["model"] == "gpt-x"
