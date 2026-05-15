# Error Monitoring Dashboard Design

**Issue:** #563 - [Frontend] Error Monitoring Dashboard - 13 Endpoints
**Date:** 2026-02-04
**Status:** Implementation

## Overview

Implement comprehensive Error Monitoring Dashboard backend in SLM server (172.16.168.19) with 13 REST endpoints, plus frontend integration in slm-admin.

## Backend Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/errors/statistics` | Overall error statistics |
| GET | `/api/errors/recent` | Recent error list with pagination |
| GET | `/api/errors/categories` | Error categories breakdown |
| GET | `/api/errors/components` | Errors by component/service |
| GET | `/api/errors/health` | Error subsystem health status |
| POST | `/api/errors/clear` | Clear error history |
| POST | `/api/errors/test-error` | Generate test error for validation |
| GET | `/api/errors/metrics/summary` | Aggregated metrics summary |
| GET | `/api/errors/metrics/timeline` | Time-series error data |
| GET | `/api/errors/metrics/top-errors` | Most frequent errors |
| POST | `/api/errors/metrics/resolve/{event_id}` | Mark error as resolved |
| POST | `/api/errors/metrics/alert-threshold` | Configure alert thresholds |
| POST | `/api/errors/metrics/cleanup` | Cleanup old errors |

## Schema Changes

**Migration 012: Add error resolution fields to NodeEvent**

```sql
ALTER TABLE node_events ADD COLUMN resolved BOOLEAN DEFAULT FALSE;
ALTER TABLE node_events ADD COLUMN resolved_at TIMESTAMP NULL;
ALTER TABLE node_events ADD COLUMN resolved_by VARCHAR(255) NULL;
```

**Settings Keys for Alert Thresholds:**
- `error_alert_threshold_critical`: 50 (errors/hour)
- `error_alert_threshold_warning`: 20 (errors/hour)
- `error_retention_days`: 30

## Response Models

### ErrorStatistics
```python
class ErrorStatistics(BaseModel):
    total_errors: int
    errors_24h: int
    errors_7d: int
    errors_30d: int
    resolved_count: int
    unresolved_count: int
    error_rate_per_hour: float
    trend: str  # "increasing", "decreasing", "stable"
```

### ErrorTimelinePoint
```python
class ErrorTimelinePoint(BaseModel):
    timestamp: datetime
    count: int
    critical: int
    error: int
```

### TopError
```python
class TopError(BaseModel):
    event_type: str
    message: str
    count: int
    last_occurred: datetime
    affected_nodes: List[str]
```

## Files Modified

**Backend:**
- `slm-server/api/errors.py` (new)
- `slm-server/migrations/012_add_error_resolution_fields.py` (new)
- `slm-server/main.py` (add router)

**Frontend:**
- `slm-admin/src/composables/useSlmApi.ts` (add methods)
- `slm-admin/src/views/monitoring/ErrorMonitor.vue` (connect API)

## Implementation Order

1. Database migration
2. Backend errors router
3. Register router in main.py
4. Frontend API composable methods
5. Frontend component integration
