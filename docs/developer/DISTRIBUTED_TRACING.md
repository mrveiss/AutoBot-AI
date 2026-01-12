# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# Distributed Tracing with OpenTelemetry

**Issue:** #697 - Implement OpenTelemetry Distributed Tracing

This document describes the OpenTelemetry distributed tracing implementation across AutoBot's 6-VM infrastructure.

## Overview

OpenTelemetry provides end-to-end request tracing across all AutoBot services, enabling:
- **Cross-service debugging** - Track requests from frontend through backend to AI Stack
- **Performance analysis** - Identify bottlenecks in request processing
- **Error correlation** - Connect errors across distributed components
- **LLM monitoring** - Track inference latency and model usage

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Frontend      │────▶│   Backend       │────▶│   Redis         │
│  (VM1: .21)     │     │  (Main: .20)    │     │  (VM3: .23)     │
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ AI Stack │ │ NPU Wrkr │ │ Browser  │
              │(VM4:.24) │ │(VM2:.22) │ │(VM5:.25) │
              └──────────┘ └──────────┘ └──────────┘
                    │
                    ▼
              ┌──────────┐
              │  Jaeger  │  ◀── Trace Collection
              │ :4317    │
              └──────────┘
```

## Configuration

### Environment Variables

Add to `.env` or `.env.example`:

```bash
# Jaeger OTLP endpoint (default: Redis VM)
AUTOBOT_JAEGER_ENDPOINT=http://172.16.168.23:4317

# Trace sampling rate (0.0-1.0)
# 1.0 = trace everything (development)
# 0.1 = trace 10% of requests (production)
AUTOBOT_TRACE_SAMPLE_RATE=1.0

# Enable console span export for debugging
AUTOBOT_TRACE_CONSOLE=false
```

### Sampling Strategy

The sampling strategy uses `ParentBasedTraceIdRatio`:
- **Respects parent decisions** - If a parent span is sampled, all children are too
- **Probabilistic sampling** - Samples based on trace ID hash for consistent decisions
- **Configurable rate** - Set via `AUTOBOT_TRACE_SAMPLE_RATE`

| Environment | Recommended Rate |
|-------------|------------------|
| Development | 1.0 (100%) |
| Staging | 0.5 (50%) |
| Production | 0.1 (10%) |

## Instrumented Components

### Auto-Instrumented (via OpenTelemetry libraries)

| Component | Library | Span Names |
|-----------|---------|------------|
| FastAPI | `opentelemetry-instrumentation-fastapi` | `HTTP {method} {path}` |
| Redis | `opentelemetry-instrumentation-redis` | `redis.{command}` |
| aiohttp | `opentelemetry-instrumentation-aiohttp-client` | `HTTP {method}` |

### Custom Instrumented

| Component | Module | Span Names | Attributes |
|-----------|--------|------------|------------|
| Ollama LLM | `src/llm_interface_pkg/providers/ollama.py` | `llm.inference` | `llm.model`, `llm.provider`, `llm.duration_ms` |
| OpenAI LLM | `src/llm_interface_pkg/providers/openai_provider.py` | `llm.inference` | `llm.model`, `llm.prompt_tokens`, `llm.total_tokens` |
| SSH/PKI | `src/pki/distributor.py` | `ssh.distribute_certificates` | `ssh.target_vm`, `ssh.files_copied` |

## Span Conventions

### Naming Convention

```
{domain}.{operation}
```

Examples:
- `llm.inference` - LLM model inference
- `ssh.distribute_certificates` - PKI certificate distribution
- `http.request` - HTTP client request

### Standard Attributes

#### HTTP Spans
```python
"http.method": "POST",
"http.url": "http://host:port/path",
"http.status_code": 200,
"http.duration_ms": 150.5,
```

#### LLM Spans
```python
"llm.provider": "ollama",
"llm.model": "mistral:7b-instruct",
"llm.streaming": True,
"llm.temperature": 0.7,
"llm.prompt_messages": 3,
"llm.duration_ms": 2500.0,
"llm.response_length": 1024,
"llm.prompt_tokens": 150,      # OpenAI only
"llm.completion_tokens": 200,  # OpenAI only
```

#### SSH Spans
```python
"ssh.target_vm": "frontend",
"ssh.target_ip": "172.16.168.21",
"ssh.user": "autobot",
"ssh.files_copied": 3,
"pki.operation": "distribute",
```

### Error Recording

Always record errors on spans:

```python
try:
    result = await operation()
except Exception as e:
    if span.is_recording():
        span.set_status(Status(StatusCode.ERROR, str(e)))
        span.record_exception(e)
        span.set_attribute("error.type", type(e).__name__)
    raise
```

## Usage Examples

### Creating Custom Spans

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

# Get tracer for your module
_tracer = trace.get_tracer("autobot.mymodule", "2.0.0")

async def my_operation(data):
    with _tracer.start_as_current_span(
        "mymodule.operation",
        kind=SpanKind.INTERNAL,
        attributes={
            "operation.input_size": len(data),
        },
    ) as span:
        try:
            result = await process(data)

            if span.is_recording():
                span.set_attribute("operation.result_size", len(result))
                span.set_status(Status(StatusCode.OK))

            return result
        except Exception as e:
            if span.is_recording():
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
            raise
```

### Using TracingService

```python
from backend.services.tracing_service import get_tracing_service

tracing = get_tracing_service()

# Context manager for spans
with tracing.span("my_operation", attributes={"key": "value"}) as span:
    # Your code here
    tracing.add_event("checkpoint_reached")
    tracing.set_attribute("result_count", 42)

# Get trace context for propagation
headers = tracing.get_trace_context()
# headers contains: traceparent, tracestate, b3, etc.
```

### Using TracedHttpClient

```python
from src.utils.traced_http_client import TracedHttpClient
from src.constants.network_constants import ServiceURLs

async with TracedHttpClient() as client:
    # Trace context is automatically propagated
    response = await client.post(
        f"{ServiceURLs.AI_STACK}/api/process",
        json={"data": "payload"}
    )
```

## Viewing Traces

### Jaeger UI

1. Start Jaeger on the Redis VM (VM3):
   ```bash
   docker run -d --name jaeger \
     -e COLLECTOR_OTLP_ENABLED=true \
     -p 16686:16686 \
     -p 4317:4317 \
     -p 4318:4318 \
     jaegertracing/all-in-one:1.50
   ```

2. Access Jaeger UI: http://172.16.168.23:16686

### Example Trace Queries

- Find slow LLM inferences: `llm.duration_ms > 5000`
- Find failed SSH operations: `ssh.error_type = asyncssh_error`
- Find requests to specific VM: `ssh.target_vm = frontend`

## Initialization

Tracing is automatically initialized during backend startup in `backend/initialization/background_tasks.py`:

```python
async def _init_distributed_tracing(app: FastAPI, update_status_fn):
    tracing = get_tracing_service()
    success = tracing.initialize(
        service_name="autobot-backend",
        service_version="2.0.0",
    )
    if success:
        # Instruments FastAPI, Redis, and aiohttp
        results = tracing.instrument_all(app)
```

## Troubleshooting

### Traces Not Appearing

1. **Check Jaeger is running:**
   ```bash
   curl http://172.16.168.23:4317/health
   ```

2. **Enable console export for debugging:**
   ```bash
   AUTOBOT_TRACE_CONSOLE=true
   ```

3. **Check sampling rate:**
   ```bash
   AUTOBOT_TRACE_SAMPLE_RATE=1.0  # Trace everything
   ```

### Missing Spans

- Ensure `opentelemetry-instrumentation-redis` is installed for Redis spans
- Ensure `opentelemetry-instrumentation-aiohttp-client` is installed for HTTP client spans
- Check that `instrument_all()` is called during initialization

### Context Not Propagating

- Use `TracedHttpClient` for inter-service HTTP calls
- Ensure trace headers are not being stripped by proxies
- Verify W3C TraceContext headers: `traceparent`, `tracestate`

## Dependencies

```
opentelemetry-api>=1.34.0
opentelemetry-sdk>=1.34.0
opentelemetry-exporter-otlp>=1.34.0
opentelemetry-instrumentation-fastapi>=0.55b0
opentelemetry-instrumentation-redis>=0.55b0
opentelemetry-instrumentation-aiohttp-client>=0.55b0
opentelemetry-propagator-b3>=1.34.0
```

## Related Files

- `backend/services/tracing_service.py` - Core tracing service
- `backend/middleware/tracing_middleware.py` - Request tracing middleware
- `backend/initialization/background_tasks.py` - Tracing initialization
- `src/utils/traced_http_client.py` - HTTP client with trace propagation
- `src/llm_interface_pkg/providers/ollama.py` - LLM tracing spans
- `src/pki/distributor.py` - SSH/PKI tracing spans

## References

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/instrumentation/python/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)
