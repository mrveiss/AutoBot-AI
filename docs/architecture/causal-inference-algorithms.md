---
tags: [type/architecture, status/current, component/backend]
date: 2026-06-04
issue: 4069
---

# Causal Inference Algorithms

Reference for the scoring and ranking algorithms used by `CausalInferenceEngine` (`autobot-backend/services/causal_inference_engine.py`).

---

## Confidence Score

Composite score combining four factors. Range: 0.0–1.0.

```
confidence = clamp(0, depth_score + event_score + intervention_score + confounder_penalty, 1)
```

| Component | Weight | Formula |
|---|---|---|
| Chain depth | max 0.4 | `(depth / 5) × 0.4` |
| Event quality | max 0.3 | `avg(event.confidence) × 0.3` |
| Intervention clarity | max 0.2 | `avg(top_3_interventions.confidence) × 0.2` |
| Confounder penalty | max −0.2 | `−confounding_strength × 0.2` |

**Examples:**

| Scenario | depth | events | interventions | confounders | confidence |
|---|---|---|---|---|---|
| Pool exhaustion | 4 | 0.925 avg | 0.89 avg | strength=0.35 | **0.71** |
| Memory leak | 3 | 0.94 avg | 0.89 avg | none | **0.70** |
| Sparse data | 1 | 0.70 avg | none | none | **0.29** |

---

## Severity Assessment

```python
def assess_severity(report, confounding_strength, interventions):
    # Base from confidence + depth
    if report.chain_depth >= 3 and report.confidence >= 0.7:
        severity = CRITICAL
    elif report.chain_depth >= 2 and report.confidence >= 0.5:
        severity = DEGRADED
    else:
        severity = WARNING

    # Upgrade: multi-factor failure
    if confounding_strength >= 0.5 and severity == DEGRADED:
        severity = CRITICAL

    # Downgrade: high-confidence fix exists
    if (interventions
            and interventions[0].predicted_success_rate >= 0.8
            and interventions[0].confidence >= 0.8):
        if severity == CRITICAL:
            severity = DEGRADED

    return severity
```

| depth | confidence | confounding | result |
|---|---|---|---|
| 1 | 0.3 | 0.0 | WARNING |
| 2 | 0.5 | 0.2 | DEGRADED |
| 3 | 0.7 | 0.0 | CRITICAL |
| 2 | 0.6 | 0.5 | CRITICAL (upgraded) |
| 3 | 0.8 | 0.0 | DEGRADED* |
| 4 | 0.85 | 0.6 | CRITICAL |

\* Downgraded when a fix has ≥80% success rate and ≥80% confidence.

---

## Intervention Ranking

```
impact_score = success_rate × cost_multiplier × risk_multiplier
```

| Cost | Multiplier | Meaning |
|---|---|---|
| low | 1.0 | Quick, reversible (config tweak, timeout increase) |
| medium | 0.7 | Days to implement (pool size, add index) |
| high | 0.4 | Weeks to implement (refactor, redesign) |

| Risk | Multiplier | Meaning |
|---|---|---|
| low | 1.0 | No adverse effects |
| medium | 0.8 | Potential side effects |
| high | 0.5 | Requires careful rollout |

Interventions sorted descending by `impact_score`; top 3 returned.

---

## Confounder Strength

```
confounding_strength = clamp(0, 1,
    (num_confounders / 3.0) × 0.8
    + avg_confounder_confidence × 0.2
)
```

| Scenario | strength |
|---|---|
| No confounders | 0.0 |
| 1 confounder (confidence 0.8) | 0.27 |
| 2 confounders (confidence 0.9) | 0.71 |
| 3+ confounders (confidence 0.8) | 0.96 |

Cap at 3 confounders — beyond that, additional factors don't meaningfully increase complexity.

---

## Recommendation Text

```python
# Urgency prefix applied to first recommendation only
urgency = "[URGENT] " if CRITICAL else "[ACTION] " if DEGRADED else ""

for intervention in sorted_by_type([IMMEDIATE, SHORT_TERM, LONG_TERM]):
    if intervention.confidence >= 0.4:
        text = f"{urgency}{intervention.type}: {intervention.name} ({intervention.success_rate:.0%} success). Reason: {intervention.mechanism}"
        urgency = ""  # Only first gets the prefix
```

---

## Summary

| Algorithm | Output | Purpose |
|---|---|---|
| Confidence | 0.0–1.0 | Overall analysis quality |
| Severity | CRITICAL / DEGRADED / WARNING | Urgency level |
| Intervention ranking | Sorted list | Priority order |
| Confounder strength | 0.0–1.0 | Multi-factor contribution |
| Recommendation text | Human-readable | User action items |

All algorithms are deterministic. Thresholds (`MAX_CHAIN_DEPTH=5`, `MIN_CONFIDENCE=0.4`) are module-level constants in `causal_inference_engine.py`.
