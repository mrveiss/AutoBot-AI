# Error Monitoring and Observability

**Version:** 1.0.0
**Last Updated:** 2025-11-09
**Phase:** 5 - Monitoring & Observability

---

## Overview

The Error Monitoring system provides real-time error tracking, metrics collection, and observability for the AutoBot platform. It automatically collects error metrics from the error boundary system and provides comprehensive analytics and reporting capabilities.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Application Code                            │
│                                                                │
│  @error_boundary or @with_error_handling decorated            │
└───────────────────────────┬──────────────────────────────────┘
                            │
                            │ Error occurs
                            ▼
┌──────────────────────────────────────────────────────────────┐
│              Error Boundary Manager                           │
│  - Creates error report                                       │
│  - Records error metric ◄────────────────┐                    │
│  - Attempts recovery                      │                   │
└───────────────────────────┬───────────────┼───────────────────┘
                            │               │
                            │               │
                            ▼               │
┌──────────────────────────────────────────┼───────────────────┐
│            Error Metrics Collector        │                   │
│  - Tracks error occurrences               │                   │
│  - Aggregates statistics                  │                   │
│  - Calculates error rates                 │                   │
│  - Manages alert thresholds ──────────────┘                   │
└───────────────────────────┬──────────────────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
        ┌─────────┐   ┌─────────┐   ┌─────────┐
        │  Memory │   │  Redis  │   │  API    │
        │ Storage │   │ Persist │   │Endpoints│
        └─────────┘   └─────────┘   └─────────┘
```

---

## Key Features

### 1. Automatic Error Collection

Errors are automatically collected when they occur in code protected by error boundaries:

```python
from src.utils.error_boundaries import error_boundary, ErrorCategory

@error_boundary(component="knowledge_base", function="search")
async def search_knowledge_base(query: str):
    # Error automatically tracked if exception occurs
    result = await perform_search(query)
    return result
```

### 2. Real-Time Metrics

- **Error counts** by component, category, and error code
- **Error rates** (errors per minute)
- **Retry tracking** - how many errors triggered retries
- **Resolution tracking** - mark errors as resolved
- **Time-series data** - hourly error trends

### 3. Aggregation & Analytics

- **Category breakdown** - errors grouped by type (validation, auth, server, etc.)
- **Component breakdown** - which components have most errors
- **Top errors** - most frequently occurring errors
- **Error timeline** - hourly error counts for visualization
- **Resolution rates** - percentage of errors marked resolved

### 4. Alert Thresholds

Set custom alert thresholds for components or specific errors:

```python
from src.utils.error_metrics import get_metrics_collector

collector = get_metrics_collector()

# Alert when knowledge_base has 10+ errors
collector.set_alert_threshold("knowledge_base", error_code=None, threshold=10)

# Alert when specific error occurs 5+ times
collector.set_alert_threshold("llm_service", error_code="LLM_0001", threshold=5)
```

### 5. Data Persistence

- **In-memory** - Last 10,000 metrics for fast access
- **Redis** (optional) - Persistent storage with 24-hour retention
- **Automatic cleanup** - Old metrics removed automatically

---

## API Endpoints

### Metrics Summary

**GET** `/api/monitoring/errors/metrics/summary`

Returns comprehensive metrics summary:

```json
{
  "status": "success",
  "data": {
    "total_errors": 1234,
    "unique_error_types": 45,
    "total_retries": 234,
    "total_resolved": 567,
    "avg_error_rate": 2.5,
    "category_breakdown": {
      "server_error": 500,
      "validation": 300,
      "authentication": 150
    },
    "component_breakdown": {
      "knowledge_base": 400,
      "llm_service": 350,
      "chat_workflow": 200
    },
    "top_errors": [...]
  }
}
```

### Error Timeline

**GET** `/api/monitoring/errors/metrics/timeline?hours=24&component=llm_service`

Returns hourly error counts for visualization:

```json
{
  "status": "success",
  "data": {
    "timeline": [
      {
        "hour": "2025-11-09 14:00",
        "error_count": 15,
        "errors": [...]
      }
    ],
    "hours": 24,
    "component": "llm_service"
  }
}
```

### Top Errors

**GET** `/api/monitoring/errors/metrics/top-errors?limit=10`

Returns most frequent errors:

```json
{
  "status": "success",
  "data": {
    "top_errors": [
      {
        "error_code": "LLM_0001",
        "category": "service_unavailable",
        "component": "llm_service",
        "total_count": 150,
        "error_rate": 2.5,
        "retry_count": 45,
        "resolved_count": 30
      }
    ]
  }
}
```

### Mark Error Resolved

**POST** `/api/monitoring/errors/metrics/resolve/{trace_id}`

Mark an error as resolved:

```json
{
  "status": "success",
  "message": "Error abc123 marked as resolved"
}
```

### Set Alert Threshold

**POST** `/api/monitoring/errors/metrics/alert-threshold`

```json
{
  "component": "knowledge_base",
  "error_code": "KB_0001",
  "threshold": 10
}
```

### Cleanup Old Metrics

**POST** `/api/monitoring/errors/metrics/cleanup`

Removes metrics older than retention period:

```json
{
  "status": "success",
  "message": "Cleaned up 500 old metrics",
  "removed_count": 500
}
```

### Legacy Endpoints (Backward Compatible)

- `GET /statistics` - Error statistics from error_boundaries
- `GET /recent?limit=20` - Recent error reports
- `GET /categories` - Category breakdown with percentages
- `GET /components` - Component breakdown
- `GET /health` - System health status
- `POST /clear` - Clear error history (admin only)

---

## Usage Examples

### Programmatic Access

```python
from src.utils.error_metrics import get_metrics_collector

# Get collector instance
collector = get_metrics_collector()

# Get overall summary
summary = collector.get_summary()
print(f"Total errors: {summary['total_errors']}")

# Get stats for specific component
kb_stats = collector.get_stats(component="knowledge_base")
for stats in kb_stats:
    print(f"{stats.error_code}: {stats.total_count} errors")

# Get recent errors
recent = collector.get_recent_errors(limit=50, component="llm_service")
for error in recent:
    print(f"[{error.timestamp}] {error.component}/{error.function}: {error.message}")

# Get error timeline
timeline = collector.get_error_timeline(hours=24)
for hour, errors in timeline.items():
    print(f"{hour}: {len(errors)} errors")

# Set alert threshold
collector.set_alert_threshold("chat_workflow", error_code=None, threshold=15)

# Mark error resolved
await collector.mark_resolved(trace_id="error_abc123")

# Clean up old metrics
removed = await collector.cleanup_old_metrics()
print(f"Removed {removed} old metrics")
```

### Manual Error Recording

```python
from src.utils.error_metrics import record_error_metric
from src.utils.error_boundaries import ErrorCategory

# Manually record error metric
await record_error_metric(
    error_code="CUSTOM_001",
    category=ErrorCategory.SERVER_ERROR,
    component="custom_component",
    function="custom_function",
    message="Something went wrong",
    trace_id="trace_123",
    user_id="user_456",
    retry_attempted=True,
)
```

---

## Integration Points

### 1. Error Boundaries

Error metrics are automatically recorded by error boundaries:

- `@error_boundary` decorator - Service layer
- `@with_error_handling` decorator - API endpoints
- Error context managers - Manual error handling

### 2. Error Catalog

Metrics can include error codes from the error catalog:

```python
from src.utils.catalog_http_exceptions import raise_kb_error

# Error code "KB_0001" automatically tracked in metrics
raise_kb_error("KB_0001", "Search failed")
```

### 3. Redis (Optional)

If Redis client is provided, metrics are persisted:

```python
from src.utils.redis_client import get_redis_client
from src.utils.error_metrics import get_metrics_collector

redis = get_redis_client(database="main")
collector = get_metrics_collector(redis_client=redis)
```

---

## Metrics Data Model

### ErrorMetric

Single error occurrence:

```python
@dataclass
class ErrorMetric:
    error_code: Optional[str]      # From error catalog
    category: str                   # ErrorCategory value
    component: str                  # Component name
    function: str                   # Function name
    timestamp: float                # Unix timestamp
    message: str                    # Error message
    trace_id: Optional[str]         # Trace ID for tracking
    user_id: Optional[str]          # User associated with error
    retry_attempted: bool           # Was retry attempted
    resolved: bool                  # Has error been resolved
```

### ErrorStats

Aggregated statistics:

```python
@dataclass
class ErrorStats:
    error_code: Optional[str]       # From error catalog
    category: str                   # ErrorCategory value
    component: str                  # Component name
    total_count: int                # Total occurrences
    last_occurrence: Optional[float] # Last occurrence timestamp
    first_occurrence: Optional[float] # First occurrence timestamp
    hourly_counts: Dict[str, int]   # Counts per hour
    retry_count: int                # Number of retries
    resolved_count: int             # Number resolved
    error_rate: float               # Errors per minute
```

---

## Configuration

### Memory Limits

```python
collector._max_metrics_memory = 10000  # Keep last 10k metrics
```

### Retention Period

```python
collector._retention_seconds = 86400  # 24 hours
```

### Alert Thresholds

```python
collector.set_alert_threshold(
    component="knowledge_base",
    error_code="KB_0001",  # Or None for any error
    threshold=10           # Alert at 10 errors
)
```

---

## Best Practices

### ✅ DO:

- **Use automatic collection** via error boundaries
- **Set alert thresholds** for critical components
- **Monitor error rates** regularly
- **Mark errors resolved** when fixed
- **Clean up old metrics** periodically
- **Use component filtering** for focused analysis
- **Track retry rates** to identify transient issues

### ❌ DON'T:

- **Manually record metrics** unless necessary (use error boundaries)
- **Set thresholds too low** (causes alert fatigue)
- **Ignore high error rates** - investigate and fix
- **Store sensitive data** in error messages
- **Disable metrics collection** in production

---

## Alerting

When error count exceeds threshold:

```
⚠️ Error alert threshold exceeded: knowledge_base:KB_0001 (15 >= 10)
```

Logged to application logs. Can be extended to:
- Send email notifications
- Post to Slack/Discord
- Create incident tickets
- Trigger automated remediation

---

## Performance Considerations

### Memory Usage

- In-memory storage: ~1KB per error metric
- 10,000 metrics = ~10MB memory
- Old metrics automatically cleaned up

### Redis Usage (Optional)

- Stored in sorted sets by timestamp
- 24-hour TTL (auto-expires)
- ~500 bytes per metric

### API Response Times

- Summary: <50ms
- Recent errors: <100ms (10k metrics)
- Timeline: <200ms (24 hours)
- Top errors: <50ms

---

## Troubleshooting

### No Metrics Collected

**Cause:** Error boundaries not integrated

**Fix:** Ensure error boundaries are applied:
```python
@error_boundary(component="my_component", function="my_func")
async def my_function():
    ...
```

### High Memory Usage

**Cause:** Too many metrics in memory

**Fix:** Reduce retention or max metrics:
```python
collector._max_metrics_memory = 5000
```

### Metrics Not Persisting

**Cause:** Redis client not configured

**Fix:** Provide Redis client:
```python
collector = get_metrics_collector(redis_client=redis)
```

### Alert Threshold Not Working

**Cause:** Threshold not set correctly

**Fix:** Verify threshold configuration:
```python
collector.set_alert_threshold("component", "code", 10)
```

---

## Monitoring Dashboard (Future)

**Planned features:**

- Real-time error dashboard UI
- Grafana/Prometheus integration
- Error trend visualizations
- Automated incident response
- SLA monitoring and reporting

---

## Related Documentation

- **Error Boundaries:** `src/utils/error_boundaries.py`
- **Error Catalog:** `docs/developer/ERROR_CODE_CONVENTIONS.md`
- **Error Metrics:** `src/utils/error_metrics.py`
- **API Endpoints:** `backend/api/error_monitoring.py`
- **Tests:** `tests/test_error_metrics.py`

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2025-11-09 | Initial error monitoring and observability system |

---

**For questions or issues, see:** `docs/system-state.md`
