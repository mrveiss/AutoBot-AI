---
tags: [type/architecture, status/current, component/backend]
date: 2026-04-10
issue: 2154
---

# Causal Error Recovery System Design

## Overview

The Causal Error Recovery System enhances AutoBot's error handling by understanding *why* errors occur (root-cause analysis) and recommending targeted recovery strategies based on causal chains, error patterns, and historical resolution data.

**Files:**
- `causal_error_recovery.py` (448 lines) - Recovery recommendations + pattern storage
- `causal_error_analyzer.py` (234 lines) - Root-cause analysis via Think Tool
- `services/failure_pattern_detector.py` (315 lines) - Pattern learning + detection
- `error_handler.py` (enhanced, 500+ lines) - Integration point
- `tests/orchestration/test_causal_error_recovery.py` (550+ lines) - Comprehensive tests

## Architecture

```
Error occurs in workflow step
            ↓
    StepErrorHandler.handle_error()
            ↓
    (If enable_causal_analysis=True)
            ↓
    _analyze_and_recommend_recovery()
            ↓
    ┌─────────────────────────────────┐
    │ CausalErrorAnalyzer             │
    │ - Uses Think Tool               │
    │ - Traces causal chain           │
    │ - Identifies confounders        │
    └─────────────────────────────────┘
            ↓
    CausalErrorAnalysis {
      root_cause,
      causal_chain,
      confounders,
      confidence
    }
            ↓
    ┌─────────────────────────────────┐
    │ CausalErrorRecovery             │
    │ - Generates recovery actions    │
    │ - Scores by likelihood/cost/risk│
    │ - Checks pattern history        │
    └─────────────────────────────────┘
            ↓
    RecoveryPlan {
      recommended_actions: [top 3],
      is_known_pattern,
      confidence,
      expected_outcomes
    }
            ↓
    Return to caller with recovery_plan
            ↓
    Caller executes recommended action
            ↓
    Record success/failure in FailurePatternDetector
            ↓
    Improve future recommendations via feedback loop
```

## Key Concepts

### 1. Error Classification

**Leaf Error:** Immediate cause (single arrow in causal chain)
- Example: "Network timeout" → Direct network issue

**Downstream Error:** Cascading from upstream (multiple arrows)
- Example: "Database down → Connection refused → Timeout"

### 2. RecoveryAction Enum

```python
RETRY_IMMEDIATELY          # Transient, try again now
RETRY_WITH_BACKOFF         # Wait, then retry (exponential)
WAIT_FOR_DEPENDENCY        # External service/resource starting up
RESTRUCTURE_WORKFLOW       # Fix step ordering/dependencies
ESCALATE                   # Manual operator intervention
SKIP_STEP                  # Skip optional step
FALLBACK_TO_ALTERNATIVE    # Execute backup step
SCALE_RESOURCES            # Add connections/memory/capacity
CIRCUIT_BREAK              # Fail-fast to prevent cascades
```

### 3. RecoveryPlan Structure

```python
RecoveryPlan {
    error_id: str                              # Unique ID for this error
    error_type: str                            # Exception class name
    root_cause: str                            # Root cause from analysis
    causal_chain: str                          # "A → B → C" visualization
    is_leaf_error: bool                        # Immediate vs cascading
    is_known_pattern: bool                     # Seen this before?
    pattern_frequency: int                     # How many times?
    recommended_actions: [RecoveryAction_, ...] # Top 3 actions
    confidence: float                          # 0.0-1.0 overall confidence
}

RecoveryAction_ {
    action: RecoveryAction                     # What to do
    description: str                           # Why this action
    likelihood_to_succeed: float               # 0.0-1.0 probability
    cost: float                                # Resource cost 0.0-1.0
    risk: float                                # Risk of side effects 0.0-1.0
    expected_outcome: str                      # What happens if it works
    estimated_delay_seconds: float             # How long it takes
    
    @property score: float                     # likelihood*2 - cost - risk
}
```

## Example: Network Timeout Error

### Scenario
A workflow step calls an external API with a 30-second timeout. The network experiences temporary congestion, and the request times out.

### Causal Analysis Flow

```
Error: TimeoutError("Connection timed out after 30s")

→ CausalErrorAnalyzer.analyze_error_causally()
  ├─ Context: Step "call_api", workflow "process_order"
  ├─ History: [API available 2min ago, traffic spike detected]
  └─ Think Tool output (with causal reasoning):
     "Network congestion detected in ISP backbone.
      Increased latency (100ms → 500ms) → Connection timeout.
      This is a transient condition that will clear."
     
→ CausalErrorAnalysis {
    error_description: "Connection timeout after 30s",
    root_cause: "Network congestion",
    causal_chain: "Traffic spike → High latency → Timeout",
    confounders_identified: ["DNS resolution time"],
    confidence: 0.85,
    recommended_action: "Retry with exponential backoff"
}
```

### Recovery Recommendation

```python
await recovery_recommender.recommend_recovery(
    error=TimeoutError(...),
    causal_analysis=...,
    execution_context={...}
)

→ _generate_recovery_actions() classifies based on error_type
   Matches: "timeout" in error_type.lower()
   
→ Recovery Actions Generated:
   1. RETRY_WITH_BACKOFF
      - likelihood: 0.75 (network congestion usually clears)
      - cost: 0.1 (one extra request)
      - risk: 0.05 (low risk of side effects)
      - score: 0.75*2 - 0.1 - 0.05 = 1.35
      - delay: 2 seconds
      
   2. WAIT_FOR_DEPENDENCY
      - likelihood: 0.65
      - cost: 0.2
      - risk: 0.1
      - score: 1.10
      - delay: 5 seconds
      
   3. ESCALATE
      - likelihood: 0.5
      - cost: 0.0
      - risk: 0.0
      - score: 1.0

→ Sorted by score:
   [RETRY_WITH_BACKOFF, WAIT_FOR_DEPENDENCY, ESCALATE]

→ RecoveryPlan {
    error_id: "TimeoutError:12345",
    root_cause: "Network congestion",
    causal_chain: "Traffic spike → High latency → Timeout",
    is_leaf_error: True,
    is_known_pattern: False (first occurrence),
    pattern_frequency: 0,
    recommended_actions: [
        {action: RETRY_WITH_BACKOFF, score: 1.35, ...},
        {action: WAIT_FOR_DEPENDENCY, score: 1.10, ...},
        {action: ESCALATE, score: 1.0, ...}
    ],
    confidence: 0.85
}
```

### Execution & Feedback

1. **Executor receives plan** → Executes RETRY_WITH_BACKOFF
2. **Request succeeds after 2s retry** → Network congestion cleared
3. **Record feedback**:
   ```python
   await recovery_recommender.record_recovery_attempt(
       recovery_plan=plan,
       action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
       success=True,
       outcome="Connection re-established after 2s delay"
   )
   ```
4. **Pattern detector learns**:
   - Hash causal chain: "Traffic spike → High latency → Timeout"
   - Increment count
   - Record resolution: "RETRY_WITH_BACKOFF worked"
5. **Next timeout with same causal chain** → Is known pattern
   - `is_known_pattern: True`
   - `pattern_frequency: 2`
   - `confidence: 0.85 + 0.15 = 1.0` (boosted by pattern recognition)

## Pattern Detection & Learning

### Pattern Storage in Redis

```
Key: failure:pattern:eda1b2c3d4e5f6g7
  - Count: "failure:pattern:eda1b2c3d4e5f6g7:count" → 5
  - Chain: "failure:pattern:eda1b2c3d4e5f6g7:chain" → "Traffic spike → Timeout"
  - Stats: "failure:pattern:eda1b2c3d4e5f6g7:stats" → {
      occurrence_count: 5,
      error_types: ["TimeoutError", "ConnectionError"],
      successful_resolutions: ["retry_with_backoff", "retry_with_backoff", "wait_for_dependency"],
      resolution_success_rate: 1.0,
      confidence: 0.95
    }
```

### Learning Process

1. **First error**: Create new pattern, count=1, confidence=0.7
2. **Second error (same chain)**: Detect pattern, count=2
3. **Record success**: resolution_success_rate = 1/1 = 100%
4. **Third error (same chain)**: 
   - Detect pattern, count=3
   - Record success: resolution_success_rate = 2/2 = 100%
   - Boost confidence: min(1.0, 0.7 + 0.3) = 1.0
5. **Future calls with same causal chain**:
   - `is_known_pattern: True`
   - `pattern_frequency: 3`
   - Recommendations informed by history

## Integration with Error Handler

### Before Enhancement
```python
async def handle_error(step, error, attempt, execution_context):
    """Log, retry, or abort based on error_config."""
    config = self._parse_config(step)
    
    if config.action == RETRY and attempt < config.max_retries:
        delay = self._compute_delay(config, attempt)
        await asyncio.sleep(delay)
        return {"action": RETRY, "delay": delay, ...}
    
    # ... other actions
```

### After Enhancement
```python
async def handle_error(step, error, attempt, execution_context):
    """Same as before + causal analysis."""
    config = self._parse_config(step)
    
    # NEW: Perform causal analysis (async, non-blocking on failure)
    recovery_plan_dict = None
    if self.enable_causal_analysis:
        try:
            recovery_plan_dict = await self._analyze_and_recommend_recovery(
                error, step, execution_context
            )
        except Exception as exc:
            logger.debug("Causal analysis failed: %s", exc)
    
    # ... existing error handling logic ...
    
    # NEW: Include recovery_plan in response
    result = {
        "action": RETRY,
        "delay": delay,
        "fallback_id": None,
        "reason": f"retry {attempt + 1}/{max_retries}",
    }
    if recovery_plan_dict:
        result["recovery_plan"] = recovery_plan_dict  # NEW
    
    return result
```

**Backward Compatibility:**
- `enable_causal_analysis=False` disables feature
- Existing code ignores `recovery_plan` key in result
- No behavioral changes to error handling logic
- Graceful degradation if analysis fails

## Recovery Strategy Selection Algorithm

```python
def _generate_recovery_actions(error, error_type, causal_analysis, context):
    """Generate candidates based on error characteristics."""
    
    actions = []
    root_lower = causal_analysis.root_cause.lower()
    
    # Classify root cause and suggest actions
    if "timeout" in error_type or "connection" in error_type:
        actions.extend([
            RETRY_WITH_BACKOFF {likelihood: 0.75, cost: 0.1, risk: 0.05},
            WAIT_FOR_DEPENDENCY {likelihood: 0.65, cost: 0.2, risk: 0.1}
        ])
    
    if any(x in root_lower for x in ["pool", "resource", "capacity"]):
        actions.extend([
            WAIT_FOR_DEPENDENCY {likelihood: 0.7, cost: 0.15, risk: 0.08},
            SCALE_RESOURCES {likelihood: 0.6, cost: 0.5, risk: 0.2}
        ])
    
    if any(x in root_lower for x in ["ordering", "dependency", "sequence"]):
        actions.extend([
            RESTRUCTURE_WORKFLOW {likelihood: 0.8, cost: 0.3, risk: 0.15},
            SKIP_STEP {likelihood: 0.5, cost: 0.1, risk: 0.3}
        ])
    
    if any(x in error_type for x in ["permission", "auth", "forbidden"]):
        actions.append(
            ESCALATE {likelihood: 0.4, cost: 0.0, risk: 0.0}
        )
    
    # Fallback if no matches
    if not actions:
        actions.extend([
            RETRY_IMMEDIATELY {likelihood: 0.4, ...},
            RETRY_WITH_EXPONENTIAL {likelihood: 0.55, ...},
            ESCALATE {likelihood: 0.5, ...}
        ])
    
    # Sort by score
    actions.sort(key=lambda a: a.score, reverse=True)
    
    # Return top 3
    return actions[:3]
```

## Test Coverage

### Unit Tests (test_causal_error_recovery.py)

1. **Timeout errors** → recommend retry_with_backoff
2. **Resource exhaustion** → recommend wait or scale
3. **Workflow design issues** → recommend restructure
4. **Permission errors** → recommend escalate
5. **Leaf vs downstream classification** → correct categorization
6. **Action scoring** → proper rank order
7. **Recording recovery attempts** → pattern learning
8. **Pattern detection** → known patterns recognized
9. **Confidence improvement** → success history boosts scores
10. **Pattern serialization** → round-trip to/from Redis

### Integration Tests

1. **Full pipeline** → error → causal analysis → recovery plan
2. **Feedback loop** → record success → improve confidence
3. **Pattern learning** → multiple occurrences → increased confidence

### Smoke Tests

1. **Serialization** → RecoveryPlan and FailurePattern to/from dict
2. **Redis operations** → pattern storage and retrieval

## Performance Characteristics

- **Causal analysis**: <200ms (async, non-blocking)
  - Leverages Think Tool (already async)
  - Graceful degradation if exceeds timeout
  
- **Pattern detection**: <50ms
  - Single Redis lookup (pattern hash)
  - No N+1 queries
  
- **Recovery recommendations**: <100ms
  - Linear scan of ~10 error type rules
  - O(n) scoring where n ≤ 10 actions
  
- **Pattern storage**: <100ms (async write)
  - Single Redis HSET for pattern metadata
  - Single Redis INCR for count

**Total overhead per error: <400ms** (mostly causal analysis)

## Graceful Degradation

1. **Causal analysis fails** → Log warning, continue with standard handling
2. **Pattern detection unavailable** → Treat as new pattern, confidence=0.7
3. **Recovery recommender fails** → Skip recovery_plan, use error_config only
4. **Redis unavailable** → Pattern storage skipped, pattern detection returns None
5. **Think Tool unavailable** → Log debug, skip causal analysis

**Result:** System always falls back to existing error_config behavior. Recovery recommendations are enhancement, not requirement.

## Future Enhancements

1. **Contextual recovery** → Consider step type, workflow context
2. **Cost model** → Weight resource cost by availability
3. **Temporal patterns** → Day-of-week effects on failures
4. **Cross-workflow learning** → Share patterns across workflows
5. **Recovery action validation** → Dry-run recovery before execution
6. **Auto-remediation** → Execute low-risk actions automatically
7. **Operator guidance** → UI hints based on recovery plan
8. **Analytics dashboard** → Visualization of failure patterns + resolutions

## References

- Issue #2154: Enhanced error handling with causal chain tracing
- CausalErrorAnalyzer (orchestration/causal_error_analyzer.py)
- CausalErrorRecovery (orchestration/causal_error_recovery.py)
- FailurePatternDetector (services/failure_pattern_detector.py)
- ThinkTool (agent_loop/think_tool.py)
