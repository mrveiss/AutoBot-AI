---
tags: [type/architecture, status/current, component/backend]
date: 2026-06-04
issue: 2154
---

# Causal Error Recovery — Architecture

The Causal Error Recovery system enhances workflow error handling by diagnosing *why* errors occur (root-cause analysis) and recommending targeted recovery strategies based on causal chains and historical resolution data.

See [[causal-error-recovery-api]] for the public API and [[causal-inference-algorithms]] for scoring details.

---

## Flow

```
Error in workflow step
        ↓
StepErrorHandler.handle_error()
        ↓  (if enable_causal_analysis=True)
_analyze_and_recommend_recovery()
        ↓
┌─────────────────────────────┐
│ CausalErrorAnalyzer         │
│  - Uses Think Tool          │
│  - Traces causal chain      │
│  - Identifies confounders   │
└─────────────────────────────┘
        ↓  CausalErrorAnalysis
┌─────────────────────────────┐
│ CausalErrorRecovery         │
│  - Generates RecoveryActions│
│  - Scores by likelihood /   │
│    cost / risk              │
│  - Checks pattern history   │
└─────────────────────────────┘
        ↓  RecoveryPlan (top 3 actions)
Caller executes recommended action
        ↓
FailurePatternDetector records outcome
        ↓
Future identical chains get confidence boost
```

---

## Key Files

| File | Responsibility |
|---|---|
| `orchestration/causal_error_recovery.py` | Recovery recommendations + pattern storage |
| `orchestration/causal_error_analyzer.py` | Root-cause analysis via Think Tool |
| `services/failure_pattern_detector.py` | Pattern learning + detection |
| `orchestration/error_handler.py` | Integration point — StepErrorHandler |

---

## Error Classification

**Leaf error** — immediate cause (single arrow in causal chain). Example: `"Network timeout"`.

**Downstream error** — cascades from upstream. Example: `"Database down → Connection refused → Timeout"`.

---

## RecoveryAction Enum

```python
RETRY_IMMEDIATELY        # Transient, try again now
RETRY_WITH_BACKOFF       # Wait then retry (exponential)
WAIT_FOR_DEPENDENCY      # External resource starting up
RESTRUCTURE_WORKFLOW     # Fix step ordering/dependencies
ESCALATE                 # Manual operator intervention
SKIP_STEP                # Skip optional step
FALLBACK_TO_ALTERNATIVE  # Execute backup step
SCALE_RESOURCES          # Add connections/memory/capacity
CIRCUIT_BREAK            # Fail-fast to prevent cascades
```

---

## Recovery Strategy Selection

```python
def _generate_recovery_actions(error_type, root_cause):
    if "timeout" in error_type or "connection" in error_type:
        → RETRY_WITH_BACKOFF, WAIT_FOR_DEPENDENCY

    if any(x in root_cause for x in ["pool", "resource", "capacity"]):
        → WAIT_FOR_DEPENDENCY, SCALE_RESOURCES

    if any(x in root_cause for x in ["ordering", "dependency", "sequence"]):
        → RESTRUCTURE_WORKFLOW, SKIP_STEP

    if any(x in error_type for x in ["permission", "auth", "forbidden"]):
        → ESCALATE

    fallback:
        → RETRY_IMMEDIATELY, RETRY_WITH_BACKOFF, ESCALATE

    # Return top 3 sorted by score = likelihood×2 - cost - risk
```

---

## Pattern Learning via Redis

```
failure:pattern:{md5(causal_chain)[:16]}:count       → occurrence count
failure:pattern:{hash}:chain                          → causal chain string
failure:pattern:{hash}:stats                          → JSON metadata
failure:patterns:known                                → Set of all known hashes
```

TTL: 30 days on all keys.

**Confidence progression:**
1. First error → `count=1, confidence=0.7`
2. Second error (same chain, resolved) → `resolution_success_rate=1.0`
3. Third+ error → `is_known_pattern=True`, confidence approaches 1.0

---

## Integration with StepErrorHandler

```python
class StepErrorHandler:
    def __init__(self, enable_causal_analysis: bool = True):
        ...

# Result dict gains one new optional key:
{
    "action": StepErrorAction,
    "delay": float,
    "fallback_id": Optional[str],
    "reason": str,
    "recovery_plan": Optional[Dict],  # ← NEW
}
```

Existing callers that don't check `recovery_plan` are unaffected.

---

## Graceful Degradation

| Failure point | Behaviour |
|---|---|
| Causal analysis fails | Log warning, continue with `error_config` handling |
| Pattern detection unavailable | Treat as new pattern, confidence=0.7 |
| Recovery recommender fails | Skip `recovery_plan`, use `error_config` only |
| Redis unavailable | Pattern storage skipped; base heuristics still run |
| Think Tool unavailable | Log debug, skip causal analysis entirely |

---

## Performance

| Step | Typical latency |
|---|---|
| Causal analysis | 150–200 ms (async) |
| Pattern detection | 20–50 ms (single Redis lookup) |
| Recovery recommendations | < 100 ms (linear scan of ~10 rules) |
| Pattern storage | < 100 ms (async write) |
| **Total overhead per error** | **~250 ms** |

Analysis is non-blocking — a 500 ms `asyncio.wait_for` timeout prevents it from blocking workflow error responses.
