# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for ResponseQualityEvaluator error path (Issue #6697).

Pre-#6697 the evaluator's exception handler emitted::

    RLM evaluator failed:  — accepting response

with two bugs:
  1. Log said "accepting response" but the return verdict was FAIL.
  2. ``%s`` on the exception was empty when ``__str__`` returned ''
     (e.g. ``ConnectionError()`` with no args).

Fix: log ``type(exc).__name__`` + ``repr(exc)`` + ``exc_info=True``, return
``ReflectionVerdict.INDETERMINATE`` so callers can distinguish evaluator
failures from genuine FAIL verdicts.
"""

import logging
from unittest.mock import AsyncMock, patch

import pytest

from rlm.evaluator import ResponseQualityEvaluator
from rlm.types import ReflectionVerdict, RLMConfig


class TestEvaluatorErrorPath:
    """Issue #6697: log/verdict consistency on evaluator failure."""

    @pytest.mark.asyncio
    async def test_returns_indeterminate_when_llm_call_raises(self, caplog):
        """Evaluator infrastructure error → INDETERMINATE (not FAIL)."""
        evaluator = ResponseQualityEvaluator(config=RLMConfig())

        with patch.object(
            evaluator,
            "_call_llm",
            new=AsyncMock(side_effect=ConnectionError("ollama timeout")),
        ):
            with caplog.at_level(logging.WARNING):
                result = await evaluator.evaluate(query="What is 2+2?", response="Probably 5", iteration=1)

        assert result.verdict == ReflectionVerdict.INDETERMINATE
        assert "ConnectionError" in result.critique
        assert "ollama timeout" in result.critique

    @pytest.mark.asyncio
    async def test_log_includes_exception_type_when_str_is_empty(self, caplog):
        """Bug 2: empty ``__str__`` no longer produces blank log lines."""
        evaluator = ResponseQualityEvaluator(config=RLMConfig())

        # ConnectionError() with no args → __str__ returns ''. Pre-fix the
        # log was 'RLM evaluator failed:  — accepting response' (note the
        # double space).
        with patch.object(
            evaluator,
            "_call_llm",
            new=AsyncMock(side_effect=ConnectionError()),
        ):
            with caplog.at_level(logging.WARNING):
                result = await evaluator.evaluate(query="x", response="y", iteration=1)

        assert result.verdict == ReflectionVerdict.INDETERMINATE
        # Log must mention the exception type even when message is empty
        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any("ConnectionError" in r.getMessage() for r in warning_records), (
            "Warning log must include exception type even when str(exc) is empty; "
            f"got messages: {[r.getMessage() for r in warning_records]}"
        )

    @pytest.mark.asyncio
    async def test_log_message_matches_returned_verdict(self, caplog):
        """Bug 1: log says what the return value actually means."""
        evaluator = ResponseQualityEvaluator(config=RLMConfig())

        with patch.object(
            evaluator,
            "_call_llm",
            new=AsyncMock(side_effect=ValueError("parse error")),
        ):
            with caplog.at_level(logging.WARNING):
                result = await evaluator.evaluate(query="q", response="r", iteration=1)

        log_text = " ".join(r.getMessage() for r in caplog.records)
        # Either the log uses INDETERMINATE wording OR doesn't claim acceptance —
        # not the previous "accepting response" while returning FAIL.
        assert "INDETERMINATE" in log_text or "passing through" in log_text
        assert result.verdict == ReflectionVerdict.INDETERMINATE

    @pytest.mark.asyncio
    async def test_log_captures_traceback(self, caplog):
        """exc_info=True so debugging has a traceback to follow."""
        evaluator = ResponseQualityEvaluator(config=RLMConfig())

        def _raise():
            raise RuntimeError("boom")

        async def _broken_call(_prompt):
            _raise()

        with patch.object(evaluator, "_call_llm", new=AsyncMock(side_effect=_raise)):
            with caplog.at_level(logging.WARNING):
                await evaluator.evaluate(query="q", response="r", iteration=1)

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        # exc_info=True attaches an exc_info tuple to the LogRecord
        assert any(
            r.exc_info is not None for r in warning_records
        ), "exc_info=True must be set so traceback is captured"

    def test_indeterminate_value_exists_on_enum(self):
        """The new INDETERMINATE verdict must be on the enum."""
        assert hasattr(ReflectionVerdict, "INDETERMINATE")

    def test_existing_verdicts_preserved(self):
        """ACCEPT / REFINE / FAIL still exist (no breaking enum changes)."""
        assert hasattr(ReflectionVerdict, "ACCEPT")
        assert hasattr(ReflectionVerdict, "REFINE")
        assert hasattr(ReflectionVerdict, "FAIL")
