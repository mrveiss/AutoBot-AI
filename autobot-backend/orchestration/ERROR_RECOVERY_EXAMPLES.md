# Error Recovery Examples

Real-world scenarios showing causal analysis → recovery recommendations.

## Example 1: Network Timeout (Transient)

### Scenario
```python
# Workflow step: "fetch_data_from_api"
error = TimeoutError("Connection timed out after 30s")

# Step config: allow 3 retries
step = {
    "id": "fetch_data",
    "error_config": {
        "action": "retry",
        "max_retries": 3,
        "base_delay": 1.0,
        "backoff": "exponential"
    }
}
```

### Causal Analysis
```
CausalErrorAnalysis {
    error_description: "Connection timeout after 30s",
    root_cause: "Network congestion on ISP backbone",
    causal_chain: "Heavy traffic → ISP congestion → High latency → Timeout",
    confounders_identified: ["DNS resolution overhead"],
    confidence: 0.85,
    recommended_action: "Retry with exponential backoff"
}
```

### Recovery Plan
```json
{
  "error_id": "TimeoutError:12345",
  "error_type": "TimeoutError",
  "root_cause": "Network congestion on ISP backbone",
  "causal_chain": "Heavy traffic → ISP congestion → High latency → Timeout",
  "is_leaf_error": true,
  "is_known_pattern": false,
  "pattern_frequency": 0,
  "confidence": 0.85,
  "recommended_actions": [
    {
      "action": "retry_with_backoff",
      "description": "Retry with exponential backoff (transient network failure)",
      "likelihood_to_succeed": 0.75,
      "cost": 0.1,
      "risk": 0.05,
      "expected_outcome": "Connection re-established, request succeeds",
      "estimated_delay_seconds": 2.0,
      "score": 1.35
    },
    {
      "action": "wait_for_dependency",
      "description": "Wait for upstream service/resource to become available",
      "likelihood_to_succeed": 0.65,
      "cost": 0.2,
      "risk": 0.1,
      "expected_outcome": "Service comes online, retry succeeds",
      "estimated_delay_seconds": 5.0,
      "score": 1.0
    },
    {
      "action": "escalate",
      "description": "Escalate to human operator for manual intervention",
      "likelihood_to_succeed": 0.5,
      "cost": 0.0,
      "risk": 0.0,
      "expected_outcome": "Operator investigates and resolves error",
      "estimated_delay_seconds": 0.0,
      "score": 1.0
    }
  ]
}
```

### Execution
```python
# Caller gets result:
outcome = await error_handler.handle_error(step, error, attempt=1, context)

# Standard handling: RETRY after 1s
outcome = {
    "action": "retry",
    "delay": 1.0,
    "fallback_id": None,
    "reason": "retry 2/3 after 1.0s",
    "recovery_plan": {...}  # NEW: recovery recommendations
}

# Caller sleeps 1s, then retries
await asyncio.sleep(outcome["delay"])
# Request succeeds on retry
```

### Feedback
```python
# Record success for pattern learning
await recovery_recommender.record_recovery_attempt(
    recovery_plan=plan,
    action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
    success=True,
    outcome="Connection re-established after 1s delay"
)

# Next timeout with same causal chain:
# - is_known_pattern: True
# - pattern_frequency: 2
# - confidence: 0.90 (boosted)
```

---

## Example 2: Connection Pool Exhaustion (Resource Contention)

### Scenario
```python
# Workflow: "parallel_api_calls" running 100 concurrent steps
error = RuntimeError("Connection pool exhausted - no available connections")

# Pool size: 20 connections
# Concurrent requests: 100
# Contention visible in execution history
```

### Causal Analysis
```
CausalErrorAnalysis {
    error_description: "Connection pool exhausted",
    root_cause: "Insufficient connection pool capacity",
    causal_chain: "Parallel requests (100) → Pool limit (20) → Exhaustion → No connections",
    confounders_identified: ["Long-lived connections holding resources"],
    confidence: 0.90,
    recommended_action: "Wait for connections to release or scale resources"
}
```

### Recovery Plan
```json
{
  "error_type": "RuntimeError",
  "root_cause": "Insufficient connection pool capacity",
  "causal_chain": "Parallel requests (100) → Pool limit (20) → Exhaustion",
  "is_leaf_error": false,
  "is_known_pattern": false,
  "confidence": 0.88,
  "recommended_actions": [
    {
      "action": "wait_for_dependency",
      "description": "Wait for resource to become available (pool recovery)",
      "likelihood_to_succeed": 0.7,
      "cost": 0.15,
      "risk": 0.08,
      "expected_outcome": "Other operations release resources, retry succeeds",
      "estimated_delay_seconds": 3.0,
      "score": 1.27
    },
    {
      "action": "scale_resources",
      "description": "Scale up resources (connection pool, memory, etc.)",
      "likelihood_to_succeed": 0.6,
      "cost": 0.5,
      "risk": 0.2,
      "expected_outcome": "More resources available, step succeeds",
      "estimated_delay_seconds": 10.0,
      "score": 0.6
    },
    {
      "action": "retry_immediately",
      "description": "Retry immediately (transient error)",
      "likelihood_to_succeed": 0.4,
      "cost": 0.05,
      "risk": 0.1,
      "expected_outcome": "Error condition resolved, retry succeeds",
      "estimated_delay_seconds": 0.0,
      "score": 0.65
    }
  ]
}
```

### Execution
```python
# Decision: Implement circuit breaker + wait
if recommendation.action == "wait_for_dependency":
    # Set circuit breaker
    breaker.open()
    
    # Wait for resources to clear
    await asyncio.sleep(3.0)
    
    # Try again
    breaker.half_open()
    try:
        result = await step_executor.execute(step)
        breaker.close()  # Success
    except:
        breaker.open()   # Try again later
        raise
```

---

## Example 3: Missing Dependency (Workflow Design)

### Scenario
```python
# Workflow step "process_data" depends on output from "fetch_data"
# But "fetch_data" hasn't completed yet (ordering issue)

error = KeyError("Key 'data' not found in context")

# Execution history shows:
# - "fetch_data" was skipped due to earlier error
# - "process_data" tries to use non-existent output
```

### Causal Analysis
```
CausalErrorAnalysis {
    error_description: "Key 'data' not found in context",
    root_cause: "Upstream step did not run, expected output missing",
    causal_chain: "Upstream error → Step skipped → Output missing → KeyError",
    confounders_identified: ["No input validation in step"],
    confidence: 0.92,
    recommended_action: "Restructure workflow to enforce dependencies"
}
```

### Recovery Plan
```json
{
  "error_type": "KeyError",
  "root_cause": "Upstream step did not run, expected output missing",
  "causal_chain": "Upstream error → Step skipped → Output missing",
  "is_leaf_error": false,
  "is_known_pattern": false,
  "confidence": 0.85,
  "recommended_actions": [
    {
      "action": "restructure_workflow",
      "description": "Restructure workflow steps (fix ordering/dependencies)",
      "likelihood_to_succeed": 0.8,
      "cost": 0.3,
      "risk": 0.15,
      "expected_outcome": "Step runs with correct dependencies met",
      "estimated_delay_seconds": 0.0,
      "score": 1.35
    },
    {
      "action": "skip_step",
      "description": "Skip problematic step if optional",
      "likelihood_to_succeed": 0.5,
      "cost": 0.1,
      "risk": 0.3,
      "expected_outcome": "Workflow continues without this step",
      "estimated_delay_seconds": 0.0,
      "score": 0.7
    },
    {
      "action": "escalate",
      "description": "Escalate to human operator for manual intervention",
      "likelihood_to_succeed": 0.9,
      "cost": 0.0,
      "risk": 0.0,
      "expected_outcome": "Operator fixes dependency, resumes workflow",
      "estimated_delay_seconds": 0.0,
      "score": 1.8
    }
  ]
}
```

### Action
```python
# Restructure: Add explicit dependency declaration
workflow = {
    "steps": [
        {
            "id": "fetch_data",
            "type": "api_call",
            "error_config": {"action": "retry", "max_retries": 3}
        },
        {
            "id": "process_data",
            "type": "transform",
            "depends_on": ["fetch_data"],  # NEW: explicit dependency
            "error_config": {"action": "skip"}  # Skip if dependency failed
        }
    ]
}

# Result: DAG executor enforces ordering, error doesn't occur
```

---

## Example 4: Permission Denied (Unrecoverable)

### Scenario
```python
# Workflow step attempts to write to restricted directory
error = PermissionError("Permission denied: /etc/passwd")

# Error is not transient or resource-related
# Requires manual intervention
```

### Causal Analysis
```
CausalErrorAnalysis {
    error_description: "Permission denied: /etc/passwd",
    root_cause: "Insufficient permissions for user 'autobot'",
    causal_chain: "User lacks write permission → Access denied",
    confounders_identified: [],
    confidence: 0.98,
    recommended_action: "Escalate to operator"
}
```

### Recovery Plan
```json
{
  "error_type": "PermissionError",
  "root_cause": "Insufficient permissions for user 'autobot'",
  "causal_chain": "User lacks write permission",
  "is_leaf_error": true,
  "is_known_pattern": false,
  "confidence": 0.95,
  "recommended_actions": [
    {
      "action": "escalate",
      "description": "Escalate to operator (permission denied)",
      "likelihood_to_succeed": 0.8,
      "cost": 0.0,
      "risk": 0.0,
      "expected_outcome": "Operator grants permission or changes target, workflow resumed",
      "estimated_delay_seconds": 0.0,
      "score": 1.6
    }
  ]
}
```

### Execution
```python
# No automatic retry - escalate immediately
if "permission" in error_type.lower():
    await escalate_to_operator(
        step=step,
        error=error,
        recovery_plan=plan,
        reason="Permission denied - requires operator approval"
    )
```

---

## Pattern Learning Over Time

### First Occurrence
```
Timeout error → TimeoutError:12345
├─ is_known_pattern: False
├─ confidence: 0.85
└─ recommended_actions: [retry_with_backoff (score 1.35), wait (...), escalate (...)]

Record: RETRY_WITH_BACKOFF → SUCCESS
Pattern stored: count=1, success_rate=100%
```

### Second Occurrence (same causal chain)
```
Timeout error → TimeoutError:12345  
├─ is_known_pattern: True ← DETECTED!
├─ pattern_frequency: 2
├─ confidence: 0.88 ← BOOSTED
└─ recommended_actions: [retry_with_backoff (unchanged), ...]

Record: RETRY_WITH_BACKOFF → SUCCESS
Pattern updated: count=2, success_rate=100%, confidence=0.95
```

### Third Occurrence
```
Timeout error → TimeoutError:12345
├─ is_known_pattern: True
├─ pattern_frequency: 3
├─ confidence: 1.0 ← VERY HIGH
└─ recommended_actions: [retry_with_backoff, ...] ← PROVEN ACTION

Record: RETRY_WITH_BACKOFF → SUCCESS
Pattern: count=3, success_rate=100%, confidence=1.0
```

### Tenth Occurrence
```
Timeout error → TimeoutError:12345
├─ is_known_pattern: True ← WELL-KNOWN PATTERN
├─ pattern_frequency: 10
├─ confidence: 1.0 ← MAXIMUM CONFIDENCE
├─ resolution_success_rate: 0.95 ← 95% SUCCEED WITH RETRY
└─ recommended_actions: [retry_with_backoff, ...] ← PROVEN EFFECTIVE

Operator dashboard shows:
- "Timeout pattern (10 occurrences): 95% resolved by retry"
- "Typical resolution time: 2-3s"
- "Estimated cost: minimal"
```

---

## Multi-Strategy Example: Resource Pool Exhaustion

### Timeline
```
Time  Event                         Action              Outcome
────────────────────────────────────────────────────────────────
 0s   100 concurrent requests       Start              Pool depleted
 0s   Pool exhausted                Try action 1       (wait)
 3s   3 connections released        Retry request      Still exhausted
 3s   Still exhausted               Try action 2       (wait longer)
 8s   10 more released              Retry request      SUCCESS!

Total recovery time: 8 seconds
```

### Recovery Strategy Execution
```python
recovery_plan = {
    "recommended_actions": [
        {action: "wait_for_dependency", delay: 3s, likelihood: 0.7},
        {action: "scale_resources", delay: 10s, likelihood: 0.6},
        {action: "retry_immediately", delay: 0s, likelihood: 0.4}
    ]
}

# Executor picks top action
action = recovery_plan.recommended_actions[0]  # wait_for_dependency

# Wait
await asyncio.sleep(action.estimated_delay_seconds)  # 3s

# Retry
try:
    result = await executor.execute(step)
    # Record success
    await recorder.record(plan, action, success=True, outcome="Recovered")
except:
    # Still failing - try next action
    action2 = recovery_plan.recommended_actions[1]  # scale_resources
    # Escalate or try next strategy
```

---

## Feedback Loop: Improving Over Time

### Week 1
```
Pattern: Timeout after heavy traffic
├─ Occurrences: 12
├─ Retry success rate: 85%
├─ Pattern frequency: 12
├─ Confidence: 0.92
└─ Most effective action: RETRY_WITH_BACKOFF
```

### Week 2
```
Pattern: Timeout after heavy traffic
├─ Occurrences: 18 (+6)
├─ Retry success rate: 89% (+4%)
├─ Pattern frequency: 18
├─ Confidence: 0.94 (+0.02)
└─ Most effective action: RETRY_WITH_BACKOFF (confirmed)
```

### Week 3
```
Pattern: Timeout after heavy traffic
├─ Occurrences: 25 (+7)
├─ Retry success rate: 92% (+3%)
├─ Pattern frequency: 25
├─ Confidence: 0.96 (+0.02)
├─ Most effective action: RETRY_WITH_BACKOFF (96% success)
└─ Alternative: WAIT_FOR_DEPENDENCY (4% success, fallback)
```

### Dashboard Display
```
Top 5 Failure Patterns

1. Timeout (heavy traffic)         25 occurrences  92% resolved
   └─ Best action: retry_with_backoff (avg 2s)
   
2. Connection pool exhausted        18 occurrences  78% resolved  
   └─ Best action: wait_for_dependency (avg 5s)
   
3. Missing dependency (workflow)     12 occurrences  100% resolved
   └─ Best action: restructure_workflow
   
4. Permission denied                  8 occurrences  87.5% resolved
   └─ Best action: escalate (avg 45min)
   
5. DNS resolution timeout             6 occurrences  50% resolved
   └─ Best action: retry_with_backoff
```

---

## Performance Characteristics

### Overhead per Error
```
StepErrorHandler.handle_error()
├─ Parse config: 0.1ms
├─ Causal analysis: 150-200ms
│  └─ Think Tool invocation
├─ Recovery recommendation: 50-100ms
│  └─ Error classification + action generation
├─ Pattern detection: 20-50ms
│  └─ Redis lookup
└─ Total: ~250ms (99th percentile: 300ms)

With enable_causal_analysis=False: ~1ms (no analysis)
```

### Redis Operations
```
Per error (if success recorded):
├─ Pattern lookup: 1 GET
├─ Pattern update: 1 SET
├─ Count increment: 1 INCR
├─ Resolution record: 1 HSET
└─ TTL refresh: 3 EXPIRE calls

Total: 7 Redis operations per error
Each operation: <1ms on local Redis
Total overhead: <20ms
```

---

## Summary

The Causal Error Recovery System provides:

1. **Root-cause understanding** via Think Tool integration
2. **Smart action selection** based on error classification
3. **Pattern learning** that improves recommendations over time
4. **Multi-strategy recommendations** ranked by effectiveness
5. **Confidence scoring** for trustworthy recommendations
6. **Graceful degradation** when analysis unavailable
7. **Zero breaking changes** to existing error handling
8. **Observable patterns** for ops dashboard integration

All while maintaining backward compatibility and minimal performance overhead.
