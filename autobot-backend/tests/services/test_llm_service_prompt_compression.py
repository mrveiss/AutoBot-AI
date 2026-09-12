# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for extractive prompt compression wired into LLMService (#16526).

Covers:
- PromptCompressor is actually invoked on the chat() request path — the
  provider receives compressed, not raw, message content.
- Compression measurably reduces token count on a representative filler-heavy
  fixture (AC: compressed < original).
- A regression fixture with code blocks, a URL, and a technical identifier
  proves filler-phrase stripping does not corrupt dense technical/code
  content — preserved verbatim, as PromptCompressor.FILLER_PHRASES documents.
- config.llm_prompt_compression_enabled is a real kill switch.

Uses the same real-module-load harness as test_llm_service_caching.py so
``services.llm_service`` (globally stubbed in conftest.py) can be exercised
directly.
"""

from __future__ import annotations

import importlib.util as _ilu
import pathlib
import sys
from typing import Dict, List

import pytest

from autobot_shared.ssot_config import config
from llm_shared.models import LLMRequest, LLMResponse

_BACKEND = pathlib.Path(__file__).resolve().parents[2]  # autobot-backend/


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

_llm_service_mod = _load_real_module("_real_llm_service_16526", "services/llm_service.py")
LLMService = _llm_service_mod.LLMService


class _FakeProvider:
    """Minimal provider that records the request and returns a fixed reply."""

    provider_name = "fake"

    def __init__(self) -> None:
        self.calls = 0
        self.last_request: LLMRequest | None = None

    async def chat_completion(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        self.last_request = request
        return LLMResponse(
            content="hello world",
            model=request.model_name or "fake-default",
            provider=self.provider_name,
            request_id=request.request_id,
        )


class _FakeRegistry:
    def __init__(self, provider: _FakeProvider) -> None:
        self._provider = provider

    async def get_provider_for_request(self, provider_name=None, conversation_id=None):
        return self._provider

    def get_provider_by_name(self, name: str):
        return self._provider

    def list_providers(self):
        return [{"name": self._provider.provider_name}]


class _FakeCache:
    """No-op cache stand-in — these tests care about compression, not caching."""

    async def get(self, key):
        return None

    async def set(self, key, response, skip_redis: bool = False) -> None:
        return None

    def generate_cache_key(self, **kwargs) -> str:
        return "key"


def _make_service() -> tuple:
    provider = _FakeProvider()
    svc = LLMService(registry=_FakeRegistry(provider))
    svc._response_cache = _FakeCache()
    return svc, provider


# A filler-heavy fixture well over the 100-char compression floor.
_FILLER_HEAVY_MESSAGE = (
    "Please note that this is important. It is important to understand that "
    "the deployment pipeline works well across every environment we support. "
    "Keep in mind that transient errors may occur during a rollout. As you "
    "know, we should be careful when retrying. Basically, the retry logic "
    "already handles this case for us."
)

# A regression fixture: filler text around a code block, a URL, and a
# technical identifier ("implement") that must survive byte-for-byte.
_CODE_BLOCK = '```python\ndef implement_feature():\n    return "implement this correctly"\n```'
_URL = "https://example.internal/docs/implement-guide"
_DENSE_TECHNICAL_MESSAGE = (
    f"Please note that you should implement the fix below.\n{_CODE_BLOCK}\n"
    f"For reference, see {_URL} for the full implementation notes."
)


@pytest.mark.asyncio
async def test_chat_sends_compressed_content_to_provider():
    """The provider receives compressed content, not the raw prompt (#16526)."""
    svc, provider = _make_service()
    messages: List[Dict[str, str]] = [{"role": "user", "content": _FILLER_HEAVY_MESSAGE}]

    await svc.chat(messages, temperature=0.0, use_cache=False)

    sent_content = provider.last_request.messages[-1]["content"]
    assert sent_content != _FILLER_HEAVY_MESSAGE
    assert len(sent_content) < len(_FILLER_HEAVY_MESSAGE)
    assert "Please note that" not in sent_content


def test_compression_reduces_token_count_on_filler_heavy_fixture():
    """AC: compressed token count < original for a representative fixture."""
    svc, _ = _make_service()
    result = svc._prompt_compressor.compress(_FILLER_HEAVY_MESSAGE)

    assert result.compressed_tokens < result.original_tokens
    assert result.compressed_text != _FILLER_HEAVY_MESSAGE


def test_compression_preserves_code_blocks_and_urls_verbatim():
    """Regression (#16526): filler stripping must not corrupt dense
    technical/code content — code blocks and URLs come back byte-identical,
    and the in-code identifier ``implement`` is never rewritten (aggressive
    mode, the only path that would touch it, defaults off)."""
    svc, _ = _make_service()
    result = svc._prompt_compressor.compress(_DENSE_TECHNICAL_MESSAGE)

    assert _CODE_BLOCK in result.compressed_text
    assert _URL in result.compressed_text
    # Filler outside the preserved regions is still stripped.
    assert "Please note that" not in result.compressed_text


@pytest.mark.asyncio
async def test_short_messages_are_left_untouched():
    """Content under the min-length floor is a no-op — existing short-prompt
    tests (e.g. test_llm_service_caching.py) must see unchanged content."""
    svc, provider = _make_service()
    short = "hi there"

    await svc.chat([{"role": "user", "content": short}], temperature=0.0, use_cache=False)

    assert provider.last_request.messages[-1]["content"] == short


@pytest.mark.asyncio
async def test_compression_disabled_via_config_is_a_real_kill_switch(monkeypatch):
    """config.llm_prompt_compression_enabled is read live inside
    _compress_messages, not baked in at __init__: the service is constructed
    with compression ON, then disabled afterward, and that still takes
    effect — LLMService is a process-wide singleton (get_llm_service()), so
    a flag read only at construction would never see a later config change."""
    svc, provider = _make_service()
    monkeypatch.setattr(config, "llm_prompt_compression_enabled", False, raising=False)

    await svc.chat(
        [{"role": "user", "content": _FILLER_HEAVY_MESSAGE}],
        temperature=0.0,
        use_cache=False,
    )

    assert provider.last_request.messages[-1]["content"] == _FILLER_HEAVY_MESSAGE


@pytest.mark.asyncio
async def test_min_chars_is_read_live_too(monkeypatch):
    """Same live-read requirement for config.llm_prompt_compression_min_chars:
    lowering it after construction makes a message the original 100-char
    floor would have skipped get compressed on the very next call."""
    svc, provider = _make_service()
    short_message = "Please note that this is a test."  # 34 chars, under the default 100
    monkeypatch.setattr(config, "llm_prompt_compression_min_chars", 10, raising=False)

    await svc.chat([{"role": "user", "content": short_message}], temperature=0.0, use_cache=False)

    assert "Please note that" not in provider.last_request.messages[-1]["content"]


@pytest.mark.asyncio
async def test_compression_failure_falls_back_to_original_content(monkeypatch):
    """HIGH review finding on #16546 (eefaafb28): compress() has no exception
    handling and runs on every 100+ char message by default, so any
    exception (a regex edge case, a future phrase-list edit, non-string
    multimodal content) would propagate and fail the whole chat/stream
    request -- a cost optimisation failing closed. It must fail open like
    the sibling quota_headroom/provider_degradation checks: log and send the
    original content unchanged."""
    svc, provider = _make_service()

    def _raise(_content: str):
        raise RuntimeError("simulated compressor failure")

    monkeypatch.setattr(svc._prompt_compressor, "compress", _raise)

    await svc.chat(
        [{"role": "user", "content": _FILLER_HEAVY_MESSAGE}],
        temperature=0.0,
        use_cache=False,
    )

    assert provider.calls == 1
    assert provider.last_request.messages[-1]["content"] == _FILLER_HEAVY_MESSAGE


def test_compression_preserves_system_role_and_redaction_markers():
    """Regression requested on #16546's review: a system-role message
    carrying a #16545 PII-redaction marker (``[REDACTED:{type}]``, from
    a2a/pii_pipeline.py) must come out byte-identical -- today that's true
    only because rule-based compression happens to never touch bracket
    syntax, not because anything pins it."""
    svc, _ = _make_service()
    redacted_marker = "[REDACTED:EMAIL]"
    system_message = (
        "Please note that this is important. The user's contact on file is "
        f"{redacted_marker}. It is important to keep in mind that this value "
        "must never be logged or echoed back to the user."
    )
    assert len(system_message) >= 100  # over the default compression floor

    compressed = svc._compress_messages([{"role": "system", "content": system_message}])

    assert redacted_marker in compressed[0]["content"]
    assert compressed[0]["role"] == "system"
    # Filler outside the marker is still stripped, proving compression ran.
    assert "Please note that" not in compressed[0]["content"]
