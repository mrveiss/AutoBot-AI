# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for time-to-first-token capture in streaming (#14211).

Before this fix, ``llm_shared/streaming.py`` never captured a first-chunk
timestamp, so ``autobot_llm_time_to_first_token_seconds`` stayed empty even
when a client streamed a real response (both TTFT dashboard panels rendered
No Data). ``process_llm_stream`` now returns the elapsed time to the first
non-empty content chunk as its third element.
"""

from __future__ import annotations

import asyncio

import pytest

from utils.async_stream_processor import process_llm_stream

_MIN_MEASURABLE_DELAY_SECONDS = 0.02


class _FakeStreamContent:
    """Minimal stand-in for ``aiohttp.ClientResponse.content``."""

    def __init__(self, chunks: list[bytes], delay_before_first: float = 0.0) -> None:
        self._chunks = chunks
        self._delay_before_first = delay_before_first

    def __aiter__(self):
        return self._generate()

    async def _generate(self):
        first = True
        for chunk in self._chunks:
            if first and self._delay_before_first:
                await asyncio.sleep(self._delay_before_first)
            first = False
            yield chunk


class _FakeResponse:
    def __init__(self, chunks: list[bytes], delay_before_first: float = 0.0) -> None:
        self.content = _FakeStreamContent(chunks, delay_before_first)


def _ollama_chunks() -> list[bytes]:
    return [
        b'{"message": {"content": "Hello"}}\n',
        b'{"message": {"content": " world"}}\n',
        b'{"done": true, "eval_count": 2, "eval_duration": 1000000}\n',
    ]


class TestTimeToFirstToken:
    """Guard: a completed streaming request observes a non-zero TTFT sample."""

    async def test_completed_stream_reports_positive_ttft(self):
        response = _FakeResponse(_ollama_chunks(), delay_before_first=_MIN_MEASURABLE_DELAY_SECONDS)

        content, completed_successfully, ttft_seconds = await process_llm_stream(response, provider="ollama")

        assert completed_successfully is True
        assert content == "Hello world"
        assert ttft_seconds is not None
        assert ttft_seconds > 0.0, "TTFT must be measurable once a content chunk has arrived (#14211)"
        # Sanity bound: TTFT should be roughly the injected delay, not the
        # whole stream duration (would indicate the *last* chunk was timed).
        assert ttft_seconds < 1.0

    async def test_stream_with_no_content_reports_no_ttft(self):
        """A stream that yields only control chunks (no content) has no TTFT to report."""
        response = _FakeResponse([b'{"done": true}\n'])

        _content, _completed, ttft_seconds = await process_llm_stream(response, provider="ollama")

        assert ttft_seconds is None

    async def test_non_streaming_path_has_no_ttft_by_construction(self):
        """process_llm_stream is only reached on the streaming path; a caller
        that never calls it (non-streaming requests) has no TTFT — verified
        via the default on LLMResponse.time_to_first_token_seconds."""
        from llm_shared.models import LLMResponse

        response = LLMResponse(content="ok")
        assert response.time_to_first_token_seconds is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
