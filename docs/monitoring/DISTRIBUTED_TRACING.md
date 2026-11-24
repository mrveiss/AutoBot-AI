> **IP addresses** in this document use role placeholders (e.g. `<backend-ip>`). Replace with your actual VM IPs. See [VM_ROLES.md](../architecture/VM_ROLES.md) for role definitions.

# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# Distributed Tracing with OpenTelemetry

This document covers the distributed tracing implementation for the AutoBot platform using OpenTelemetry and Jaeger.

## Overview

AutoBot uses OpenTelemetry for distributed tracing across its role-based infrastructure — Docker, a single VM, or however many machines a deployment scales to:

| Role | IP Address | Service Name |
|----|------------|--------------|
| Main / Control | <backend-ip> | autobot-backend |
| Frontend | <frontend-ip> | autobot-frontend |
| NPU Worker | <npu-ip> | autobot-npu-worker |
| Database (Redis) | <database-ip> | autobot-redis + Jaeger |
| AI/ML | <aiml-ip> | autobot-ai-stack |
| Browser | <browser-ip> | autobot-browser |

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

### 1. Tracing module (`autobot_shared/tracing.py`)

The one OpenTelemetry setup for every AutoBot service (one tracer provider per process):
- `init_tracing(service_name)` - TracerProvider, sampler, OTLP exporter, optional console exporter,
  W3C TraceContext + B3 propagation
- `instrument_fastapi(app)`, `instrument_redis()`, `instrument_aiohttp()` - auto-instrumentation
- `get_tracer(name)` - tracer for custom spans (a no-op tracer when tracing is off)
- `get_trace_context()` - headers for cross-service propagation

### 2. FastAPI instrumentation options (`autobot_shared/tracing.py`)

`instrument_fastapi()` applies `FastAPIInstrumentor` with AutoBot's shared options
(`fastapi_instrumentation_kwargs()`), so there is one span per request and no second tracing middleware:
- Request/response attributes, exception recording and timing come from the instrumentation
- `autobot.request_id` and the trusted-proxy-aware `http.client_ip` are added by a `server_request_hook`
- Health, metrics and static paths are excluded from tracing

### 3. Traced HTTP Client (`src/utils/traced_http_client.py`)

HTTP client wrapper (245 lines) for cross-role communication:
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

### Jaeger Setup (Database Role - Redis - <database-ip>)

Since AutoBot doesn't use Docker, Jaeger runs as a native binary on the database role's host in this example.

#### Download and Install Jaeger

```bash
# SSH to the database role's host
ssh -i ~/.ssh/autobot_key autobot@<database-ip>

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
curl http://<database-ip>:4317  # gRPC (connection refused is OK)
curl http://<database-ip>:4318  # HTTP

# Access Jaeger UI
# Open in browser: http://<database-ip>:16686
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AUTOBOT_OTEL_ENDPOINT` | unset | OTLP collector endpoint (falls back to `AUTOBOT_JAEGER_ENDPOINT`) |
| `AUTOBOT_TRACE_CONSOLE` | `false` | Enable console span export |
| `AUTOBOT_ENV` | `development` | Deployment environment tag |

### Backend Configuration

Tracing is initialized during backend startup in `app_factory.py`:

```python
init_tracing(service_name="autobot-backend")
instrument_fastapi(app)
```

## Usage

### Automatic Tracing

All HTTP requests to the backend are automatically traced via FastAPI instrumentation
(request/response spans), with AutoBot-specific attributes added by its `server_request_hook`.

### Custom Spans

Add custom spans for specific operations. Exceptions raised inside the span are recorded on it automatically:

```python
from autobot_shared.tracing import get_tracer

tracer = get_tracer(__name__)

with tracer.start_as_current_span("process_ai_request") as span:
    span.set_attribute("model", "gpt-4")
    result = await process_request()
    span.set_attribute("tokens_used", result.tokens)
    span.add_event("model_response_received")
```

### Cross-Service Propagation

For HTTP calls between roles, use the `TracedHttpClient` for automatic trace propagation:

```python
from src.utils.traced_http_client import get_traced_http_client

# Get the traced HTTP client singleton
http_client = get_traced_http_client()

async def call_ai_stack(payload: dict):
    # Trace context is automatically propagated via headers
    response = await http_client.post(
        "http://<aiml-ip>:8080/api/process",
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
from autobot_shared.tracing import get_trace_context

async def call_ai_stack(payload: dict):
    # Get trace context headers manually
    headers = get_trace_context()

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://<aiml-ip>:8080/api/process",
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

Access the Jaeger UI at: `http://<database-ip>:16686`

Features:
- Search traces by service, operation, tags
- View trace timeline and span details
- Analyze latency distributions
- Compare traces

### Health Check

Tracing status is included in the backend health check:

```bash
curl https://<backend-ip>:8443/api/health | jq '.services.distributed_tracing'
# Returns: "ready" or "pending" or "failed"
```

## Troubleshooting

### Traces Not Appearing in Jaeger

1. **Check Jaeger is running:**
   ```bash
   ssh autobot@<database-ip> "sudo systemctl status jaeger"
   ```

2. **Verify OTLP endpoint:**
   ```bash
   curl -v http://<database-ip>:4318/v1/traces
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

## Per-Role Setup

### NPU Worker (<npu-ip>)

```python
# In NPU worker initialization
from autobot_shared.tracing import init_tracing

init_tracing(service_name="autobot-npu-worker")
```

### AI Stack (<aiml-ip>)

```python
# In AI stack initialization
init_tracing(service_name="autobot-ai-stack")
```

### Browser Automation (<browser-ip>)

```python
# In browser automation service
init_tracing(service_name="autobot-browser")
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
