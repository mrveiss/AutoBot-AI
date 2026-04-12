# Causal Error Recovery API Reference

## Public API Surface

### CausalErrorRecovery

**Module:** `orchestration.causal_error_recovery`

**Singleton:** `get_recovery_recommender() -> CausalErrorRecovery`

#### Methods

##### `async recommend_recovery(error, causal_analysis, execution_context) -> RecoveryPlan`

Generate recovery recommendations based on error analysis.

**Parameters:**
- `error: Exception` - The exception that occurred
- `causal_analysis: CausalErrorAnalysis` - Results from CausalErrorAnalyzer
- `execution_context: Dict[str, Any]` - Step/workflow context

**Returns:** `RecoveryPlan` with top 3 recovery actions ranked by score

**Example:**
```python
from orchestration.causal_error_recovery import get_recovery_recommender
from orchestration.causal_error_analyzer import analyze_error_causally

error = TimeoutError("Connection timeout")
causal = await analyze_error_causally(error, "step_1", "workflow_1")

recommender = get_recovery_recommender()
plan = await recommender.recommend_recovery(
    error=error,
    causal_analysis=causal,
    execution_context={"step_id": "step_1", "workflow_id": "workflow_1"}
)

# Use plan.recommended_actions[0] for best action
print(f"Root cause: {plan.root_cause}")
print(f"Confidence: {plan.confidence:.2%}")
print(f"Top action: {plan.recommended_actions[0].action.value}")
```

##### `async record_recovery_attempt(recovery_plan, action_taken, success, outcome=None) -> None`

Record the outcome of a recovery attempt for pattern learning.

**Parameters:**
- `recovery_plan: RecoveryPlan` - The plan that was executed
- `action_taken: RecoveryAction` - The action that was attempted
- `success: bool` - Whether the action succeeded
- `outcome: Optional[str]` - Description of outcome

**Example:**
```python
# After executing recommended action
if request_succeeded:
    await recommender.record_recovery_attempt(
        recovery_plan=plan,
        action_taken=RecoveryAction.RETRY_WITH_BACKOFF,
        success=True,
        outcome="Connection re-established"
    )
```

---

### FailurePatternDetector

**Module:** `services.failure_pattern_detector`

**Singleton:** `get_pattern_detector() -> FailurePatternDetector`

#### Methods

##### `async detect_pattern(causal_chain, error_type) -> Optional[FailurePattern]`

Check if a causal chain matches a known failure pattern.

**Parameters:**
- `causal_chain: str` - Causal chain from error analysis (e.g., "A → B → C")
- `error_type: str` - Exception type name

**Returns:** `FailurePattern` if pattern exists, None otherwise

**Example:**
```python
from services.failure_pattern_detector import get_pattern_detector

detector = get_pattern_detector()
pattern = await detector.detect_pattern(
    causal_chain="Network congestion → Timeout",
    error_type="TimeoutError"
)

if pattern:
    print(f"Known pattern, seen {pattern.occurrence_count} times")
    print(f"Success rate: {pattern.resolution_success_rate:.1%}")
    print(f"Confidence: {pattern.confidence:.2%}")
else:
    print("New pattern, no history")
```

##### `async learn_pattern(causal_chain, error_type, successful_action=None) -> FailurePattern`

Learn or update a failure pattern from experience.

**Parameters:**
- `causal_chain: str` - Causal chain
- `error_type: str` - Exception type
- `successful_action: Optional[str]` - If provided, marks this resolution as successful

**Returns:** Updated `FailurePattern`

**Example:**
```python
# Record a successful resolution
pattern = await detector.learn_pattern(
    causal_chain="Network congestion → Timeout",
    error_type="TimeoutError",
    successful_action="retry_with_backoff"
)

print(f"Pattern learned: {pattern.causal_chain}")
print(f"Success actions: {pattern.successful_resolutions}")
```

##### `async get_pattern_statistics() -> Dict[str, Any]`

Get aggregate statistics about all learned patterns.

**Returns:** Dictionary with keys:
- `total_patterns: int` - Number of unique patterns
- `total_occurrences: int` - Total error occurrences across patterns
- `average_success_rate: float` - Mean resolution success rate
- `high_confidence_patterns: int` - Count of patterns with confidence > 0.8

**Example:**
```python
stats = await detector.get_pattern_statistics()
print(f"Known failure patterns: {stats['total_patterns']}")
print(f"Avg success rate: {stats['average_success_rate']:.1%}")
```

##### `async list_known_patterns(limit=50) -> List[FailurePattern]`

List known patterns sorted by frequency (most common first).

**Parameters:**
- `limit: int` - Maximum patterns to return (default 50)

**Returns:** List of `FailurePattern` ordered by occurrence count

**Example:**
```python
patterns = await detector.list_known_patterns(limit=10)
for i, pattern in enumerate(patterns, 1):
    print(f"{i}. {pattern.causal_chain}: {pattern.occurrence_count} occurrences")
```

##### `async clear_patterns() -> None`

Clear all learned patterns (for testing or reset).

**Example:**
```python
# Reset pattern history
await detector.clear_patterns()
```

---

### StepErrorHandler (Enhanced)

**Module:** `orchestration.error_handler`

**Singleton:** `_error_handler` (internal, use via module functions if available)

#### Enhancements

The `StepErrorHandler` class now includes causal analysis capability:

```python
class StepErrorHandler:
    def __init__(self, enable_causal_analysis: bool = True):
        """Enable causal analysis for recovery recommendations."""
        self.enable_causal_analysis = enable_causal_analysis
```

#### Updated Method: `async handle_error(step, error, attempt, execution_context) -> Dict`

Returns dict with new optional field:

```python
{
    "action": StepErrorAction,           # Existing: RETRY, SKIP, FALLBACK, etc.
    "delay": float,                      # Existing: delay before retry
    "fallback_id": Optional[str],        # Existing: fallback step ID
    "reason": str,                       # Existing: explanation
    "recovery_plan": Optional[Dict]      # NEW: RecoveryPlan (if analysis enabled)
}
```

**Example:**
```python
from orchestration.error_handler import _error_handler

outcome = await _error_handler.handle_error(
    step={"id": "step_1", "error_config": {"action": "retry"}},
    error=TimeoutError("timeout"),
    attempt=1,
    execution_context={"workflow_id": "wf_1"}
)

if outcome.get("recovery_plan"):
    plan = outcome["recovery_plan"]
    print(f"Root cause: {plan['root_cause']}")
    print(f"Top action: {plan['recommended_actions'][0]['action']}")
```

---

## Data Classes

### RecoveryPlan

**Location:** `orchestration.causal_error_recovery`

```python
@dataclass
class RecoveryPlan:
    error_id: str                          # Unique identifier
    error_type: str                        # Exception type name
    root_cause: str                        # Root cause from analysis
    causal_chain: str                      # Visualization: "A → B → C"
    is_leaf_error: bool                    # Immediate vs cascading
    is_known_pattern: bool                 # Known pattern?
    pattern_frequency: int                 # Occurrences count
    recommended_actions: List[RecoveryAction_]  # Top 3 actions
    confidence: float                      # 0.0-1.0
    timestamp: str                         # ISO-8601 UTC
    
    def to_dict() -> Dict[str, Any]
    @classmethod
    def from_dict(data: Dict) -> RecoveryPlan
```

### RecoveryAction_ (Note: Underscore to avoid conflict with enum)

**Location:** `orchestration.causal_error_recovery`

```python
@dataclass
class RecoveryAction_:
    action: RecoveryAction                 # What to do
    description: str                       # Why this action
    likelihood_to_succeed: float           # 0.0-1.0
    cost: float                            # 0.0-1.0 (resource cost)
    risk: float                            # 0.0-1.0 (side effect risk)
    expected_outcome: str                  # What happens if successful
    estimated_delay_seconds: float         # How long it takes
    
    @property
    score() -> float                       # likelihood*2 - cost - risk
```

### RecoveryAction (Enum)

**Location:** `orchestration.causal_error_recovery`

```python
class RecoveryAction(str, Enum):
    RETRY_IMMEDIATELY = "retry_immediately"
    RETRY_WITH_BACKOFF = "retry_with_backoff"
    RETRY_WITH_EXPONENTIAL = "retry_with_exponential"
    WAIT_FOR_DEPENDENCY = "wait_for_dependency"
    RESTRUCTURE_WORKFLOW = "restructure_workflow"
    ESCALATE = "escalate"
    SKIP_STEP = "skip_step"
    FALLBACK_TO_ALTERNATIVE = "fallback_to_alternative"
    SCALE_RESOURCES = "scale_resources"
    CIRCUIT_BREAK = "circuit_break"
```

### FailurePattern

**Location:** `services.failure_pattern_detector`

```python
@dataclass
class FailurePattern:
    pattern_id: str                        # Hash of causal chain
    causal_chain: str                      # Causal chain pattern
    error_types: List[str]                 # Exception types seen
    occurrence_count: int                  # How many times
    successful_resolutions: List[str]      # Actions that worked
    resolution_success_rate: float         # 0.0-1.0
    confidence: float                      # 0.7-1.0 (improves over time)
    first_seen: str                        # ISO-8601 UTC
    last_seen: str                         # ISO-8601 UTC
    
    def to_dict() -> Dict[str, Any]
    @classmethod
    def from_dict(data: Dict) -> FailurePattern
```

---

## Redis Storage

### Key Patterns

```
failure:pattern:{pattern_hash}:{suffix}

Pattern hashes are MD5(causal_chain)[:16]

Suffixes:
  :count          → occurrence count (integer)
  :chain          → causal chain string
  :stats          → JSON with full pattern metadata
  :resolutions    → Hash of {action: result}

failure:patterns:known          → Set of all known pattern hashes
```

### Example Redis Keys

```
failure:pattern:eda1b2c3d4e5f6g7:count
failure:pattern:eda1b2c3d4e5f6g7:chain
failure:pattern:eda1b2c3d4e5f6g7:stats
failure:pattern:eda1b2c3d4e5f6g7:resolutions
failure:patterns:known  (Set)
```

### TTLs

- Pattern counts: 30 days
- Pattern chains: 30 days
- Pattern stats: 30 days
- Pattern resolutions: 30 days

---

## Integration Points

### 1. With StepErrorHandler

```python
# In error_handler.py
async def handle_error(step, error, attempt, execution_context):
    # ...existing logic...
    
    # NEW: Causal analysis
    if self.enable_causal_analysis:
        recovery_plan_dict = await self._analyze_and_recommend_recovery(...)
    
    # ...execute error_config action...
    
    # NEW: Include recovery plan in result
    result["recovery_plan"] = recovery_plan_dict
    return result
```

### 2. With WorkflowExecutor

```python
# In workflow executor
outcome = await error_handler.handle_error(step, error, attempt, context)

if outcome["action"] == StepErrorAction.RETRY:
    # Use outcome["recovery_plan"] for better diagnostics
    await asyncio.sleep(outcome["delay"])
    # Retry step
```

### 3. With Monitoring/Logging

```python
# In monitoring code
if outcome.get("recovery_plan"):
    plan = outcome["recovery_plan"]
    
    # Log for analysis
    logger.info(f"Error {plan['error_type']}: {plan['root_cause']}")
    logger.info(f"Confidence: {plan['confidence']:.1%}")
    logger.info(f"Top actions: {[a['action'] for a in plan['recommended_actions']]}")
    
    # Send to APM/tracing
    span.set_attribute("error.root_cause", plan["root_cause"])
    span.set_attribute("recovery.confidence", plan["confidence"])
```

---

## Configuration

### Enable/Disable Causal Analysis

```python
# Enable (default)
handler = StepErrorHandler(enable_causal_analysis=True)

# Disable (for backward compatibility or testing)
handler = StepErrorHandler(enable_causal_analysis=False)
```

### Think Tool Availability

The system gracefully degrades if Think Tool is unavailable:

```python
# If Think Tool fails:
# 1. CausalErrorAnalyzer logs warning
# 2. Returns None from _analyze_and_recommend_recovery()
# 3. Continues with standard error_config handling
# 4. No crash, no broken workflow
```

### Redis Availability

If Redis is unavailable:

```python
# Pattern detection returns None
# Pattern storage is skipped
# Recovery recommendations continue (base heuristics)
# Graceful degradation maintained
```

---

## Error Handling

### Exceptions Never Raised

The system is designed to never raise exceptions to callers:

```python
try:
    recovery_plan = await recommender.recommend_recovery(...)
except Exception:
    # Should never happen - all exceptions logged internally
    recovery_plan = None
```

All errors are:
- Logged at DEBUG or WARNING level
- Caught and handled internally
- Never propagated to workflow executor

### Logging Levels

```python
# DEBUG: Detailed analysis steps
logger.debug("Causal analysis complete: step=%s, confidence=%.2f", ...)

# INFO: Pattern detection success
logger.info("Found known pattern: hash=%s, count=%d", ...)

# WARNING: Analysis failed, graceful degradation
logger.warning("Causal analysis failed, continuing with standard handling: %s", ...)

# ERROR: Only if workflow state is corrupted (shouldn't happen)
```

---

## Testing

### Unit Tests

```python
# Run all tests
pytest test_causal_error_recovery.py -v

# Run specific test class
pytest test_causal_error_recovery.py::TestCausalErrorRecovery -v

# Run with coverage
pytest test_causal_error_recovery.py --cov=orchestration.causal_error_recovery
```

### Test Classes

- `TestCausalErrorRecovery` - Recovery action generation
- `TestFailurePatternDetector` - Pattern learning
- `TestCausalErrorRecoveryIntegration` - Full pipeline
- `TestRecoverySystemSmoke` - Serialization

---

## Performance Characteristics

### Latency (per error)

- Causal analysis: 150-200ms (async, non-blocking)
- Pattern detection: 20-50ms (single Redis lookup)
- Total overhead: ~250ms (300ms 99th percentile)
- With analysis disabled: ~1ms

### Memory

- Per pattern: ~500 bytes (causal chain + metadata)
- Estimated: 1MB for 2000 patterns
- 30-day TTL prevents unbounded growth

### Concurrency

- Thread-safe (Redis-backed)
- Async-compatible (all I/O non-blocking)
- No locks, no blocking operations

---

## Future Enhancements

See `CAUSAL_ERROR_RECOVERY_DESIGN.md` for planned additions:

1. Contextual recovery (step type, workflow context)
2. Temporal patterns (time-of-day effects)
3. Cross-workflow learning (global patterns)
4. Auto-remediation (low-risk actions executed automatically)
5. Cost model (weight resource cost)
6. Operator guidance (UI hints)
7. Analytics dashboard (visualization)

---

## Troubleshooting

### Issue: Recovery plan is None

**Cause:** Causal analysis failed or disabled

**Solution:** Check logs for:
```
"Causal analysis failed (continuing with standard handling)"
```

Check `enable_causal_analysis` flag is True.

### Issue: Pattern never detected

**Cause:** Causal chains don't match exactly

**Solution:**
- Patterns use MD5 hash of exact chain string
- "A → B → C" differs from "A→B→C" (whitespace)
- Use `detector.list_known_patterns()` to see actual chains

### Issue: Confidence not increasing

**Cause:** Actions not being recorded as successful

**Solution:**
```python
# Ensure recovery attempt is recorded
await recommender.record_recovery_attempt(
    plan, action, success=True
)
```

### Issue: High pattern count in Redis

**Cause:** Many unique error causal chains

**Solution:**
- 30-day TTL automatically expires old patterns
- Use `detector.get_pattern_statistics()` to monitor
- Consider `detector.clear_patterns()` for testing

---

## References

- Issue #2154: Enhanced error handling with causal chain tracing
- `CAUSAL_ERROR_RECOVERY_DESIGN.md` - Architecture & design
- `ERROR_RECOVERY_EXAMPLES.md` - Real-world examples
- `test_causal_error_recovery.py` - Comprehensive test suite
