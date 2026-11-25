# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""FastAPI instrumentation options: excluded URLs and the AutoBot request-span hook (#21685)."""

import os
import re
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
    patterns = [re.compile(p) for p in tracing.fastapi_instrumentation_kwargs()["excluded_urls"].split(",")]
    for url in ("/health", "/api/health", "/metrics", "/api/metrics"):
        assert any(p.search(url) for p in patterns), url


def test_instrument_fastapi_passes_the_shared_options(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "otel_enabled", "true")
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
    assert kwargs["excluded_urls"] == tracing._EXCLUDED_URLS


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

    monkeypatch.setattr(config.misc, "otel_endpoint", "")
    monkeypatch.setattr(config.misc, "jaeger_endpoint", "")
    assert tracing._create_exporter() is None
    monkeypatch.setattr(config.misc, "jaeger_endpoint", "collector:4317")
    exporter = tracing._create_exporter()
    assert exporter is not None


def test_provider_resource_carries_the_autobot_namespace(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
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
    monkeypatch.setattr(config.misc, "otel_endpoint", "canonical:4317")
    with caplog.at_level("WARNING"):
        tracing._create_exporter()
    assert "AUTOBOT_JAEGER_ENDPOINT is deprecated" not in caplog.text
    monkeypatch.setattr(config.misc, "otel_endpoint", "")
    with caplog.at_level("WARNING"):
        tracing._create_exporter()
    assert "AUTOBOT_JAEGER_ENDPOINT is deprecated" in caplog.text


# --- sampling extremes, SSOT-read settings, URL patterns, request id (#21685) ----------------


@pytest.mark.parametrize(
    "rate,expected", [(0.0, "ALWAYS_OFF"), (-1.0, "ALWAYS_OFF"), (1.0, "ALWAYS_ON"), (3.0, "ALWAYS_ON")]
)
def test_the_extreme_rates_ignore_an_inbound_sampled_parent(rate, expected):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON

    assert tracing._sampler_for(rate) is {"ALWAYS_OFF": ALWAYS_OFF, "ALWAYS_ON": ALWAYS_ON}[expected]


def test_a_sampled_parent_cannot_force_export_at_rate_zero():
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    sampler = tracing._sampler_for(0.0)
    sampled_parent = trace.set_span_in_context(
        trace.NonRecordingSpan(
            trace.SpanContext(
                trace_id=1, span_id=2, is_remote=True, trace_flags=trace.TraceFlags(trace.TraceFlags.SAMPLED)
            )
        )
    )
    spans = []
    provider = TracerProvider(sampler=sampler)
    with provider.get_tracer("t").start_as_current_span("s", context=sampled_parent) as span:
        spans.append(span)
    assert not spans[0].get_span_context().trace_flags.sampled


def test_a_middle_rate_still_follows_the_parent():
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

    assert isinstance(tracing._sampler_for(0.5), ParentBasedTraceIdRatio)


def test_enabled_and_endpoint_values_in_a_dotenv_file_are_honoured(tmp_path):
    from autobot_shared.ssot_config import MiscConfig

    env_file = tmp_path / ".env"
    env_file.write_text(
        "AUTOBOT_OTEL_ENABLED=true\nAUTOBOT_OTEL_ENDPOINT=collector:4317\nAUTOBOT_OTEL_SERVICE_VERSION=9.9.9\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {}, clear=True):
        cfg = MiscConfig(_env_file=str(env_file))
    assert cfg.otel_enabled == "true"
    assert cfg.otel_endpoint == "collector:4317"
    assert cfg.otel_service_version == "9.9.9"


def test_tracing_reads_enabled_through_the_ssot_settings(monkeypatch):
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "otel_enabled", "TRUE")
    assert tracing._is_otel_enabled() is True
    monkeypatch.setattr(config.misc, "otel_enabled", "false")
    assert tracing._is_otel_enabled() is False


@pytest.mark.parametrize("url", ["/health", "/health?probe=1", "http://host:8000/health", "/api/health/", "/metrics"])
def test_excluded_urls_match_probes_in_path_or_full_url_form(url):
    patterns = [re.compile(p) for p in tracing._EXCLUDED_URLS.split(",")]
    assert any(p.search(url) for p in patterns), url


@pytest.mark.parametrize(
    "url", ["/api/healthcheck", "/api/chat/health-summary", "/api/metrics-export", "/api/static-analysis"]
)
def test_excluded_urls_do_not_swallow_real_routes(url):
    patterns = [re.compile(p) for p in tracing._EXCLUDED_URLS.split(",")]
    assert not any(p.search(url) for p in patterns), url


def test_a_long_request_id_is_truncated():
    span = _recording_span()
    tracing._server_request_hook(span, _http_scope({"X-Request-ID": "x" * 5000}))
    recorded = {c.args[0]: c.args[1] for c in span.set_attribute.call_args_list}
    assert len(recorded["autobot.request_id"]) == tracing._MAX_REQUEST_ID_CHARS


@pytest.mark.asyncio
async def test_the_guarded_outbound_client_carries_the_active_trace_context():
    """``HTTPClientManager.request`` sends the same headers ``get_trace_context`` builds (one propagation path)."""
    pytest.importorskip("opentelemetry.sdk.trace")
    from unittest.mock import AsyncMock

    from opentelemetry.sdk.trace import TracerProvider

    from autobot_shared.http_client_manager import HTTPClientManager

    manager = HTTPClientManager.__new__(HTTPClientManager)
    session = MagicMock()
    session.request = AsyncMock(return_value="response")
    manager.get_session = AsyncMock(return_value=session)
    manager.increment_active = AsyncMock()
    manager._adjust_pool_size = AsyncMock()

    with TracerProvider().get_tracer("t").start_as_current_span("outbound"):
        await manager.request("GET", "http://service.internal/ping", headers={"X-Own": "1"})
    sent = session.request.call_args.kwargs["headers"]
    assert "traceparent" in sent and sent["X-Own"] == "1"

    await manager.request("GET", "http://service.internal/ping")  # no active span: nothing to propagate
    assert "traceparent" not in session.request.call_args.kwargs["headers"]


def test_the_service_version_comes_from_the_ssot_settings(monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.misc, "otel_service_version", "4.5.6")
    provider = tracing._create_tracer_provider("svc", None)
    assert provider.resource.attributes["service.version"] == "4.5.6"
    assert tracing._create_tracer_provider("svc", "7.0").resource.attributes["service.version"] == "7.0"


@pytest.mark.asyncio
async def test_a_caller_supplied_trace_header_is_kept_and_its_dict_is_not_mutated():
    pytest.importorskip("opentelemetry.sdk.trace")
    from unittest.mock import AsyncMock

    from opentelemetry.sdk.trace import TracerProvider

    from autobot_shared.http_client_manager import HTTPClientManager

    manager = HTTPClientManager.__new__(HTTPClientManager)
    session = MagicMock()
    session.request = AsyncMock(return_value="response")
    manager.get_session = AsyncMock(return_value=session)
    manager.increment_active = AsyncMock()
    manager._adjust_pool_size = AsyncMock()

    caller_headers = {"TraceParent": "00-caller-trace-01", "X-Own": "1"}
    with TracerProvider().get_tracer("t").start_as_current_span("outbound"):
        await manager.request("GET", "http://service.internal/ping", headers=caller_headers)

    sent = session.request.call_args.kwargs["headers"]
    assert sent["TraceParent"] == "00-caller-trace-01"
    assert "traceparent" not in sent  # no second, differently-cased copy
    assert sent["X-Own"] == "1"
    assert caller_headers == {"TraceParent": "00-caller-trace-01", "X-Own": "1"}  # the caller's dict is untouched


@pytest.mark.asyncio
async def test_a_real_instrumentor_traces_api_routes_and_skips_health():
    """Drives the real FastAPIInstrumentor, so the URL form it matches the exclusion patterns against is proven."""
    pytest.importorskip("opentelemetry.instrumentation.fastapi")
    import httpx
    from fastapi import FastAPI
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.trace import SpanKind

    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    app = FastAPI()

    @app.get("/health")
    async def health():
        return {"ok": True}

    @app.get("/api/x")
    async def api_x():
        return {"ok": True}

    FastAPIInstrumentor.instrument_app(app, tracer_provider=provider, **tracing.fastapi_instrumentation_kwargs())
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            await client.get("/health")
            await client.get("/api/x", headers={"X-Request-ID": "req-7"})
    finally:
        FastAPIInstrumentor.uninstrument_app(app)

    # Newer instrumentor releases also emit internal "<route> http send/receive" child spans; only the SERVER span is a request.
    server_spans = [s for s in exporter.get_finished_spans() if s.kind == SpanKind.SERVER]
    assert [s.name for s in server_spans] == ["GET /api/x"]
    assert server_spans[0].attributes["autobot.request_id"] == "req-7"
