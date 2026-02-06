# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Distributed Tracing Service with OpenTelemetry (Issue #57, #697)

Provides centralized OpenTelemetry configuration for distributed tracing
across the 5-VM AutoBot infrastructure (see NetworkConstants for IPs):
- Main Machine - Backend API
- VM1 Frontend - Web interface
- VM2 NPU Worker - Hardware AI acceleration
- VM3 Redis - Data layer + Jaeger
- VM4 AI Stack - AI processing
- VM5 Browser - Web automation

Features:
- Trace context propagation across services
- Span creation and management
- Custom attributes for AutoBot-specific data
- OTLP export to Jaeger/Zipkin
- Graceful fallback when tracing is unavailable
- Redis auto-instrumentation (Issue #697)
- aiohttp client auto-instrumentation (Issue #697)
- Configurable sampling strategy (Issue #697)
"""

import logging
import os
import threading
from contextlib import contextmanager
from typing import Any, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.trace.sampling import (
    ParentBasedTraceIdRatio,
    ALWAYS_ON,
    ALWAYS_OFF,
)
from opentelemetry.trace import Status, StatusCode, SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

from constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)

# Service identification for distributed tracing
SERVICE_INSTANCES = {
    NetworkConstants.MAIN_MACHINE_IP: "autobot-backend",
    NetworkConstants.FRONTEND_VM_IP: "autobot-frontend",
    NetworkConstants.NPU_WORKER_VM_IP: "autobot-npu-worker",
    NetworkConstants.REDIS_VM_IP: "autobot-redis",
    NetworkConstants.AI_STACK_VM_IP: "autobot-ai-stack",
    NetworkConstants.BROWSER_VM_IP: "autobot-browser",
}


class TracingService:
    """
    Centralized OpenTelemetry tracing service for AutoBot.

    Manages trace provider initialization, span creation, and context propagation.
    Designed for multi-VM distributed tracing with Jaeger as the backend.
    """

    _instance: Optional["TracingService"] = None
    _initialized: bool = False
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "TracingService":
        """Singleton pattern - only one tracing service per process (thread-safe)."""
        if cls._instance is None:
            with cls._lock:
                # Double-check after acquiring lock (Issue #481 - race condition fix)
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize tracing service (only runs once due to singleton)."""
        if TracingService._initialized:
            return

        self._tracer: Optional[trace.Tracer] = None
        self._provider: Optional[TracerProvider] = None
        self._enabled: bool = False
        self._service_name: str = "autobot-backend"
        self._service_version: str = "1.0.0"

        # Configuration from environment
        self._jaeger_endpoint = os.getenv(
            "AUTOBOT_JAEGER_ENDPOINT",
            f"http://{NetworkConstants.REDIS_VM_IP}:4317"  # Default: Redis VM
        )
        self._console_export = os.getenv(
            "AUTOBOT_TRACE_CONSOLE",
            "false"
        ).lower() == "true"

        # Issue #697: Configurable sampling strategy
        # AUTOBOT_TRACE_SAMPLE_RATE: 0.0-1.0 (0.1 = 10% sampling in production)
        self._sample_rate = float(os.getenv("AUTOBOT_TRACE_SAMPLE_RATE", "1.0"))
        self._redis_instrumented = False
        self._aiohttp_instrumented = False

        TracingService._initialized = True

    def _resolve_service_name(self, service_name: Optional[str]) -> str:
        """
        Resolve service name from hostname if not provided (Issue #665: extracted helper).

        Args:
            service_name: Explicit service name or None for auto-detect

        Returns:
            Resolved service name string
        """
        if service_name is not None:
            return service_name

        import socket
        try:
            hostname = socket.gethostbyname(socket.gethostname())
            return SERVICE_INSTANCES.get(hostname, "autobot-unknown")
        except Exception:
            return "autobot-backend"

    def _create_resource(self) -> Resource:
        """
        Create OpenTelemetry resource with service information (Issue #665: extracted helper).

        Returns:
            Resource with service name, version, and namespace
        """
        return Resource.create({
            SERVICE_NAME: self._service_name,
            SERVICE_VERSION: self._service_version,
            "deployment.environment": os.getenv("AUTOBOT_ENV", "development"),
            "service.namespace": "autobot",
        })

    def _create_sampler(self):
        """
        Create trace sampler based on configuration (Issue #697).

        Uses ParentBasedTraceIdRatio for probabilistic sampling that respects
        parent span decisions (ensures complete traces).

        Returns:
            Configured sampler instance
        """
        if self._sample_rate <= 0.0:
            logger.info("Trace sampling disabled (rate=0.0)")
            return ALWAYS_OFF
        elif self._sample_rate >= 1.0:
            logger.info("Trace sampling: all traces (rate=1.0)")
            return ALWAYS_ON
        else:
            logger.info("Trace sampling: %.1f%% of traces", self._sample_rate * 100)
            return ParentBasedTraceIdRatio(self._sample_rate)

    def _setup_exporters(self, enable_console_export: bool) -> None:
        """
        Configure OTLP and console span exporters (Issue #665: extracted helper).

        Args:
            enable_console_export: Whether to add console exporter for debugging
        """
        # Add OTLP exporter for Jaeger
        try:
            otlp_exporter = OTLPSpanExporter(
                endpoint=self._jaeger_endpoint,
                insecure=True,  # Use insecure for internal network
            )
            self._provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter)
            )
            logger.info("OTLP exporter configured for %s", self._jaeger_endpoint)
        except Exception as e:
            logger.warning("Failed to configure OTLP exporter: %s", e)
            # Continue without OTLP - tracing still works locally

        # Optionally add console exporter for debugging
        if enable_console_export or self._console_export:
            self._provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter())
            )
            logger.info("Console span exporter enabled for debugging")

    def initialize(
        self,
        service_name: Optional[str] = None,
        service_version: str = "1.0.0",
        jaeger_endpoint: Optional[str] = None,
        enable_console_export: bool = False,
    ) -> bool:
        """
        Initialize the OpenTelemetry tracing provider.

        Issue #665: Refactored to use extracted helper methods for
        service name resolution, resource creation, and exporter setup.

        Args:
            service_name: Name of this service for trace attribution
            service_version: Version string for the service
            jaeger_endpoint: OTLP endpoint for Jaeger (e.g., http://host:4317)
            enable_console_export: Also export spans to console for debugging

        Returns:
            True if initialization succeeded, False otherwise
        """
        try:
            # Determine service name from IP if not provided (Issue #665: uses helper)
            self._service_name = self._resolve_service_name(service_name)
            self._service_version = service_version

            if jaeger_endpoint:
                self._jaeger_endpoint = jaeger_endpoint

            # Create resource with service information (Issue #665: uses helper)
            resource = self._create_resource()

            # Issue #697: Create sampler for trace sampling strategy
            sampler = self._create_sampler()

            # Create tracer provider with sampling
            self._provider = TracerProvider(resource=resource, sampler=sampler)

            # Configure exporters (Issue #665: uses helper)
            self._setup_exporters(enable_console_export)

            # Set as global tracer provider
            trace.set_tracer_provider(self._provider)

            # Set up context propagation (W3C TraceContext + B3 for compatibility)
            propagator = CompositePropagator([
                TraceContextTextMapPropagator(),
                B3MultiFormat(),
            ])
            set_global_textmap(propagator)

            # Get tracer instance
            self._tracer = trace.get_tracer(
                self._service_name,
                self._service_version,
            )

            self._enabled = True
            logger.info(
                f"OpenTelemetry tracing initialized for {self._service_name} "
                f"(version {self._service_version})"
            )
            return True

        except Exception as e:
            logger.error("Failed to initialize OpenTelemetry tracing: %s", e)
            self._enabled = False
            return False

    def instrument_fastapi(self, app) -> bool:
        """
        Instrument a FastAPI application for automatic tracing.

        Args:
            app: FastAPI application instance

        Returns:
            True if instrumentation succeeded
        """
        if not self._enabled:
            logger.warning("Tracing not enabled, skipping FastAPI instrumentation")
            return False

        try:
            FastAPIInstrumentor.instrument_app(
                app,
                tracer_provider=self._provider,
                excluded_urls="/health,/api/health,/metrics,/api/metrics",
            )
            logger.info("FastAPI instrumented for distributed tracing")
            return True
        except Exception as e:
            logger.error("Failed to instrument FastAPI: %s", e)
            return False

    def instrument_redis(self) -> bool:
        """
        Instrument Redis clients for automatic tracing (Issue #697).

        Auto-traces all Redis operations including GET, SET, HGET, LPUSH, etc.
        Works with both sync and async Redis clients.

        Returns:
            True if instrumentation succeeded
        """
        if not self._enabled:
            logger.warning("Tracing not enabled, skipping Redis instrumentation")
            return False

        if self._redis_instrumented:
            logger.debug("Redis already instrumented, skipping")
            return True

        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument(tracer_provider=self._provider)
            self._redis_instrumented = True
            logger.info("Redis instrumented for distributed tracing")
            return True
        except ImportError:
            logger.warning(
                "opentelemetry-instrumentation-redis not installed. "
                "Run: pip install opentelemetry-instrumentation-redis"
            )
            return False
        except Exception as e:
            logger.error("Failed to instrument Redis: %s", e)
            return False

    def instrument_aiohttp(self) -> bool:
        """
        Instrument aiohttp client for automatic tracing (Issue #697).

        Auto-traces all outgoing HTTP requests made with aiohttp.ClientSession,
        including trace context propagation to downstream services.

        Returns:
            True if instrumentation succeeded
        """
        if not self._enabled:
            logger.warning("Tracing not enabled, skipping aiohttp instrumentation")
            return False

        if self._aiohttp_instrumented:
            logger.debug("aiohttp already instrumented, skipping")
            return True

        try:
            from opentelemetry.instrumentation.aiohttp_client import (
                AioHttpClientInstrumentor,
            )

            AioHttpClientInstrumentor().instrument(tracer_provider=self._provider)
            self._aiohttp_instrumented = True
            logger.info("aiohttp client instrumented for distributed tracing")
            return True
        except ImportError:
            logger.warning(
                "opentelemetry-instrumentation-aiohttp-client not installed. "
                "Run: pip install opentelemetry-instrumentation-aiohttp-client"
            )
            return False
        except Exception as e:
            logger.error("Failed to instrument aiohttp: %s", e)
            return False

    def instrument_all(self, app=None) -> Dict[str, bool]:
        """
        Instrument all supported libraries (Issue #697).

        Convenience method to instrument FastAPI, Redis, and aiohttp in one call.

        Args:
            app: Optional FastAPI application instance

        Returns:
            Dictionary of instrumentation results
        """
        results = {
            "redis": self.instrument_redis(),
            "aiohttp": self.instrument_aiohttp(),
        }

        if app is not None:
            results["fastapi"] = self.instrument_fastapi(app)

        successful = sum(1 for v in results.values() if v)
        logger.info(
            "Instrumentation complete: %d/%d libraries instrumented",
            successful,
            len(results),
        )
        return results

    @property
    def tracer(self) -> Optional[trace.Tracer]:
        """Get the OpenTelemetry tracer instance."""
        return self._tracer

    @property
    def enabled(self) -> bool:
        """Check if tracing is enabled."""
        return self._enabled

    @contextmanager
    def span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Create a traced span context manager.

        Args:
            name: Name of the span
            kind: Type of span (INTERNAL, SERVER, CLIENT, PRODUCER, CONSUMER)
            attributes: Custom attributes to attach to the span

        Yields:
            The active span, or a no-op context if tracing is disabled

        Example:
            with tracing_service.span("process_request", attributes={"user_id": 123}):
                # Your code here
                pass
        """
        if not self._enabled or not self._tracer:
            # Return a no-op context when tracing is disabled
            yield None
            return

        with self._tracer.start_as_current_span(
            name,
            kind=kind,
            attributes=attributes or {},
        ) as span:
            try:
                yield span
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise

    def create_span(
        self,
        name: str,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """
        Create and start a new span (non-context manager version).

        Args:
            name: Name of the span
            kind: Type of span
            attributes: Custom attributes

        Returns:
            The span object, or None if tracing is disabled
        """
        if not self._enabled or not self._tracer:
            return None

        return self._tracer.start_span(
            name,
            kind=kind,
            attributes=attributes or {},
        )

    def add_event(
        self,
        name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Add an event to the current span.

        Args:
            name: Event name
            attributes: Event attributes
        """
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.add_event(name, attributes=attributes or {})

    def set_attribute(self, key: str, value: Any) -> None:
        """
        Set an attribute on the current span.

        Args:
            key: Attribute key
            value: Attribute value
        """
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.set_attribute(key, value)

    def set_error(self, exception: Exception) -> None:
        """
        Mark the current span as errored.

        Args:
            exception: The exception that occurred
        """
        current_span = trace.get_current_span()
        if current_span and current_span.is_recording():
            current_span.set_status(Status(StatusCode.ERROR, str(exception)))
            current_span.record_exception(exception)

    def get_trace_context(self) -> Dict[str, str]:
        """
        Get the current trace context for propagation to other services.

        Returns:
            Dictionary of trace context headers
        """
        from opentelemetry.propagate import inject

        headers: Dict[str, str] = {}
        inject(headers)
        return headers

    def shutdown(self) -> None:
        """Gracefully shutdown the tracing provider."""
        if self._provider:
            try:
                self._provider.shutdown()
                logger.info("OpenTelemetry tracing provider shutdown complete")
            except Exception as e:
                logger.error("Error shutting down tracing provider: %s", e)

        self._enabled = False


# Singleton instance
tracing_service = TracingService()


def get_tracing_service() -> TracingService:
    """Get the singleton tracing service instance."""
    return tracing_service
