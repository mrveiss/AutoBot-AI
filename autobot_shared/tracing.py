# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
OpenTelemetry Distributed Tracing Module (Issue #697)
=====================================================

Provides centralized tracing initialization for all AutoBot services.
Handles trace context propagation across the distributed VM architecture.

Usage:
    from autobot_shared.tracing import init_tracing, get_tracer

    # Initialize once at app startup
    init_tracing(service_name="autobot-backend")

    # Get a tracer for creating custom spans
    tracer = get_tracer(__name__)

    # Create custom spans
    with tracer.start_as_current_span("my.operation") as span:
        span.set_attribute("key", "value")
        result = do_work()

Configuration via environment variables:
    AUTOBOT_OTEL_ENABLED=true              # Enable/disable tracing
    AUTOBOT_OTEL_ENDPOINT=localhost:4317   # OTLP collector endpoint
    AUTOBOT_OTEL_PROTOCOL=grpc            # Export protocol (grpc|http)
    AUTOBOT_OTEL_SAMPLE_RATE=0.1          # Sampling rate (0.0-1.0)
    AUTOBOT_OTEL_SERVICE_VERSION=1.5.0    # Service version tag
"""

import logging
import os

logger = logging.getLogger(__name__)

# Lazy-loaded OpenTelemetry imports (graceful degradation if not installed)
_tracer_provider = None
_initialized = False

# Noop tracer for when OTel is disabled or unavailable
_NOOP_TRACER = None


def _is_otel_enabled() -> bool:
    """Check if OpenTelemetry tracing is enabled via environment."""
    return os.getenv("AUTOBOT_OTEL_ENABLED", "false").lower() == "true"


def _get_sample_rate() -> float:
    """Get configured sampling rate."""
    try:
        rate = float(os.getenv("AUTOBOT_OTEL_SAMPLE_RATE", "0.1"))
        return max(0.0, min(1.0, rate))
    except ValueError:
        return 0.1


def _create_tracer_provider(service_name: str, service_version: str | None):
    """
    Create and configure the TracerProvider with resource, sampler, and exporter.

    Helper for init_tracing (Issue #697).

    Args:
        service_name: Name of the service
        service_version: Service version tag

    Returns:
        Configured TracerProvider instance
    """
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

    version = service_version or os.getenv("AUTOBOT_OTEL_SERVICE_VERSION", "1.5.0")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.version": version,  # type: ignore[dict-item]  # GH#7105: OTel stubs expect int|float|Sequence; str valid at runtime  # noqa: E501
            "deployment.environment": os.getenv("AUTOBOT_ENVIRONMENT", "development"),
        }
    )

    sample_rate = _get_sample_rate()
    sampler = ParentBasedTraceIdRatio(sample_rate)

    provider = TracerProvider(resource=resource, sampler=sampler)

    exporter = _create_exporter()
    if exporter:
        provider.add_span_processor(BatchSpanProcessor(exporter))

    logger.info(
        "OpenTelemetry tracing initialized: service=%s, " "sample_rate=%.1f%%, exporter=%s",
        service_name,
        sample_rate * 100,
        "otlp" if exporter else "none",
    )
    return provider


def init_tracing(
    service_name: str = "autobot-backend",
    service_version: str | None = None,
) -> bool:
    """
    Initialize OpenTelemetry tracing for a service.

    Must be called once at application startup, before any spans are created.
    Safe to call multiple times (idempotent).

    Args:
        service_name: Name of the service (appears in traces)
        service_version: Service version tag

    Returns:
        True if tracing was initialized, False if disabled or unavailable
    """
    global _tracer_provider, _initialized

    if _initialized:
        return _tracer_provider is not None

    _initialized = True

    if not _is_otel_enabled():
        logger.info("OpenTelemetry tracing disabled (AUTOBOT_OTEL_ENABLED != true)")
        return False

    try:
        from opentelemetry import trace
    except ImportError:
        logger.warning(
            "OpenTelemetry SDK not installed. " "Install with: pip install opentelemetry-sdk opentelemetry-api"
        )
        return False

    try:
        _tracer_provider = _create_tracer_provider(service_name, service_version)
        trace.set_tracer_provider(_tracer_provider)
        return True
    except Exception as e:
        logger.error("Failed to initialize OpenTelemetry tracing: %s", e)
        _tracer_provider = None
        return False


def _create_exporter():
    """
    Create the OTLP span exporter based on configuration.

    Returns:
        SpanExporter instance or None if configuration is missing
    """
    endpoint = os.getenv("AUTOBOT_OTEL_ENDPOINT")
    if not endpoint:
        logger.info("No AUTOBOT_OTEL_ENDPOINT configured, traces will not be exported")
        return None

    protocol = os.getenv("AUTOBOT_OTEL_PROTOCOL", "grpc").lower()  # ssot-config-exempt: pre-init OTEL

    try:
        if protocol == "http":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            if not endpoint.startswith("http"):
                endpoint = f"http://{endpoint}"
            return OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            return OTLPSpanExporter(endpoint=endpoint, insecure=True)

    except ImportError:
        logger.warning("OTLP exporter not installed. " "Install with: pip install opentelemetry-exporter-otlp")
        return None
    except Exception as e:
        logger.error("Failed to create OTLP exporter: %s", e)
        return None


def get_tracer(name: str = __name__):
    """
    Get a tracer instance for creating spans.

    Safe to call whether or not tracing is initialized.
    Returns a noop tracer if OTel is disabled.

    Args:
        name: Tracer name (typically __name__ of the calling module)

    Returns:
        opentelemetry.trace.Tracer instance (real or noop)
    """
    try:
        from opentelemetry import trace

        return trace.get_tracer(name)
    except ImportError:
        return _get_noop_tracer()


def _get_noop_tracer():
    """Get a noop tracer that creates no-op spans."""
    global _NOOP_TRACER
    if _NOOP_TRACER is None:
        _NOOP_TRACER = _NoopTracer()
    return _NOOP_TRACER


class _NoopSpan:
    """No-op span for when tracing is unavailable."""

    def set_attribute(self, key, value) -> None:
        """No-op."""

    def set_status(self, status) -> None:
        """No-op."""

    def record_exception(self, exception) -> None:
        """No-op."""

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, *args) -> None:
        """Context manager exit."""


class _NoopTracer:
    """No-op tracer for when OpenTelemetry is unavailable."""

    def start_as_current_span(self, name, **kwargs):
        """Return a no-op span context manager."""
        return _NoopSpan()

    def start_span(self, name, **kwargs):
        """Return a no-op span."""
        return _NoopSpan()


def instrument_fastapi(app) -> bool:
    """
    Apply OpenTelemetry auto-instrumentation to a FastAPI app.

    Args:
        app: FastAPI application instance

    Returns:
        True if instrumentation was applied
    """
    if not _is_otel_enabled():
        return False

    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI auto-instrumentation applied")
        return True
    except ImportError:
        logger.debug("FastAPI OTel instrumentation not installed")
        return False
    except Exception as e:
        logger.warning("Failed to instrument FastAPI: %s", e)
        return False


def instrument_redis() -> bool:
    """
    Apply OpenTelemetry auto-instrumentation to Redis clients.

    Returns:
        True if instrumentation was applied
    """
    if not _is_otel_enabled():
        return False

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        logger.info("Redis auto-instrumentation applied")
        return True
    except ImportError:
        logger.debug("Redis OTel instrumentation not installed")
        return False
    except Exception as e:
        logger.warning("Failed to instrument Redis: %s", e)
        return False


def instrument_aiohttp() -> bool:
    """
    Apply OpenTelemetry auto-instrumentation to aiohttp client sessions.

    Returns:
        True if instrumentation was applied
    """
    if not _is_otel_enabled():
        return False

    try:
        from opentelemetry.instrumentation.aiohttp_client import (
            AioHttpClientInstrumentor,
        )

        AioHttpClientInstrumentor().instrument()
        logger.info("aiohttp client auto-instrumentation applied")
        return True
    except ImportError:
        logger.debug("aiohttp OTel instrumentation not installed")
        return False
    except Exception as e:
        logger.warning("Failed to instrument aiohttp: %s", e)
        return False


def tool_span(tool_name: str, retry_count: int = 0):
    """Context manager emitting an ``agent.tool`` span with standard attributes.

    Matches the attribute-naming style of OTELObserver (``llm.*``).  Records the
    exception and sets ERROR status on exit when the body raises.  Is a no-op when
    tracing is disabled or the OpenTelemetry SDK is absent — no import penalty.

    Args:
        tool_name: Name of the tool being invoked (``tool.name`` attribute).
        retry_count: How many times this call has already been retried (``tool.retry_count``).

    Returns:
        A synchronous context manager (``start_as_current_span`` is sync-compatible).
    """
    try:
        from opentelemetry.trace import SpanKind

        tracer = get_tracer("autobot.agent_loop")
        attrs = {"tool.name": tool_name, "tool.retry_count": retry_count}
        return _RecordingSpan(tracer.start_as_current_span("agent.tool", kind=SpanKind.INTERNAL, attributes=attrs))
    except ImportError:
        return _NoopSpan()


def step_span(iteration: int, task_id: str | None = None):
    """Context manager emitting an ``agent.step`` span for a single loop iteration.

    Wraps the full per-step boundary so all child spans (tool calls, LLM calls) are
    nested beneath it.  Is a no-op when tracing is disabled or the SDK is absent.

    Args:
        iteration: Current iteration number (``agent.step.iteration`` attribute).
        task_id: Optional task identifier (``agent.step.task_id`` attribute).
    """
    try:
        from opentelemetry.trace import SpanKind

        tracer = get_tracer("autobot.agent_loop")
        attrs: dict = {"agent.step.iteration": iteration}
        if task_id is not None:
            attrs["agent.step.task_id"] = task_id
        return _RecordingSpan(tracer.start_as_current_span("agent.step", kind=SpanKind.INTERNAL, attributes=attrs))
    except ImportError:
        return _NoopSpan()


class _RecordingSpan:
    """Thin wrapper that records exceptions and sets ERROR status on the inner span.

    Used by tool_span and step_span so callers get automatic error recording without
    boilerplate.  Only wraps spans returned by real OTel tracers (not noop spans).
    """

    def __init__(self, ctx):
        self._ctx = ctx
        self._span = None

    def __enter__(self):
        self._span = self._ctx.__enter__()
        return self._span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val is not None and self._span is not None:
            try:
                from opentelemetry.trace import Status, StatusCode

                self._span.set_attribute("tool.error", True)
                self._span.record_exception(exc_val)
                self._span.set_status(Status(StatusCode.ERROR, str(exc_val)))
            except Exception:
                pass
        return self._ctx.__exit__(exc_type, exc_val, exc_tb)


async def shutdown_tracing() -> None:
    """
    Flush and shutdown the tracer provider.

    Call during application shutdown to ensure all pending spans are exported.
    """
    global _tracer_provider, _initialized

    if _tracer_provider is not None:
        try:
            _tracer_provider.force_flush()
            _tracer_provider.shutdown()
            logger.info("OpenTelemetry tracing shutdown complete")
        except Exception as e:
            logger.warning("Error during tracing shutdown: %s", e)

    _tracer_provider = None
    _initialized = False
