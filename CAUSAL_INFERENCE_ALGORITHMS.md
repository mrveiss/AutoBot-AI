# CausalInferenceEngine - Core Algorithms

## 1. Confidence Scoring Algorithm

Confidence is a composite score combining four factors: chain depth, event quality, intervention clarity, and confounder penalty.

### Formula

```
confidence = min(1.0, max(0.0, depth_score + event_score + intervention_score + confounder_penalty))
```

### Components

#### Depth Score (max 0.4)
```python
depth_score = (chain_depth / MAX_CHAIN_DEPTH) × 0.4
            = (chain_depth / 5) × 0.4

Examples:
- depth=1: (1/5) × 0.4 = 0.08
- depth=3: (3/5) × 0.4 = 0.24
- depth=5: (5/5) × 0.4 = 0.40
```

**Rationale:** Deeper chains provide more evidence of the causal path. Maximum depth is 5 because beyond 5 events, we're likely reaching the limits of observable causality. Capped at 0.4 because chain depth alone is insufficient for confidence.

#### Event Quality Score (max 0.3)
```python
event_scores = [e.confidence for e in causal_chain]
event_score = (sum(event_scores) / len(event_scores)) × 0.3
            = avg(confidence_of_all_events) × 0.3

Examples:
- All events confidence 0.9: (0.9) × 0.3 = 0.27
- Events confidence [0.9, 0.8, 0.7]: (0.8) × 0.3 = 0.24
- Events confidence [0.5, 0.6, 0.4]: (0.5) × 0.3 = 0.15
```

**Rationale:** Events in the chain have individual confidence scores based on how certain we are about that specific event. Average these and weight at 0.3 to reflect that individual event quality is important but secondary to chain depth.

#### Intervention Clarity Score (max 0.2)
```python
top_3_interventions = interventions[:3]  # Best 3 by impact
avg_intervention_confidence = sum(i.confidence for i in top_3_interventions) / len(top_3_interventions)
intervention_score = avg_intervention_confidence × 0.2

Examples:
- Top 3 intervention confidence [0.95, 0.90, 0.85]: (0.90) × 0.2 = 0.18
- Top 3 intervention confidence [0.70, 0.60, 0.50]: (0.60) × 0.2 = 0.12
- No interventions: 0.0
```

**Rationale:** Clear, high-confidence interventions suggest the analysis is sound. When we can identify confident fixes, we're more confident in the root cause analysis. Only look at top 3 to avoid over-weighting marginal interventions.

#### Confounder Penalty (max -0.2)
```python
confounder_penalty = -confounding_strength × 0.2

confounding_strength = min(1.0, 
    (num_confounders / 3.0) × 0.8 +           # Multi-factor contribution
    (avg_confounder_confidence) × 0.2          # Confounder quality
)

Examples:
- No confounders: 0 × 0.2 = 0.0
- 1 confounder (confidence 0.8): (0.333 × 0.8 + 0.8 × 0.2) × 0.2 = 0.068
- 3 confounders (confidence 0.8): (1.0 × 0.8 + 0.8 × 0.2) × 0.2 = 0.192
  → penalty = -0.192 × 0.2 = -0.038

Full example:
- confounding_strength = 0.5 → penalty = -0.5 × 0.2 = -0.1
```

**Rationale:** Confounders introduce uncertainty. Multiple independent causes make it harder to pinpoint the true root cause. The penalty scales with confounding strength to reflect this uncertainty.

### Confidence Score Examples

#### Example 1: High Confidence (Pool Exhaustion)
```
chain_depth = 4 events
event_confidences = [0.95, 0.98, 0.92, 0.85] → avg = 0.925
interventions = [0.90, 0.92, 0.85]
confounders = 1 (confidence 0.9) → strength = 0.35

Calculation:
  depth_score = (4/5) × 0.4 = 0.32
  event_score = 0.925 × 0.3 = 0.278
  intervention_score = 0.89 × 0.2 = 0.178
  confounder_penalty = -0.35 × 0.2 = -0.07

Total = 0.32 + 0.278 + 0.178 - 0.07 = 0.706
Result: confidence = 0.71 (HIGH CONFIDENCE)
```

#### Example 2: Medium Confidence (Memory Leak)
```
chain_depth = 3 events
event_confidences = [0.99, 0.98, 0.85] → avg = 0.94
interventions = [0.95, 0.92, 0.80]
confounders = 0 → strength = 0.0

Calculation:
  depth_score = (3/5) × 0.4 = 0.24
  event_score = 0.94 × 0.3 = 0.282
  intervention_score = 0.89 × 0.2 = 0.178
  confounder_penalty = -0.0 × 0.2 = 0.0

Total = 0.24 + 0.282 + 0.178 = 0.70
Result: confidence = 0.70 (MEDIUM-HIGH CONFIDENCE)
```

#### Example 3: Low Confidence (Sparse Data)
```
chain_depth = 1 event
event_confidences = [0.70] → avg = 0.70
interventions = [] (none found)
confounders = 0 → strength = 0.0

Calculation:
  depth_score = (1/5) × 0.4 = 0.08
  event_score = 0.70 × 0.3 = 0.21
  intervention_score = 0.0 × 0.2 = 0.0
  confounder_penalty = -0.0 × 0.2 = 0.0

Total = 0.08 + 0.21 = 0.29
Result: confidence = 0.29 (LOW CONFIDENCE)
```

---

## 2. Severity Assessment Algorithm

Severity determines urgency level: CRITICAL (immediate action), DEGRADED (action needed), WARNING (informational).

### Algorithm

```python
def assess_severity(report, confounding_strength, interventions):
    # Step 1: Base severity from confidence and depth
    if report.chain_depth >= 3 and report.confidence >= 0.7:
        base_severity = CRITICAL
    elif report.chain_depth >= 2 and report.confidence >= 0.5:
        base_severity = DEGRADED
    else:
        base_severity = WARNING
    
    # Step 2: Upgrade to CRITICAL if multi-factor
    if confounding_strength >= 0.5 and base_severity == DEGRADED:
        base_severity = CRITICAL
    
    # Step 3: Downgrade if high-confidence fix available
    if (interventions and 
        interventions[0].predicted_success_rate >= 0.8 and
        interventions[0].confidence >= 0.8):
        if base_severity == CRITICAL:
            base_severity = DEGRADED
    
    return base_severity
```

### Decision Table

| Chain Depth | Confidence | Confounding | Base | After Upgrade | Final |
|---|---|---|---|---|---|
| 1 | 0.3 | 0.0 | WARNING | WARNING | WARNING |
| 2 | 0.5 | 0.2 | DEGRADED | DEGRADED | DEGRADED |
| 3 | 0.7 | 0.0 | CRITICAL | — | CRITICAL |
| 2 | 0.6 | 0.5 | DEGRADED | CRITICAL | CRITICAL |
| 3 | 0.8 | 0.0 | CRITICAL | — | DEGRADED* |
| 4 | 0.85 | 0.6 | CRITICAL | CRITICAL | CRITICAL |

*Downgraded if high-confidence fix (success≥0.8, confidence≥0.8)

### Examples

#### Pool Exhaustion → CRITICAL
```
chain_depth = 4
confidence = 0.88
confounding_strength = 0.35
interventions[0] = (success_rate=0.85, confidence=0.90)

1. Base: depth=4≥3 AND confidence=0.88≥0.7 → CRITICAL
2. Upgrade: confounding=0.35 < 0.5 → no upgrade
3. Downgrade: success_rate=0.85≥0.8 but confounding>0 → no downgrade
Result: CRITICAL (cascading, needs immediate action)
```

#### Memory Leak → DEGRADED
```
chain_depth = 3
confidence = 0.92
confounding_strength = 0.0
interventions[0] = (success_rate=0.95, confidence=0.95)

1. Base: depth=3≥3 AND confidence=0.92≥0.7 → CRITICAL
2. Upgrade: confounding=0 < 0.5 → no upgrade
3. Downgrade: success_rate=0.95≥0.8 AND confidence=0.95≥0.8 → DEGRADED
Result: DEGRADED (clear fix available, reduce urgency)
```

#### Sparse Data → WARNING
```
chain_depth = 1
confidence = 0.35
confounding_strength = 0.0
interventions = []

1. Base: depth=1<3 → WARNING
2. Upgrade: confounding=0 < 0.5 → no upgrade
3. Downgrade: no interventions → no downgrade
Result: WARNING (insufficient data)
```

---

## 3. Intervention Ranking Algorithm

Interventions are ranked by impact: success likelihood × cost efficiency × risk tolerance.

### Impact Score Formula

```
impact_score = success_rate × cost_multiplier × risk_multiplier

Where:
  success_rate ∈ [0.0, 1.0]
  cost_multiplier ∈ {low: 1.0, medium: 0.7, high: 0.4}
  risk_multiplier ∈ {low: 1.0, medium: 0.8, high: 0.5}

Examples:
  (0.95, low, low) = 0.95 × 1.0 × 1.0 = 0.95  ← HIGHEST IMPACT
  (0.85, medium, low) = 0.85 × 0.7 × 1.0 = 0.595
  (0.90, high, low) = 0.90 × 0.4 × 1.0 = 0.36
  (0.70, low, high) = 0.70 × 1.0 × 0.5 = 0.35
  (0.50, high, high) = 0.50 × 0.4 × 0.5 = 0.1  ← LOWEST IMPACT
```

### Ranking Examples

#### Pool Exhaustion Interventions

```
Option A: Increase connection pool (low cost, low risk, 0.85 success)
  impact = 0.85 × 1.0 × 1.0 = 0.85
  recommendation = SHORT_TERM
  rank = 1

Option B: Optimize N+1 query (high cost, low risk, 0.95 success)
  impact = 0.95 × 0.4 × 1.0 = 0.38
  recommendation = LONG_TERM
  rank = 2

Option C: Implement query timeout (low cost, medium risk, 0.70 success)
  impact = 0.70 × 1.0 × 0.8 = 0.56
  recommendation = SHORT_TERM
  rank = 3

Ranking: A (0.85) > C (0.56) > B (0.38)
Strategy: Do A immediately (quick win), then B later (permanent fix)
```

#### Memory Leak Interventions

```
Option A: Increase RAM (medium cost, low risk, 0.95 success)
  impact = 0.95 × 0.7 × 1.0 = 0.665
  recommendation = SHORT_TERM
  rank = 1

Option B: Fix memory leak (high cost, low risk, 0.92 success)
  impact = 0.92 × 0.4 × 1.0 = 0.368
  recommendation = LONG_TERM
  rank = 2

Ranking: A (0.665) > B (0.368)
Strategy: Add RAM (buys time), then find/fix leak
```

### Cost Multiplier Rationale

| Cost | Multiplier | Rationale |
|------|-----------|-----------|
| Low | 1.0 | Quick, reversible, cheap (increase timeout, add config) |
| Medium | 0.7 | Days to implement, moderate investment (pool size, add index) |
| High | 0.4 | Weeks to implement, large effort (refactor code, redesign) |

Penalizing high-cost interventions ensures we recommend quick wins first, even if they're not permanent solutions.

### Risk Multiplier Rationale

| Risk | Multiplier | Rationale |
|-----|-----------|-----------|
| Low | 1.0 | Safe, no adverse effects (increase limit, add monitoring) |
| Medium | 0.8 | Potential side effects (query timeout, restart service) |
| High | 0.5 | Risky, requires careful rollout (major refactor, state change) |

Penalizing high-risk interventions ensures we recommend safer options when success rates are similar.

---

## 4. Confounder Strength Calculation

Confounders are independent causes that contribute to failure. Strength measures how much they matter.

### Formula

```
confounding_strength = min(1.0, 
    (num_confounders / 3.0) × 0.8 +        # Multi-factor component (max 0.8)
    avg_confounder_confidence × 0.2         # Quality component (max 0.2)
)
```

### Components

#### Multi-Factor Component (max 0.8)
```
(num_confounders / 3.0) × 0.8

Examples:
  0 confounders: (0/3) × 0.8 = 0.0
  1 confounder: (1/3) × 0.8 = 0.267
  2 confounders: (2/3) × 0.8 = 0.533
  3+ confounders: (1.0) × 0.8 = 0.8 (capped at 3)
```

**Rationale:** More independent causes increase confounding. Cap at 3 because beyond that, additional confounders don't meaningfully increase the complexity.

#### Quality Component (max 0.2)
```
avg_confounder_confidence × 0.2

Examples:
  Confounders [0.9, 0.8, 0.7]: (0.8) × 0.2 = 0.16
  Confounders [0.5, 0.4]: (0.45) × 0.2 = 0.09
```

**Rationale:** Uncertain confounders matter less. If we're not sure a confounder exists, it shouldn't increase confounding strength as much.

### Examples

#### Single Root Cause
```
Root cause: Database query N+1 pattern
Confounders: none

confounding_strength = (0/3) × 0.8 + 0 × 0.2 = 0.0
Interpretation: Single-factor failure, high clarity on root cause
```

#### Multi-Factor Failure
```
Root cause: Code change (max_retries=0)
Confounder 1: Network flakiness (confidence 0.88)
Confounder 2: Traffic spike (confidence 0.92)

confounding_strength = (2/3) × 0.8 + (0.90) × 0.2
                    = 0.533 + 0.18 = 0.713
Interpretation: Multi-factor failure, strong confounding (71%), reduces confidence
```

#### Weak Confounder
```
Root cause: Memory leak
Confounder: Possible load spike (confidence 0.4 — uncertain)

confounding_strength = (1/3) × 0.8 + (0.4) × 0.2
                    = 0.267 + 0.08 = 0.347
Interpretation: Likely multi-factor but uncertain, moderate confounding (35%)
```

---

## 5. Recommendation Generation Algorithm

Recommendations are human-readable action items grouped by urgency and type.

### Algorithm

```python
def generate_recommendations(interventions, severity):
    recommendations = []
    
    # Group by recommendation type
    immediate = [i for i in interventions if i.type == IMMEDIATE]
    short_term = [i for i in interventions if i.type == SHORT_TERM]
    long_term = [i for i in interventions if i.type == LONG_TERM]
    
    # Urgency prefix based on severity
    urgency = ""
    if severity == CRITICAL:
        urgency = "[URGENT] "
    elif severity == DEGRADED:
        urgency = "[ACTION] "
    
    # Generate recommendations in priority order
    for intervention_list in [immediate, short_term, long_term]:
        for intervention in intervention_list:
            if intervention.confidence >= MIN_CONFIDENCE (0.4):
                recommendation = (
                    f"{urgency}{intervention.type}: "
                    f"{intervention.name} "
                    f"({intervention.success_rate:.0%} success). "
                    f"Reason: {intervention.mechanism}"
                )
                recommendations.append(recommendation)
                urgency = ""  # Only urgency on first recommendation
    
    return recommendations
```

### Output Examples

#### Critical Pool Exhaustion
```
"[URGENT] SHORT-TERM: Increase connection pool size (85% success). 
Reason: More connections available reduces queueing"

"LONG-TERM: Optimize N+1 query pattern (95% success). 
Reason: Fewer queries per request, shorter hold time"
```

#### Degraded Memory Leak
```
"[ACTION] SHORT-TERM: Increase memory allocation (95% success). 
Reason: More available memory prevents allocation failures"

"LONG-TERM: Find and fix memory leak (92% success). 
Reason: Fix the source of the leak, memory stops accumulating"
```

#### Warning Sparse Data
```
"Enable detailed logging and profiling (80% likelihood improves diagnosis). 
Reason: Current data insufficient to identify root cause"

"Add defensive checks (60% likelihood prevents panic). 
Reason: May mitigate symptoms while investigating root cause"
```

---

## Summary

| Algorithm | Input | Output | Use |
|-----------|-------|--------|-----|
| Confidence | Chain, events, interventions, confounders | Score 0.0-1.0 | Overall quality of analysis |
| Severity | Confidence, depth, confounding, fixes | CRITICAL/DEGRADED/WARNING | Urgency level |
| Intervention Ranking | All interventions | Sorted by impact | Priority order |
| Confounder Strength | Confounding events | Score 0.0-1.0 | Multi-factor contribution |
| Recommendation | Top interventions, severity | Human-readable text | User action items |

All algorithms are deterministic, transparent, and tuned for production use cases.
