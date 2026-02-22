# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# Distributed Tracing with OpenTelemetry

This document covers the distributed tracing implementation for the AutoBot platform using OpenTelemetry and Jaeger.

## Overview

AutoBot uses OpenTelemetry for distributed tracing across its 5-VM infrastructure:

| VM | IP Address | Service Name | Role |
|----|------------|--------------|------|
| Main Machine | 172.16.168.20 | autobot-backend | Backend API |
| VM1 Frontend | 172.16.168.21 | autobot-frontend | Web interface |
| VM2 NPU Worker | 172.16.168.22 | autobot-npu-worker | Hardware AI acceleration |
| VM3 Redis | 172.16.168.23 | autobot-redis | Data layer + Jaeger |
| VM4 AI Stack | 172.16.168.24 | autobot-ai-stack | AI processing |
| VM5 Browser | 172.16.168.25 | autobot-browser | Web automation |

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Distributed Tracing Flow                         │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │   Frontend   │ ──── │   Backend    │ ──── │   AI Stack   │
  │  (.21:5173)  │      │  (.20:8001)  │      │  (.24:8080)  │
  └──────────────┘      └──────────────┘      └──────────────┘
         │                     │                     │
         │                     ▼                     │
         │              ┌──────────────┐             │
         │              │    Redis     │             │
         └─────────────▶│  (.23:6379)  │◀────────────┘
                        │   + Jaeger   │
                        │  (.23:16686) │
                        └──────────────┘
                               ▲
                               │
                        ┌──────────────┐
                        │  NPU Worker  │
                        │  (.22:8081)  │
                        └──────────────┘
```

## Components

### 1. Tracing Service (`backend/services/tracing_service.py`)

Central OpenTelemetry configuration (365 lines) providing:
- Singleton pattern for single tracer per process
- OpenTelemetry TracerProvider initialization
- OTLP exporter configuration for Jaeger
- FastAPI auto-instrumentation
- Span creation and management
- W3C TraceContext + B3 propagation

Key methods:
- `initialize()` - Configure OpenTelemetry with Jaeger exporter
- `instrument_fastapi(app)` - Auto-instrument FastAPI application
- `span(name, attributes)` - Context manager for creating spans
- `get_trace_context()` - Get headers for cross-service propagation
- `set_error(exception)` - Record exception in current span

### 2. Tracing Middleware (`backend/middleware/tracing_middleware.py`)

ASGI middleware (267 lines) adding AutoBot-specific tracing:
- Automatic span creation per request
- Request/response attribute capture
- Error tracking and exception recording
- Performance timing metrics
- Path exclusions for health/metrics endpoints

### 3. Traced HTTP Client (`src/utils/traced_http_client.py`)

HTTP client wrapper (245 lines) for cross-VM communication:
- Automatic trace context propagation via headers
- Span creation for each HTTP request
- Error recording with exception details
- Request/response attribute capture
- Retry logic with exponential backoff
- Connection pooling for performance

## Installation

### Prerequisites

OpenTelemetry packages are already installed in AutoBot:

```bash
# Already in requirements.txt
opentelemetry-api
opentelemetry-sdk
opentelemetry-instrumentation-fastapi
opentelemetry-exporter-otlp
opentelemetry-propagator-b3
```

### Jaeger Setup (VM3 Redis - 172.16.168.23)

Since AutoBot doesn't use Docker, Jaeger runs as a native binary on the Redis VM.

#### Download and Install Jaeger

```bash
# SSH to Redis VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23

# Download Jaeger (latest version)
JAEGER_VERSION="1.53.0"
wget https://github.com/jaegertracing/jaeger/releases/download/v${JAEGER_VERSION}/jaeger-${JAEGER_VERSION}-linux-amd64.tar.gz

# Extract
tar -xzf jaeger-${JAEGER_VERSION}-linux-amd64.tar.gz
sudo mv jaeger-${JAEGER_VERSION}-linux-amd64 /opt/jaeger

# Create systemd service
sudo tee /etc/systemd/system/jaeger.service << 'EOF'
[Unit]
Description=Jaeger All-in-One
After=network.target

[Service]
Type=simple
User=autobot
ExecStart=/opt/jaeger/jaeger-all-in-one \
    --collector.otlp.enabled=true \
    --collector.otlp.grpc.host-port=0.0.0.0:4317 \
    --collector.otlp.http.host-port=0.0.0.0:4318 \
    --query.http-server.host-port=0.0.0.0:16686 \
    --memory.max-traces=100000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable jaeger
sudo systemctl start jaeger
```

#### Verify Installation

```bash
# Check status
sudo systemctl status jaeger

# Test OTLP endpoint
curl http://172.16.168.23:4317  # gRPC (connection refused is OK)
curl http://172.16.168.23:4318  # HTTP

# Access Jaeger UI
# Open in browser: http://172.16.168.23:16686
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_JAEGER_ENDPOINT` | `http://172.16.168.23:4317` | OTLP gRPC endpoint |
| `AUTOBOT_TRACE_CONSOLE` | `false` | Enable console span export |
| `AUTOBOT_ENV` | `development` | Deployment environment tag |

### Backend Configuration

Tracing is automatically initialized during backend startup via `app_factory_enhanced.py`:

```python
# Tracing initialization (automatic)
tracing = get_tracing_service()
tracing.initialize(
    service_name="autobot-backend",
    service_version="2.0.0",
    jaeger_endpoint="http://172.16.168.23:4317",
)
tracing.instrument_fastapi(app)
```

## Usage

### Automatic Tracing

All HTTP requests to the backend are automatically traced via:
1. FastAPI instrumentation (request/response spans)
2. TracingMiddleware (AutoBot-specific attributes)

### Custom Spans

Add custom spans for specific operations:

```python
from backend.services.tracing_service import get_tracing_service

tracing = get_tracing_service()

# Context manager style (recommended)
with tracing.span("process_ai_request", attributes={"model": "gpt-4"}):
    result = await process_request()
    tracing.set_attribute("tokens_used", result.tokens)
    tracing.add_event("model_response_received")

# Manual span management
span = tracing.create_span("long_operation")
try:
    # ... operation ...
    span.set_attribute("result_size", len(result))
finally:
    span.end()
```

### Error Recording

Errors are automatically recorded in spans:

```python
with tracing.span("risky_operation"):
    try:
        risky_function()
    except Exception as e:
        tracing.set_error(e)  # Records exception in span
        raise
```

### Cross-Service Propagation

For HTTP calls between VMs, use the `TracedHttpClient` for automatic trace propagation:

```python
from src.utils.traced_http_client import get_traced_http_client

# Get the traced HTTP client singleton
http_client = get_traced_http_client()

async def call_ai_stack(payload: dict):
    # Trace context is automatically propagated via headers
    response = await http_client.post(
        "http://172.16.168.24:8080/api/process",
        payload=payload,
    )
    return response

# Other HTTP methods available:
result = await http_client.get("http://...")
result = await http_client.put("http://...", payload=data)
result = await http_client.patch("http://...", payload=data)
result = await http_client.delete("http://...")
```

#### TracedHttpClient Features

The `TracedHttpClient` (`src/utils/traced_http_client.py`) provides:
- **Automatic trace context injection** via W3C TraceContext headers
- **Span creation** for each HTTP request
- **Error recording** when requests fail
- **Request/response attribute capture** (method, URL, status code, duration)
- **Retry logic** with exponential backoff
- **Connection pooling** for performance

#### Manual Propagation (Alternative)

For cases where you can't use `TracedHttpClient`:

```python
import httpx
from backend.services.tracing_service import get_tracing_service

tracing = get_tracing_service()

async def call_ai_stack(payload: dict):
    # Get trace context headers manually
    headers = tracing.get_trace_context()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://172.16.168.24:8080/api/process",
            json=payload,
            headers=headers,  # Propagate trace context
        )
    return response.json()
```

## Span Attributes

### Standard HTTP Attributes

| Attribute | Example | Description |
|-----------|---------|-------------|
| `http.method` | `POST` | HTTP method |
| `http.url` | `http://...` | Full request URL |
| `http.status_code` | `200` | Response status |
| `http.duration_ms` | `45.2` | Request duration |

### AutoBot Custom Attributes

| Attribute | Example | Description |
|-----------|---------|-------------|
| `autobot.service` | `autobot-backend` | Service name |
| `autobot.request_id` | `uuid-...` | Request correlation ID |
| `error.type` | `ValueError` | Exception type name |
| `error.message` | `Invalid input` | Exception message |

## Excluded Paths

The following paths are excluded from detailed tracing to reduce noise:

- `/health`, `/api/health`
- `/metrics`, `/api/metrics`
- `/favicon.ico`
- `/static/*`

## Monitoring

### Jaeger UI

Access the Jaeger UI at: `http://172.16.168.23:16686`

Features:
- Search traces by service, operation, tags
- View trace timeline and span details
- Analyze latency distributions
- Compare traces

### Health Check

Tracing status is included in the backend health check:

```bash
curl https://172.16.168.20:8443/api/health | jq '.services.distributed_tracing'
# Returns: "ready" or "pending" or "failed"
```

## Troubleshooting

### Traces Not Appearing in Jaeger

1. **Check Jaeger is running:**
   ```bash
   ssh autobot@172.16.168.23 "sudo systemctl status jaeger"
   ```

2. **Verify OTLP endpoint:**
   ```bash
   curl -v http://172.16.168.23:4318/v1/traces
   ```

3. **Enable console export for debugging:**
   ```bash
   export AUTOBOT_TRACE_CONSOLE=true
   # Restart backend - spans will print to console
   ```

4. **Check backend logs:**
   ```bash
   grep -i "tracing\|opentelemetry" logs/backend.log
   ```

### High Latency Warnings

If you see "Slow request traced" warnings:
- Check the Jaeger UI for the specific trace
- Analyze span breakdown to identify bottleneck
- Consider adding custom spans around suspected slow operations

### Memory Issues

If Jaeger uses too much memory:
```bash
# Reduce max traces in memory
sudo systemctl edit jaeger
# Add: --memory.max-traces=50000
sudo systemctl restart jaeger
```

## VM-Specific Setup

### NPU Worker (VM2 - 172.16.168.22)

```python
# In NPU worker initialization
from backend.services.tracing_service import get_tracing_service

tracing = get_tracing_service()
tracing.initialize(
    service_name="autobot-npu-worker",
    jaeger_endpoint="http://172.16.168.23:4317",
)
```

### AI Stack (VM4 - 172.16.168.24)

```python
# In AI stack initialization
tracing.initialize(
    service_name="autobot-ai-stack",
    jaeger_endpoint="http://172.16.168.23:4317",
)
```

### Browser Automation (VM5 - 172.16.168.25)

```python
# In browser automation service
tracing.initialize(
    service_name="autobot-browser",
    jaeger_endpoint="http://172.16.168.23:4317",
)
```

## Best Practices

1. **Name spans descriptively**: Use format `<verb>_<noun>` (e.g., `process_message`, `fetch_user`)

2. **Add meaningful attributes**: Include IDs, counts, and relevant context

3. **Record events for checkpoints**: Use `add_event()` for important milestones

4. **Don't over-trace**: Avoid creating spans for trivial operations

5. **Propagate context**: Always pass trace headers in cross-service calls

6. **Handle errors properly**: Let automatic error recording capture exceptions

## Related Documentation

- [OpenTelemetry Python Docs](https://opentelemetry.io/docs/languages/python/)
- [Jaeger Documentation](https://www.jaegertracing.io/docs/)
- [W3C Trace Context](https://www.w3.org/TR/trace-context/)

## Issue Reference

This implementation addresses GitHub Issue #57: Distributed Tracing with OpenTelemetry.
