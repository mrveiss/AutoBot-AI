---
tags: [type/architecture, status/current, component/backend]
date: 2026-06-04
---

# Counterfactual Reasoning — Architecture

`CounterfactualReasoner` extends AutoBot's decision engine with "what if" simulation. Before committing to risky decisions (escalate, retry, automate), agents predict outcomes and understand side effects without executing.

**Module:** `context_aware_decision.counterfactual_reasoner`

---

## Key Innovation: Three-Tier Prediction Strategy

Gracefully degrades from best available evidence to heuristics:

```
1. Empirical  → Historical Redis data ("this action worked 87% last time")
2. Causal     → Knowledge graph inference ("retry fixes transient errors")
3. Heuristic  → Static rules ("escalation always has near-zero cost")
```

`prediction_source` in `InterventionOutcome` tells you which tier answered.

---

## Data Model

```python
@dataclass
class InterventionOutcome:
    option: str                          # "retry", "escalate", "automate", "wait"
    predicted_success_rate: float        # 0.0–1.0
    side_effects: List[Dict]             # Non-obvious consequences
    confidence: float                    # 0.0–1.0
    reasoning: str                       # Why this outcome is predicted
    prediction_source: str               # "empirical" | "causal" | "heuristic"
    supporting_evidence: List[Dict]      # Evidence citations
    fallback_risk: Optional[str]         # What breaks if this option fails
    estimated_latency_ms: Optional[int]  # Expected execution time
```

---

## Integration with Decision Engine

`CounterfactualReasoner` is one of three Tier 2 services consumed by `CausalInferenceEngine`:

| Service | Role |
|---|---|
| `RootCauseAnalyzer` (Tier 1) | Find the causal chain |
| `CounterfactualReasoner` (Tier 2) | Simulate intervention outcomes |
| `ConfounderControlAnalyzer` (Tier 2) | Identify multi-factor confounders |
| `CausalInferenceEngine` (Tier 3) | Synthesise all three into a `CausalReport` |

---

## Typical Usage

```python
from context_aware_decision.counterfactual_reasoner import CounterfactualReasoner

reasoner = CounterfactualReasoner()
outcomes = await reasoner.simulate_interventions(
    options=["retry", "escalate", "wait"],
    context={
        "error_type": "TimeoutError",
        "causal_chain": "Network congestion → High latency → Timeout",
        "task_id": "task-123",
    },
)

for outcome in sorted(outcomes, key=lambda o: o.predicted_success_rate, reverse=True):
    print(f"{outcome.option}: {outcome.predicted_success_rate:.0%} "
          f"(source: {outcome.prediction_source})")
```

---

## Redis Storage

Empirical data is stored per `(action, causal_chain_hash)` key:

```
counterfactual:outcomes:{action}:{chain_hash}:success_count
counterfactual:outcomes:{action}:{chain_hash}:total_count
counterfactual:outcomes:{action}:{chain_hash}:latency_ms
```

TTL: 30 days. Confidence increases as `total_count` grows toward a threshold.
