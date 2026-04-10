# CausalInferenceEngine - Integration Guide

## How to Integrate into AutoBot

### 1. Register Diagnostics API Routes

In `autobot-backend/main.py` or your FastAPI app initialization:

```python
from api.diagnostics import router as diagnostics_router

app = FastAPI()

# Register diagnostics endpoints
app.include_router(diagnostics_router)
```

This exposes:
- `POST /api/diagnostics/analyze-failure` — Analyze task failure
- `GET /api/diagnostics/health` — Service health check
- `GET /api/diagnostics/analyze-failure?task_id=...` — Alternative GET endpoint

### 2. Using CausalInferenceEngine Directly

```python
from services.causal_inference_engine import CausalInferenceEngine

engine = CausalInferenceEngine()

# Analyze a task failure
report = await engine.analyze_failure(
    task_id="task-123",
    error_description="Database query timeout after deployment"
)

# Access results
print(f"Severity: {report.severity.value}")
print(f"Confidence: {report.confidence:.1%}")
print(f"Root cause: {report.root_cause.name if report.root_cause else 'Unknown'}")
print(f"Chain depth: {report.chain_depth}")
print(f"Confounders: {len(report.confounders)}")

for rec in report.recommendations:
    print(f"  - {rec}")

# Serialize to JSON for API response
report_dict = report.to_dict()
```

### 3. Integration with Error Handler

Use CausalInferenceEngine in your error handling middleware:

```python
import asyncio
from fastapi import Request
from fastapi.responses import JSONResponse
from services.causal_inference_engine import CausalInferenceEngine

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log error normally
    logger.error("Unhandled exception: %s", exc, exc_info=True)
    
    # Optionally trigger causal analysis
    if should_analyze(exc):  # Your own logic
        try:
            engine = CausalInferenceEngine()
            report = await asyncio.wait_for(
                engine.analyze_failure(
                    task_id=request.headers.get("X-Task-ID", "unknown"),
                    error_description=str(exc)
                ),
                timeout=0.5  # Don't block error response
            )
            
            # Include analysis in error response
            return JSONResponse(
                status_code=500,
                content={
                    "error": str(exc),
                    "analysis": report.to_dict() if report else None
                }
            )
        except asyncio.TimeoutError:
            # Analysis took too long, just return error
            logger.warning("Causal analysis timeout for error: %s", exc)
        except Exception as analysis_error:
            # Analysis failed, don't fail the error handler
            logger.warning("Causal analysis failed: %s", analysis_error)
    
    return JSONResponse(
        status_code=500,
        content={"error": str(exc)}
    )
```

### 4. Integration with Monitoring/Alerts

Send analysis results to your monitoring system:

```python
from services.causal_inference_engine import CausalInferenceEngine, Severity

async def on_critical_error(task_id: str, error_msg: str):
    """Called when a critical error occurs."""
    
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_msg)
    
    # Send to monitoring
    if report.severity == Severity.CRITICAL:
        send_alert(
            title=f"Critical: {report.root_cause.name if report.root_cause else 'Unknown error'}",
            message=f"Chain depth: {report.chain_depth}, Confounders: {len(report.confounders)}",
            recommendations=report.recommendations,
            severity="critical"
        )
    elif report.severity == Severity.DEGRADED:
        send_notification(
            title=f"Degraded: {report.root_cause.name if report.root_cause else 'Unknown error'}",
            message="\n".join(report.recommendations)
        )
```

### 5. Postmortem Analysis Endpoint

Create a dedicated endpoint for incident analysis:

```python
from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

@router.post("/analyze")
async def analyze_incident(
    task_id: str,
    error_description: str,
    incident_time: str = None
):
    """Analyze completed incident and generate postmortem."""
    
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_description)
    
    if not report or report.analysis_status == "failed":
        raise HTTPException(
            status_code=500,
            detail="Failed to analyze incident"
        )
    
    # Generate postmortem
    postmortem = {
        "incident_id": task_id,
        "timestamp": incident_time or datetime.now(tz=timezone.utc).isoformat(),
        "severity": report.severity.value,
        "confidence": report.confidence,
        
        "root_cause": {
            "name": report.root_cause.name if report.root_cause else "Unknown",
            "type": report.root_cause.event_type if report.root_cause else None,
            "description": report.root_cause.description if report.root_cause else None,
        },
        
        "causal_chain": [
            {
                "event": e.name,
                "type": e.event_type,
                "depth": e.depth,
                "confidence": e.confidence
            }
            for e in report.causal_chain
        ],
        
        "confounders": [
            {
                "event": c.name,
                "type": c.event_type,
                "confidence": c.confidence
            }
            for c in report.confounders
        ],
        "confounding_strength": report.confounding_strength,
        
        "recommendations": report.recommendations,
        "analysis_duration_ms": report.analysis_duration_ms,
    }
    
    return postmortem
```

### 6. Pattern Detection

Track recurring failures:

```python
from autobot_shared.redis_client import get_async_redis_client
from services.causal_inference_engine import CausalInferenceEngine

async def track_failure_pattern(task_id: str, error_msg: str):
    """Analyze failure and track if it's a recurring pattern."""
    
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_msg)
    
    if report and report.root_cause:
        redis = await get_async_redis_client(database="analytics")
        
        # Track failures by root cause type
        failure_key = f"failures:by_root_cause:{report.root_cause.event_type}"
        await redis.incr(failure_key)
        
        # Set expiry (track last 7 days)
        await redis.expire(failure_key, 7 * 24 * 3600)
        
        # If > 5 occurrences in 7 days, flag as pattern
        count = await redis.get(failure_key)
        if int(count) > 5:
            pattern_key = f"patterns:flagged"
            await redis.sadd(pattern_key, report.root_cause.event_type)
```

### 7. Automated Fix Suggestions

Combine analysis with automated fixes:

```python
from services.causal_inference_engine import (
    CausalInferenceEngine,
    RecommendationType,
    Severity
)

async def apply_automated_fixes(task_id: str, error_msg: str):
    """Apply immediate automated fixes based on analysis."""
    
    engine = CausalInferenceEngine()
    report = await engine.analyze_failure(task_id, error_msg)
    
    if not report or report.severity != Severity.CRITICAL:
        return None
    
    # Find IMMEDIATE interventions (safe to auto-apply)
    immediate = [
        i for i in report.interventions
        if i.recommendation_type == RecommendationType.IMMEDIATE
        and i.predicted_success_rate >= 0.8
        and i.confidence >= 0.9
    ]
    
    for intervention in immediate:
        # Apply automated fix
        if "retry" in intervention.name.lower():
            # Trigger retry
            await trigger_retry(task_id)
            logger.info("Applied: %s", intervention.name)
        
        elif "timeout" in intervention.name.lower():
            # Increase timeout (if safe)
            await increase_timeout(task_id)
            logger.info("Applied: %s", intervention.name)
        
        elif "cache" in intervention.name.lower():
            # Clear or refresh cache
            await refresh_cache(task_id)
            logger.info("Applied: %s", intervention.name)
    
    return len(immediate) > 0
```

### 8. Testing the Integration

```python
import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def test_diagnostics_endpoint():
    """Test failure analysis endpoint."""
    
    response = client.post(
        "/api/diagnostics/analyze-failure",
        json={
            "task_id": "test-task-1",
            "error_description": "Database connection timeout"
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert "data" in data
    report = data["data"]
    
    assert "task_id" in report
    assert "severity" in report
    assert "confidence" in report
    assert "recommendations" in report

def test_health_check():
    """Test service health endpoint."""
    
    response = client.get("/api/diagnostics/health")
    
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
```

## Dependencies

The CausalInferenceEngine requires:

1. **Services:**
   - `services.root_cause_analyzer.RootCauseAnalyzer`
   - `context_aware_decision.counterfactual_reasoner.CounterfactualReasoner`
   - `services.confounder_control_analyzer.ConfounderControlAnalyzer`

2. **Infrastructure:**
   - `knowledge.temporal_search.TemporalSearchService`
   - `autobot_shared.redis_client.get_async_redis_client` (async Redis)

3. **Framework:**
   - FastAPI (for API endpoints)
   - Pydantic (for request/response models)

All dependencies are already in the codebase.

## Configuration

No additional configuration needed. The engine uses:
- Redis database: `knowledge` (for temporal search)
- Analysis timeout: 500ms (configurable via `ANALYSIS_TIMEOUT_MS` constant)
- Max chain depth: 5 events (configurable)
- Min confidence for recommendations: 0.4 (configurable)

## Logging

All operations are logged to `logging.getLogger(__name__)`:

```python
import logging

logger = logging.getLogger(__name__)

# Enable debug logging for analysis details
logging.getLogger("services.causal_inference_engine").setLevel(logging.DEBUG)
```

Log output includes:
- Analysis start/completion with timing
- Chain depth, confounding strength, confidence
- Intervention generation and ranking
- Severity assessment
- Errors during analysis (with stack traces)

## Performance Tuning

If analysis is slow:

1. **Reduce max_depth** in traverse step:
   ```python
   # In RootCauseAnalyzer.analyze_task_failure()
   chain = await self.temporal_service.find_causal_chain(
       event_id=error_event_id,
       direction="backward",
       max_depth=3  # Reduce from 5
   )
   ```

2. **Cache intervention generation**:
   ```python
   from functools import lru_cache
   
   @lru_cache(maxsize=100)
   def _cached_interventions(event_type: str):
       # Generate once, reuse
   ```

3. **Parallel analysis** (if analyzing multiple tasks):
   ```python
   import asyncio
   
   results = await asyncio.gather(
       engine.analyze_failure("task-1"),
       engine.analyze_failure("task-2"),
       engine.analyze_failure("task-3"),
   )
   ```

## Troubleshooting

### Issue: Analysis returns "failed" status

**Cause:** Base RootCauseAnalyzer failed to find causal chain.

**Fix:**
1. Check Redis connectivity
2. Verify task_id exists in Redis
3. Check temporal_search service initialization

### Issue: Confidence is very low (< 0.4)

**Cause:** Shallow chain, low event quality, or high confounding.

**Fix:**
1. Improve event quality (ensure confidence scores are high)
2. Traverse deeper chains (check temporal_search configuration)
3. Reduce confounding by analyzing multi-factor separately

### Issue: Analysis takes too long (> 500ms)

**Cause:** Deep chain traversal or many interventions.

**Fix:**
1. Reduce max_chain_depth
2. Cache intervention generation
3. Profile with `analysis_duration_ms` in report

## Next Steps

1. **Integration:** Add diagnostics routes to main FastAPI app
2. **Testing:** Run test suite to verify all components work
3. **Deployment:** Deploy to production with monitoring
4. **Monitoring:** Track analysis success rate, confidence distribution
5. **Feedback:** Collect user feedback on recommendation quality
6. **Enhancement:** Tune confidence/severity thresholds based on data
