# AutoBot Monitoring Architecture

**Author**: mrveiss
**Copyright**: (c) 2025 mrveiss
**Last Updated**: 2025-12-20
**Issue**: #469 - Prometheus/Grafana Monitoring Migration

---

## Overview

AutoBot uses a unified Prometheus/Grafana monitoring stack for comprehensive observability across all services. This document describes the architecture, components, data flow, and best practices.

## Architecture Diagram

```
+------------------+     +------------------+     +------------------+
|   AutoBot        |     |   NPU Worker     |     |   Browser        |
|   Backend        |     |   (VM2)          |     |   VM (VM5)       |
|   (Main/VM1)     |     |   :8081          |     |   :3000          |
+--------+---------+     +--------+---------+     +--------+---------+
         |                        |                        |
         | /metrics               | /metrics               | /metrics
         v                        v                        v
+--------+-----------------------+-----------------------+---------+
|                                                                   |
|                         Prometheus                                |
|                         (VM3: 172.16.168.23:9090)                |
|                                                                   |
|   - Scrapes all /metrics endpoints every 15s                    |
|   - Stores time-series data (30 day retention)                  |
|   - Evaluates alert rules                                        |
|                                                                   |
+----------------------------+--------------------------------------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
+-------------+-------------+  +------------+------------+
|                           |  |                         |
|      Grafana              |  |     AlertManager        |
|   (VM3: :3000)            |  |     (VM3: :9093)        |
|                           |  |                         |
|   - Dashboard viz         |  |   - Alert routing       |
|   - Embedded in Vue UI    |  |   - Notifications       |
|   - 13 pre-built dashboards|  |   - Silencing           |
|                           |  |                         |
+---------------------------+  +-------------------------+
              |
              v
+---------------------------+
|   AutoBot Frontend        |
|   (VM1: :5173)            |
|                           |
|   - GrafanaDashboard.vue  |
|   - Embedded iframes      |
|   - View mode toggles     |
+---------------------------+
```

## Components

### 1. Backend Metrics Exporters

Location: `src/monitoring/`

| Component | Purpose |
|-----------|---------|
| `prometheus_metrics.py` | Central PrometheusMetricsManager - facade for all recorders |
| `metrics/base.py` | BaseMetricsRecorder - common initialization pattern |
| `metrics/performance.py` | PerformanceMetricsRecorder - GPU/NPU/system metrics |
| `metrics/knowledge_base.py` | KnowledgeBaseMetricsRecorder - vector store metrics |
| `metrics/llm_provider.py` | LLMProviderMetricsRecorder - LLM API metrics |
| `metrics/websocket.py` | WebSocketMetricsRecorder - real-time connection metrics |
| `metrics/redis.py` | RedisMetricsRecorder - Redis operations/pool metrics |

### 2. Prometheus Server

**Location**: VM3 (172.16.168.23:9090)

**Configuration**: `config/prometheus/prometheus.yml`

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'autobot-backend'
    static_configs:
      - targets: ['172.16.168.20:8001']
    metrics_path: '/api/monitoring/metrics'

  - job_name: 'npu-worker'
    static_configs:
      - targets: ['172.16.168.22:8081']
    metrics_path: '/metrics'
```

**Data Retention**: 30 days (configurable via `--storage.tsdb.retention.time`)

### 3. Grafana Dashboards

**Location**: VM3 (172.16.168.23:3000)

**Datasource UID**: `PBFA97CFB590B2093`

**Dashboard Directory**: `config/grafana/dashboards/`

| Dashboard | UID | Purpose |
|-----------|-----|---------|
| autobot-overview.json | autobot-overview | System-wide health overview |
| autobot-system.json | autobot-system | CPU, memory, disk metrics |
| autobot-workflow.json | autobot-workflow | Workflow execution metrics |
| autobot-api-health.json | autobot-api-health | API endpoint health |
| autobot-errors.json | autobot-errors | Error tracking and rates |
| autobot-claude-api.json | autobot-claude-api | Claude API usage |
| autobot-github.json | autobot-github | GitHub integration metrics |
| autobot-multi-machine.json | autobot-multi-machine | Multi-VM infrastructure health |
| autobot-performance.json | autobot-performance | GPU/NPU performance |
| autobot-knowledge-base.json | autobot-knowledge-base | Vector store metrics |
| autobot-llm-providers.json | autobot-llm-providers | LLM provider metrics |
| autobot-redis.json | autobot-redis | Redis performance |
| autobot-websocket.json | autobot-websocket | WebSocket connection metrics |

### 4. Frontend Integration

**Component**: `autobot-user-frontend/src/components/monitoring/GrafanaDashboard.vue`

**Features**:
- Embeds Grafana dashboards in iframes
- Time range and refresh controls
- Fullscreen mode
- Dashboard type selection (13 types)

**View Mode Toggle**: Components like `MultiMachineHealth.vue` support switching between custom Vue views and embedded Grafana dashboards.

## Metric Naming Conventions

All metrics follow Prometheus naming best practices:

```
autobot_<domain>_<metric>_<unit>
```

### Examples

| Pattern | Example | Description |
|---------|---------|-------------|
| Counter | `autobot_llm_requests_total` | Cumulative count |
| Gauge | `autobot_websocket_connections_active` | Current value |
| Histogram | `autobot_redis_operation_latency_seconds` | Distribution |
| Summary | (not used) | - |

### Label Guidelines

- **Use lowercase**: `provider`, `status`, `model`
- **Fixed cardinality**: Avoid dynamic IDs as labels
- **Meaningful values**: `status: success/failed` not error messages
- **Consistent across domains**: Same label names for same concepts

## Metric Domains

### 1. Knowledge Base Metrics

Prefix: `autobot_knowledge_`

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `documents_total` | Gauge | collection, document_type | Total documents |
| `vectors_total` | Gauge | collection | Total vector embeddings |
| `search_latency_seconds` | Histogram | search_type, collection | Search response time |
| `cache_hits_total` | Counter | cache_type | Cache hit count |
| `cache_misses_total` | Counter | cache_type | Cache miss count |

### 2. LLM Provider Metrics

Prefix: `autobot_llm_`

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `requests_total` | Counter | provider, model, request_type | Total LLM requests |
| `tokens_total` | Counter | provider, model, token_type | Token usage |
| `cost_dollars_total` | Counter | provider, model, cost_type | Estimated cost |
| `request_latency_seconds` | Histogram | provider, model | Response latency |
| `errors_total` | Counter | provider, error_type | Error count |
| `rate_limit_remaining` | Gauge | provider | Remaining rate limit |
| `provider_availability` | Gauge | provider | Provider status (0/1) |

### 3. WebSocket Metrics

Prefix: `autobot_websocket_`

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `connections_active` | Gauge | namespace | Active connections |
| `connections_total` | Counter | namespace, status | Total connections |
| `messages_sent_total` | Counter | namespace, event_type | Messages sent |
| `messages_received_total` | Counter | namespace, event_type | Messages received |
| `message_latency_seconds` | Histogram | namespace | Message latency |
| `errors_total` | Counter | namespace, error_type | Connection errors |

### 4. Redis Metrics

Prefix: `autobot_redis_`

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `operations_total` | Counter | database, operation, status | Redis operations |
| `operation_latency_seconds` | Histogram | database, operation | Operation latency |
| `connections_active` | Gauge | database | Active connections |
| `pool_size` | Gauge | database | Connection pool size |
| `memory_used_bytes` | Gauge | database | Memory usage |
| `pubsub_messages_total` | Counter | database, direction | Pub/sub messages |

### 5. Performance Metrics

Prefix: `autobot_performance_`

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `cpu_usage_percent` | Gauge | machine | CPU utilization |
| `memory_usage_percent` | Gauge | machine | Memory usage |
| `gpu_utilization_percent` | Gauge | device | GPU usage |
| `npu_utilization_percent` | Gauge | device | NPU usage |
| `inference_latency_seconds` | Histogram | model, device | Model inference time |

## Data Flow

### Metric Collection Flow

```
1. Application Code
   │
   │  metrics.record_llm_request(...)
   │
   ▼
2. Domain Metrics Recorder (e.g., LLMProviderMetricsRecorder)
   │
   │  self.requests_total.labels(...).inc()
   │
   ▼
3. PrometheusMetricsManager (facade)
   │
   │  Exposes /api/monitoring/metrics endpoint
   │
   ▼
4. Prometheus Server
   │
   │  Scrapes every 15 seconds
   │  Stores in TSDB
   │
   ▼
5. Grafana
   │
   │  Queries via PromQL
   │  Renders dashboards
   │
   ▼
6. Frontend (GrafanaDashboard.vue)
      │
      │  Embeds in iframe
      │
      ▼
      User
```

### Alert Flow

```
Prometheus → AlertManager → Notifications
    │             │
    │ Rules       │ Routes
    │ evaluate    │
    │ every 15s   │
    ▼             ▼
Alert fires → Routing rules → Notification channels
              (severity,      (Slack, email,
               team)          PagerDuty, etc.)
```

## Usage Examples

### Recording Metrics in Backend Code

```python
from src.monitoring.prometheus_metrics import get_metrics_manager
import time

metrics = get_metrics_manager()

# Record LLM request
start = time.time()
response = await llm_client.complete(prompt)
duration = time.time() - start

metrics.record_llm_request(
    provider="openai",
    model="gpt-4",
    request_type="completion",
    status="success",
    latency=duration
)

metrics.record_llm_tokens(
    provider="openai",
    model="gpt-4",
    input_tokens=response.usage.prompt_tokens,
    output_tokens=response.usage.completion_tokens
)
```

### Creating Custom Grafana Queries

```promql
# LLM request rate by provider
sum(rate(autobot_llm_requests_total[5m])) by (provider)

# Average search latency
histogram_quantile(0.95,
  rate(autobot_knowledge_search_latency_seconds_bucket[5m])
)

# WebSocket connection count
sum(autobot_websocket_connections_active) by (namespace)

# Redis cache hit ratio
sum(rate(autobot_redis_operations_total{status="hit"}[5m]))
/
sum(rate(autobot_redis_operations_total[5m]))
```

## Frontend Dashboard Integration

### Using GrafanaDashboard Component

```vue
<template>
  <GrafanaDashboard
    dashboard="llm-providers"
    :height="600"
    :show-controls="true"
    theme="dark"
    time-range="now-1h"
    refresh="15s"
  />
</template>

<script setup>
import GrafanaDashboard from '@/components/monitoring/GrafanaDashboard.vue'
</script>
```

### Available Dashboard Types

```typescript
type DashboardType =
  | 'overview'
  | 'system'
  | 'workflow'
  | 'errors'
  | 'claude'
  | 'github'
  | 'performance'
  | 'api-health'
  | 'multi-machine'
  | 'knowledge-base'
  | 'llm-providers'
  | 'redis'
  | 'websocket'
```

## Configuration Files

| File | Purpose |
|------|---------|
| `config/prometheus/prometheus.yml` | Prometheus scrape configuration |
| `config/prometheus/alerts/` | Alert rule files |
| `config/grafana/provisioning/` | Grafana auto-provisioning |
| `config/grafana/dashboards/` | Dashboard JSON definitions |
| `config/alertmanager/alertmanager.yml` | AlertManager routing |

## Troubleshooting

### No Metrics in Grafana

1. Check backend metrics endpoint:
   ```bash
   curl http://172.16.168.20:8001/api/monitoring/metrics | head
   ```

2. Check Prometheus targets:
   ```bash
   curl http://172.16.168.23:9090/api/v1/targets | jq '.data.activeTargets'
   ```

3. Verify Grafana datasource:
   ```bash
   curl http://172.16.168.23:3000/api/datasources
   ```

### Missing New Metrics

After adding new metrics recorders:

1. Restart backend to register new metrics
2. Wait 15 seconds for Prometheus scrape
3. Verify in Prometheus: `http://172.16.168.23:9090/graph`
4. Refresh Grafana dashboard

### High Cardinality Warnings

Symptoms: Slow Prometheus queries, high memory usage

Fix:
- Avoid using dynamic values (UUIDs, timestamps) as labels
- Use fixed label sets
- Consider pre-aggregation with recording rules

## See Also

- [PROMETHEUS_METRICS_USAGE.md](../developer/PROMETHEUS_METRICS_USAGE.md) - Developer usage guide
- [QUICK_REFERENCE.md](../monitoring/QUICK_REFERENCE.md) - Operations quick reference
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)

---

**Author**: mrveiss
**Copyright**: (c) 2025 mrveiss
