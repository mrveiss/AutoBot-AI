---
tags: [type/reference, status/current, component/backend]
date: 2026-06-04
issue: 4069
---

# Causal Inference — Integration Guide

How to wire `CausalInferenceEngine` and related services into AutoBot backend code.

See [[causal-inference-algorithms]] for scoring formulas and [[causal-error-recovery]] for the error-recovery layer built on top.

---

## Register the Diagnostics Router

In `autobot-backend/main.py`:

```python
from api.diagnostics import router as diagnostics_router
app.include_router(diagnostics_router)
```

Exposes:
- `POST /api/diagnostics/analyze-failure`
- `GET  /api/diagnostics/health`

---

## Direct Usage

```python
from services.causal_inference_engine import CausalInferenceEngine

engine = CausalInferenceEngine()
report = await engine.analyze_failure(
    task_id="task-123",
    error_description="Database query timeout after deployment",
)

print(f"Severity:    {report.severity.value}")
print(f"Confidence:  {report.confidence:.1%}")
print(f"Root cause:  {report.root_cause.name if report.root_cause else 'Unknown'}")
for rec in report.recommendations:
    print(f"  - {rec}")
```

---

## In a FastAPI Exception Handler

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from services.causal_inference_engine import CausalInferenceEngine
import asyncio

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception: %s", exc, exc_info=True)

    report = None
    if should_analyze(exc):
        try:
            engine = CausalInferenceEngine()
            report = await asyncio.wait_for(
                engine.analyze_failure(
                    task_id=request.headers.get("X-Task-ID", "unknown"),
                    error_description=str(exc),
                ),
                timeout=0.5,  # never block the error response
            )
        except (asyncio.TimeoutError, Exception) as inner:
            logger.warning("Causal analysis failed: %s", inner)

    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "analysis": report.to_dict() if report else None},
    )
```

---

## With Monitoring / Alerts

```python
from services.causal_inference_engine import CausalInferenceEngine, Severity

async def on_critical_error(task_id: str, error_msg: str):
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_msg)

    if report.severity == Severity.CRITICAL:
        send_alert(
            title=f"Critical: {report.root_cause.name if report.root_cause else 'Unknown'}",
            message=f"Chain depth: {report.chain_depth}, Confounders: {len(report.confounders)}",
            recommendations=report.recommendations,
            severity="critical",
        )
```

---

## Postmortem Endpoint

```python
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

@router.post("/analyze")
async def analyze_incident(task_id: str, error_description: str, incident_time: str = None):
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_description)

    if not report or report.analysis_status == "failed":
        raise HTTPException(status_code=500, detail="Failed to analyze incident")

    return {
        "incident_id": task_id,
        "timestamp": incident_time or datetime.now(tz=timezone.utc).isoformat(),
        "severity": report.severity.value,
        "confidence": report.confidence,
        "root_cause": {
            "name": report.root_cause.name if report.root_cause else "Unknown",
            "type": report.root_cause.event_type if report.root_cause else None,
        },
        "causal_chain": [
            {"event": e.name, "type": e.event_type, "depth": e.depth, "confidence": e.confidence}
            for e in report.causal_chain
        ],
        "confounders": [
            {"event": c.name, "confidence": c.confidence}
            for c in report.confounders
        ],
        "confounding_strength": report.confounding_strength,
        "recommendations": report.recommendations,
        "analysis_duration_ms": report.analysis_duration_ms,
    }
```

---

## Recurring Failure Pattern Tracking

```python
from autobot_shared.redis_client import get_async_redis_client
from services.causal_inference_engine import CausalInferenceEngine

async def track_failure_pattern(task_id: str, error_msg: str):
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_msg)

    if report and report.root_cause:
        redis = await get_async_redis_client(database="analytics")
        key = f"failures:by_root_cause:{report.root_cause.event_type}"
        await redis.incr(key)
        await redis.expire(key, 7 * 24 * 3600)  # 7-day window

        if int(await redis.get(key)) > 5:
            await redis.sadd("patterns:flagged", report.root_cause.event_type)
```

---

## Configuration

No additional config required. Engine uses:

| Setting | Default | Override |
|---|---|---|
| Redis database | `knowledge` | — |
| Analysis timeout | 500 ms | `ANALYSIS_TIMEOUT_MS` constant |
| Max chain depth | 5 events | `MAX_CHAIN_DEPTH` constant |
| Min recommendation confidence | 0.4 | `MIN_CONFIDENCE` constant |

---

## Performance Tuning

If analysis is slow, reduce traversal depth:

```python
# In RootCauseAnalyzer.analyze_task_failure()
chain = await self.temporal_service.find_causal_chain(
    event_id=error_event_id,
    direction="backward",
    max_depth=3,  # reduce from default 5
)
```

For parallel analysis of multiple tasks:

```python
results = await asyncio.gather(
    engine.analyze_failure("task-1", error_1),
    engine.analyze_failure("task-2", error_2),
)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `analysis_status == "failed"` | RootCauseAnalyzer can't find chain | Check Redis connectivity; verify task_id exists |
| Confidence < 0.4 | Shallow chain or high confounding | Improve event quality; traverse deeper chains |
| Analysis > 500 ms | Deep chain or many interventions | Reduce `max_depth`; cache intervention generation |
