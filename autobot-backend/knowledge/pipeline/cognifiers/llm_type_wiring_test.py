# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Cognifier LLM calls pass the correct llm_type (#10639).

llm_type drives per-task sampling defaults (lower temperature for extraction)
and, via #10597, makes low-temperature extraction calls cacheable. These tests
pin the task type each cognifier sends so it can't silently regress to GENERAL.
"""

from __future__ import annotations

import types
from unittest.mock import AsyncMock

import pytest

from knowledge.pipeline.cognifiers.context_generator import ContextGeneratorCognifier
from knowledge.pipeline.cognifiers.entity_extractor import EntityExtractor
from knowledge.pipeline.cognifiers.fact_extractor import FactExtractor


def _chunk(text: str = "some text"):
    return types.SimpleNamespace(content=text, id="c1")


def _ctx():
    return types.SimpleNamespace(document_id="d1")


@pytest.mark.asyncio
async def test_fact_extractor_uses_extraction_llm_type():
    ext = FactExtractor.__new__(FactExtractor)  # bypass heavy __init__
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content="[]")))

    await ext._extract_from_chunk(_chunk(), _ctx())

    _, kwargs = ext.llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"


@pytest.mark.asyncio
async def test_context_generator_uses_analysis_llm_type():
    # analysis-typed cognifier — the cache-consequential branch (temp 0.4 → not cached).
    gen = ContextGeneratorCognifier.__new__(ContextGeneratorCognifier)
    gen.llm = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content="a summary")))

    out = await gen._call_llm_for_summary("some document text")

    assert out == "a summary"
    _, kwargs = gen.llm.chat.call_args
    assert kwargs.get("llm_type") == "analysis"


@pytest.mark.asyncio
async def test_entity_extractor_uses_extraction_llm_type():
    ext = EntityExtractor.__new__(EntityExtractor)
    ext.llm = types.SimpleNamespace(chat=AsyncMock(return_value=types.SimpleNamespace(content="[]")))

    await ext._extract_from_chunk(_chunk(), _ctx())

    _, kwargs = ext.llm.chat.call_args
    assert kwargs.get("llm_type") == "extraction"
