# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FastAPI instrumentation options: excluded URLs and the AutoBot request-span hook (#21685)."""

import os
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from autobot_shared import tracing


def _http_scope(headers: dict[str, str], client: str = "10.0.0.9") -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": "/api/ping",
        "query_string": b"",
        "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
        "client": (client, 5000),
        "server": ("testserver", 80),
        "scheme": "http",
    }


def _recording_span() -> MagicMock:
    span = MagicMock()
    span.is_recording.return_value = True
    return span


def test_request_id_and_client_ip_become_span_attributes():
    span = _recording_span()
    tracing._server_request_hook(span, _http_scope({"X-Request-ID": "req-1"}))
    attrs = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
    assert attrs["autobot.request_id"] == "req-1"
    assert attrs["http.client_ip"] == "10.0.0.9"


def test_absent_request_id_is_not_recorded():
    span = _recording_span()
    tracing._server_request_hook(span, _http_scope({}))
    assert "autobot.request_id" not in {c.args[0] for c in span.set_attribute.call_args_list}


def test_forwarded_for_is_ignored_from_an_untrusted_peer():
    span = _recording_span()
    tracing._server_request_hook(span, _http_scope({"X-Forwarded-For": "203.0.113.7"}))
    assert ("http.client_ip", "10.0.0.9") in [c.args for c in span.set_attribute.call_args_list]


@pytest.mark.parametrize("scope", [{"type": "websocket", "headers": []}, {"type": "lifespan"}])
def test_non_http_scopes_are_left_alone(scope):
    span = _recording_span()
    tracing._server_request_hook(span, scope)
    span.set_attribute.assert_not_called()


def test_a_span_that_is_not_recording_is_left_alone():
    span = MagicMock()
    span.is_recording.return_value = False
    tracing._server_request_hook(span, _http_scope({"X-Request-ID": "r"}))
    span.set_attribute.assert_not_called()


def test_a_broken_scope_never_raises():
    tracing._server_request_hook(_recording_span(), {"type": "http", "headers": "not-a-list"})


def test_health_and_metrics_are_excluded():
    excluded = tracing.fastapi_instrumentation_kwargs()["excluded_urls"].split(",")
    assert {"/health", "/api/health", "/metrics", "/api/metrics"} <= set(excluded)


def test_instrument_fastapi_passes_the_shared_options(monkeypatch):
    monkeypatch.setenv("AUTOBOT_OTEL_ENABLED", "true")
    instrumentor = MagicMock()
    module = types.ModuleType("opentelemetry.instrumentation.fastapi")
    module.FastAPIInstrumentor = instrumentor
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.fastapi", module)
    app = object()
    assert tracing.instrument_fastapi(app) is True
    instrumentor.instrument_app.assert_called_once()
    kwargs = instrumentor.instrument_app.call_args.kwargs
    assert instrumentor.instrument_app.call_args.args == (app,)
    assert kwargs["server_request_hook"] is tracing._server_request_hook
    assert "/health" in kwargs["excluded_urls"]


# --- one provider: what the retired TracingService also did (#21685) ---------------------------


def test_trace_context_headers_carry_the_active_span():
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider

    tracer = TracerProvider().get_tracer("t")
    with tracer.start_as_current_span("s"):
        assert "traceparent" in tracing.get_trace_context()


def test_trace_context_is_empty_outside_a_span():
    pytest.importorskip("opentelemetry.sdk.trace")
    assert "traceparent" not in tracing.get_trace_context()


def test_propagators_include_w3c_trace_context():
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.propagate import get_global_textmap, set_global_textmap

    previous = get_global_textmap()
    try:
        tracing._install_propagators()
        assert "traceparent" in get_global_textmap().fields
    finally:
        set_global_textmap(previous)


def test_console_exporter_is_added_only_when_asked(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    from autobot_shared.ssot_config import config

    provider = MagicMock()
    monkeypatch.setattr(config, "trace_console", "")
    tracing._add_console_exporter(provider)
    provider.add_span_processor.assert_not_called()
    monkeypatch.setattr(config, "trace_console", "true")
    tracing._add_console_exporter(provider)
    provider.add_span_processor.assert_called_once()


def test_exporter_endpoint_falls_back_to_the_jaeger_setting(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.delenv("AUTOBOT_OTEL_ENDPOINT", raising=False)
    monkeypatch.setattr(config.misc, "jaeger_endpoint", "")
    assert tracing._create_exporter() is None
    monkeypatch.setattr(config.misc, "jaeger_endpoint", "collector:4317")
    exporter = tracing._create_exporter()
    assert exporter is not None


def test_provider_resource_carries_the_autobot_namespace(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    monkeypatch.delenv("AUTOBOT_OTEL_ENDPOINT", raising=False)
    provider = tracing._create_tracer_provider("svc", "1.0")
    assert provider.resource.attributes["service.namespace"] == "autobot"
    assert provider.resource.attributes["service.name"] == "svc"


# --- one sampling setting; the old name is a deprecated alias (#21685) -------------------------


def _rate_with(monkeypatch, env: dict):
    from autobot_shared.ssot_config import MiscConfig, config

    with patch.dict(os.environ, env, clear=True):
        monkeypatch.setattr(config, "misc", MiscConfig(_env_file=None))
        return tracing._get_sample_rate()


def test_the_canonical_sample_rate_is_used(monkeypatch, caplog):
    assert _rate_with(monkeypatch, {"AUTOBOT_OTEL_SAMPLE_RATE": "0.4"}) == 0.4
    assert "deprecated" not in caplog.text


def test_only_the_deprecated_alias_is_used_and_warns(monkeypatch, caplog):
    with caplog.at_level("WARNING"):
        assert _rate_with(monkeypatch, {"AUTOBOT_TRACE_SAMPLE_RATE": "0.7"}) == 0.7
    assert "AUTOBOT_TRACE_SAMPLE_RATE is deprecated" in caplog.text
    assert "AUTOBOT_OTEL_SAMPLE_RATE" in caplog.text


def test_the_canonical_name_wins_when_both_are_set(monkeypatch, caplog):
    env = {"AUTOBOT_OTEL_SAMPLE_RATE": "0.2", "AUTOBOT_TRACE_SAMPLE_RATE": "0.9"}
    with caplog.at_level("WARNING"):
        assert _rate_with(monkeypatch, env) == 0.2
    assert "deprecated" not in caplog.text


def test_neither_set_gives_the_default(monkeypatch):
    assert _rate_with(monkeypatch, {}) == 0.1


def test_an_unreadable_rate_falls_back_to_the_default(monkeypatch):
    assert _rate_with(monkeypatch, {"AUTOBOT_OTEL_SAMPLE_RATE": "lots"}) == 0.1


def test_a_rate_is_clamped_to_the_unit_interval(monkeypatch):
    assert _rate_with(monkeypatch, {"AUTOBOT_OTEL_SAMPLE_RATE": "7"}) == 1.0


def test_the_deprecated_jaeger_endpoint_is_used_only_when_canonical_is_unset(monkeypatch, caplog):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "jaeger_endpoint", "legacy:4317")
    monkeypatch.setenv("AUTOBOT_OTEL_ENDPOINT", "canonical:4317")
    with caplog.at_level("WARNING"):
        tracing._create_exporter()
    assert "AUTOBOT_JAEGER_ENDPOINT is deprecated" not in caplog.text
    monkeypatch.delenv("AUTOBOT_OTEL_ENDPOINT")
    with caplog.at_level("WARNING"):
        tracing._create_exporter()
    assert "AUTOBOT_JAEGER_ENDPOINT is deprecated" in caplog.text
