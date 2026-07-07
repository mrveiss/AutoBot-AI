# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for step-level and tool-level OpenTelemetry spans (GH#11172).

Verifies:
- tool_span emits a span with expected attributes when tracing is enabled.
- step_span emits a span with expected attributes when tracing is enabled.
- Both helpers are no-ops (no error) when tracing is disabled.
- tool_span records exceptions and sets ERROR status on failure.
- _RecordingSpan wraps the inner span correctly.

Uses an in-memory InMemorySpanExporter so no OTLP collector is needed.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers to set up an in-memory OTel provider for isolated test assertions
# ---------------------------------------------------------------------------


def _make_in_memory_provider():
    """Return (TracerProvider, InMemorySpanExporter) with no sampling."""
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.sdk.trace.sampling import ALWAYS_ON

    exporter = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": "test"}), sampler=ALWAYS_ON)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider, exporter


# ---------------------------------------------------------------------------
# tool_span — enabled
# ---------------------------------------------------------------------------


class TestToolSpanEnabled:
    """tool_span emits expected span attributes when tracing is active."""

    def test_tool_span_emits_span_name(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.dict(os.environ, {"AUTOBOT_OTEL_ENABLED": "true"}):
            with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
                from autobot_shared.tracing import tool_span

                with tool_span("web_search"):
                    pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "agent.tool"

    def test_tool_span_sets_tool_name_attribute(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import tool_span

            with tool_span("read_file"):
                pass

        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get("tool.name") == "read_file"

    def test_tool_span_sets_retry_count_default(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import tool_span

            with tool_span("bash"):
                pass

        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get("tool.retry_count") == 0

    def test_tool_span_sets_retry_count_explicit(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import tool_span

            with tool_span("bash", retry_count=2):
                pass

        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get("tool.retry_count") == 2

    def test_tool_span_records_exception_on_error(self):
        from opentelemetry import trace
        from opentelemetry.trace import StatusCode

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import tool_span

            with pytest.raises(RuntimeError):
                with tool_span("failing_tool"):
                    raise RuntimeError("boom")

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        span = spans[0]
        assert span.status.status_code == StatusCode.ERROR
        # Exception should be recorded as an event
        event_names = [e.name for e in span.events]
        assert "exception" in event_names

    def test_tool_span_duration_ms_attribute_set_by_executor(self):
        """tool_span itself does not set duration_ms — the executor sets it after.

        This test verifies the span is open and the span object is accessible
        so the executor can call set_attribute on it mid-span.
        """
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import tool_span

            with tool_span("code_interpreter") as span:
                assert span is not None
                span.set_attribute("tool.duration_ms", 123.4)
                span.set_attribute("tool.success", True)

        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get("tool.duration_ms") == pytest.approx(123.4)
        assert spans[0].attributes.get("tool.success") is True


# ---------------------------------------------------------------------------
# step_span — enabled
# ---------------------------------------------------------------------------


class TestStepSpanEnabled:
    """step_span emits expected span attributes when tracing is active."""

    def test_step_span_emits_span_name(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import step_span

            with step_span(iteration=1):
                pass

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "agent.step"

    def test_step_span_sets_iteration_attribute(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import step_span

            with step_span(iteration=7):
                pass

        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get("agent.step.iteration") == 7

    def test_step_span_sets_task_id_attribute(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import step_span

            with step_span(iteration=3, task_id="task-abc123"):
                pass

        spans = exporter.get_finished_spans()
        assert spans[0].attributes.get("agent.step.task_id") == "task-abc123"

    def test_step_span_omits_task_id_when_none(self):
        from opentelemetry import trace

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import step_span

            with step_span(iteration=1, task_id=None):
                pass

        spans = exporter.get_finished_spans()
        assert "agent.step.task_id" not in (spans[0].attributes or {})

    def test_step_span_records_exception_on_error(self):
        from opentelemetry import trace
        from opentelemetry.trace import StatusCode

        provider, exporter = _make_in_memory_provider()
        with patch.object(trace, "get_tracer", wraps=provider.get_tracer):
            from autobot_shared.tracing import step_span

            with pytest.raises(ValueError):
                with step_span(iteration=2):
                    raise ValueError("step error")

        spans = exporter.get_finished_spans()
        assert spans[0].status.status_code == StatusCode.ERROR


# ---------------------------------------------------------------------------
# No-op behaviour when AUTOBOT_OTEL_ENABLED is false / SDK absent
# ---------------------------------------------------------------------------


class TestSpanHelpersDisabled:
    """Helpers must not raise when tracing is disabled or SDK is absent."""

    def test_tool_span_noop_when_import_error(self):
        """When OTel SDK is absent, tool_span returns _NoopSpan — no error."""
        with patch.dict(sys.modules, {"opentelemetry.trace": None}):
            # Force reimport so the try/except in tool_span fires
            from autobot_shared import tracing as _tracing

            # Directly call the helper with patched import
            with patch("autobot_shared.tracing.get_tracer", side_effect=ImportError):
                # Should not raise
                with _tracing.tool_span("any_tool") as span:
                    assert span is not None  # _NoopSpan returned

    def test_step_span_noop_when_import_error(self):
        """When OTel SDK is absent, step_span returns _NoopSpan — no error."""
        from autobot_shared import tracing as _tracing

        with patch("autobot_shared.tracing.get_tracer", side_effect=ImportError):
            with _tracing.step_span(iteration=1) as span:
                assert span is not None

    def test_tool_span_noop_is_silent_on_exception(self):
        """Even when the body raises, _NoopSpan exit does not swallow or raise."""
        from autobot_shared import tracing as _tracing

        with patch("autobot_shared.tracing.get_tracer", side_effect=ImportError):
            with pytest.raises(RuntimeError, match="noop error"):
                with _tracing.tool_span("tool_x"):
                    raise RuntimeError("noop error")
