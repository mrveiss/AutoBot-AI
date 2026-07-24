# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Unit tests for embedding-fallback failure visibility and retry — Issue #12312.

Regression guard for the four previously-unlogged failure paths in
``generate_embedding_with_fallback`` that silently dropped 130 vectors:
  - every failure route is logged with a diagnosable reason;
  - the whole NPU->Ollama attempt is retried with backoff before giving up;
  - the terminal ``return None`` is loud (ERROR with model + reason + text prefix)
    so a dropped vector is never undiagnosable.
"""

from __future__ import annotations

import logging
import sys

import pytest

# The conftest `services` package stub means ``from services import npu_client``
# yields a stub attribute, not the loaded submodule. Bind the real module via
# sys.modules so monkeypatch targets the same dict the functions resolve globals in.
from services.npu_client import _try_ollama_embedding, generate_embedding_with_fallback  # noqa: F401

npu_client = sys.modules["services.npu_client"]

VALID_EMBEDDING = [0.1, 0.2, 0.3]


@pytest.fixture(autouse=True)
def _no_backoff_sleep(monkeypatch):
    """Keep tests instant: zero backoff sleep between attempts."""
    monkeypatch.setattr(npu_client, "EMBEDDING_RETRY_BASE_DELAY", 0.0)


def _npu_unavailable(monkeypatch):
    """Force the NPU branch to be skipped so Ollama drives the outcome."""

    class _Client:
        async def is_available(self):
            return False

        async def generate_embedding(self, *_a, **_k):
            return None

    monkeypatch.setattr(npu_client, "get_npu_client", lambda: _Client())


class TestFailureIsSurfacedAndRetried:
    @pytest.mark.asyncio
    async def test_inline_default_is_single_attempt_fast_fail(self, monkeypatch, caplog):
        """Issue #12312 regression: the inline default must NOT retry — one attempt only,
        so a downed backend cannot stall a user-facing request with an N-attempt wait."""
        _npu_unavailable(monkeypatch)

        calls = {"n": 0}

        async def _always_fail(_text, _model, _url):
            calls["n"] += 1
            return None, "Ollama HTTP 503: b'model is loading'"

        monkeypatch.setattr(npu_client, "_try_ollama_embedding", _always_fail)

        with caplog.at_level(logging.WARNING):
            result = await generate_embedding_with_fallback("hello")  # default max_attempts=1

        assert result is None
        assert calls["n"] == 1  # exactly one attempt — no inline retry wait
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert any("FAILED after 1 attempt" in r.getMessage() for r in errors)

    @pytest.mark.asyncio
    async def test_background_all_attempts_fail_returns_none_and_logs_error(self, monkeypatch, caplog):
        _npu_unavailable(monkeypatch)

        calls = {"n": 0}

        async def _always_fail(_text, _model, _url):
            calls["n"] += 1
            return None, "Ollama HTTP 503: b'model is loading'"

        monkeypatch.setattr(npu_client, "_try_ollama_embedding", _always_fail)

        with caplog.at_level(logging.WARNING):
            result = await generate_embedding_with_fallback("hello", max_attempts=3)

        # Failure is surfaced to the caller (None), NOT a silent empty success.
        assert result is None
        # Retried the requested number of attempts before giving up.
        assert calls["n"] == 3
        # Every failed attempt is logged with its reason (no silent fall-through).
        assert sum("attempt" in r.message.lower() for r in caplog.records) >= 3
        assert any("503" in r.getMessage() for r in caplog.records)
        # Terminal give-up is a loud ERROR naming the model + reason.
        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "terminal failure must log at ERROR level"
        assert any("FAILED after" in r.getMessage() for r in errors)

    @pytest.mark.asyncio
    async def test_retry_recovers_on_later_attempt(self, monkeypatch, caplog):
        _npu_unavailable(monkeypatch)

        calls = {"n": 0}

        async def _fail_then_succeed(_text, _model, _url):
            calls["n"] += 1
            if calls["n"] < 2:
                return None, "Ollama request error: timeout"
            return list(VALID_EMBEDDING), ""

        monkeypatch.setattr(npu_client, "_try_ollama_embedding", _fail_then_succeed)

        result = await generate_embedding_with_fallback("hello", max_attempts=3)

        assert result == VALID_EMBEDDING
        assert calls["n"] == 2  # first attempt failed, second recovered

    @pytest.mark.asyncio
    async def test_success_on_first_attempt_no_error(self, monkeypatch):
        _npu_unavailable(monkeypatch)

        async def _ok(_text, _model, _url):
            return list(VALID_EMBEDDING), ""

        monkeypatch.setattr(npu_client, "_try_ollama_embedding", _ok)

        assert await generate_embedding_with_fallback("hello") == VALID_EMBEDDING


class TestOllamaAttemptReasons:
    """_try_ollama_embedding must distinguish each failure route with a reason."""

    @pytest.mark.asyncio
    async def test_non_200_reports_status_and_body(self, monkeypatch):
        embedding, reason = await self._run_with_response(monkeypatch, status=503, payload={"error": "loading"})
        assert embedding is None
        assert "503" in reason

    @pytest.mark.asyncio
    async def test_200_empty_embedding_reports_reason(self, monkeypatch):
        embedding, reason = await self._run_with_response(monkeypatch, status=200, payload={"embedding": []})
        assert embedding is None
        assert "empty" in reason.lower()

    @pytest.mark.asyncio
    async def test_200_valid_embedding_returns_vector(self, monkeypatch):
        embedding, reason = await self._run_with_response(
            monkeypatch, status=200, payload={"embedding": VALID_EMBEDDING}
        )
        assert embedding == VALID_EMBEDDING
        assert reason == ""

    async def _run_with_response(self, monkeypatch, status, payload):
        """Drive _try_ollama_embedding against a fake aiohttp response."""

        class _Resp:
            def __init__(self):
                self.status = status

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

            async def json(self):
                return payload

            async def text(self):
                return str(payload)

        class _Session:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_a):
                return False

            def post(self, *_a, **_k):
                return _Resp()

        monkeypatch.setattr(npu_client.aiohttp, "ClientSession", lambda *a, **k: _Session())
        return await _try_ollama_embedding("hello", "nomic-embed-text", "http://x/api/embeddings")
