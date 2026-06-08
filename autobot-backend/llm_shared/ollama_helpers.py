# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Shared narrow Ollama /api/generate transport.

Used by modules that need a one-shot prompt completion without invoking
the full OllamaProvider / LLMInterface stack (e.g. RAG refiner, query
evaluator, agentic search query rewriter).

Issue #5102: three near-identical ``_call_llm`` methods collapsed into
this single helper.

Moved from llm_providers/ as part of Phase 2 consolidation (MVA-178 / GH#7637).
"""

from __future__ import annotations

import httpx


async def call_ollama_generate(
    prompt: str,
    model: str,
    base_url: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 512,
    timeout_ms: int = 30000,
) -> str:
    """POST /api/generate to Ollama and return the ``response`` field.

    Args:
        prompt:       Raw prompt text to send.
        model:        Ollama model tag (e.g. ``llama3.2:latest``).
        base_url:     Ollama server URL (no trailing slash required).
        temperature:  Sampling temperature forwarded as ``options.temperature``.
        max_tokens:   Token budget forwarded as ``options.num_predict``.
        timeout_ms:   Per-request timeout in milliseconds.

    Returns:
        The string value of the ``response`` key, or an empty string when
        the response body lacks that key.

    Raises:
        httpx.HTTPError: On transport failure or non-2xx HTTP status.
            Callers are expected to catch and fall back as appropriate.
    """
    url = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
            "num_predict": max_tokens,
        },
    }
    timeout = httpx.Timeout(timeout_ms / 1000.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "")
