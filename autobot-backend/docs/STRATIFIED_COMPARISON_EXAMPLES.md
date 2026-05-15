# Stratified Agent Comparison Examples

This document provides practical examples of using the stratified comparison API to perform fair, confounder-controlled agent performance analysis.

## Overview

Stratified comparison answers the question: **Is Agent A really better than Agent B, or does it just appear better because it handled easier tasks?**

By partitioning execution history by confounder values (e.g., query complexity, knowledge base size), we can:
- Compare agents fairly within each condition
- Detect if apparent advantages are confounded by task characteristics
- Estimate the "true effect" after controlling for confounders
- Measure confidence in the comparison results

---

## Example 1: Comparing RAGAgent vs SemanticSearchAgent (Query Complexity Control)

**Scenario:** You have two search agents. RAGAgent has a 85% success rate overall, SemanticSearchAgent has 75%. But does RAGAgent actually perform better?

### API Request

```bash
curl -X GET "http://localhost:8001/api/analytics/agents/stratified-comparison" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_a": "rag_agent",
    "agent_b": "semantic_search_agent",
    "metric": "success_rate",
    "confounders": "query_complexity",
    "limit": 1000
  }'
```

### Response

```json
{
  "agent_a": "rag_agent",
  "agent_b": "semantic_search_agent",
  "metric": "success_rate",
  "confounders": ["query_complexity"],
  "overall_advantage": 0.1,
  "confounded_effect": true,
  "confounding_strength": 0.28,
  "true_effect": 0.04,
  "true_effect_confidence": 0.75,
  "interpretation": "RAGAgent shows 10% advantage over SemanticSearchAgent on success_rate. Confounding detected (strength: 0.28). Agent performance varies significantly across task conditions. After controlling for confounders, the true effect is 0.04.",
  "sample_coverage": 0.83,
  "strata": {
    "query_complexity:low": {
      "agent_a": {
        "stratum_value": "low",
        "task_count": 120,
        "success_count": 118,
        "metric_value": 98.33,
        "confidence": 0.94
      },
      "agent_b": {
        "stratum_value": "low",
        "task_count": 115,
        "success_count": 100,
        "metric_value": 86.96,
        "confidence": 0.93
      }
    },
    "query_complexity:medium": {
      "agent_a": {
        "stratum_value": "medium",
        "task_count": 85,
        "success_count": 72,
        "metric_value": 84.71,
        "confidence": 0.88
      },
      "agent_b": {
        "stratum_value": "medium",
        "task_count": 92,
        "success_count": 71,
        "metric_value": 77.17,
        "confidence": 0.89
      }
    },
    "query_complexity:high": {
      "agent_a": {
        "stratum_value": "high",
        "task_count": 45,
        "success_count": 31,
        "metric_value": 68.89,
        "confidence": 0.75
      },
      "agent_b": {
        "stratum_value": "high",
        "task_count": 48,
        "success_count": 38,
        "metric_value": 79.17,
        "confidence": 0.77
      }
    }
  }
}
```

### Interpretation

- **Overall advantage (10%):** RAGAgent looks 10% better in raw success rate
- **Confounding detected (strength 0.28):** Performance varies significantly by query complexity
  - Low complexity: RAGAgent 98.3% vs SemanticSearchAgent 87% (RAGAgent wins by 11.3%)
  - Medium complexity: RAGAgent 84.7% vs SemanticSearchAgent 77.2% (RAGAgent wins by 7.5%)
  - High complexity: RAGAgent 68.9% vs SemanticSearchAgent 79.2% (SemanticSearchAgent wins by 10.3%!)
- **True effect (4%):** After accounting for task complexity, RAGAgent is only truly ~4% better
- **High confidence (0.75):** We're fairly confident in this estimate due to good sample sizes in each stratum

**Conclusion:** RAGAgent is slightly better overall, but it excels at simple/medium tasks and actually *underperforms* on complex queries. The "confounding" here is that RAGAgent historically received more simple tasks, artificially inflating its apparent advantage.

---

## Example 2: Multiple Confounders (Query Complexity + Knowledge Base Size)

**Scenario:** Compare ChatAgent vs CodeAnalysisAgent on latency, controlling for both query complexity AND knowledge base size.

### API Request

```bash
curl -X GET "http://localhost:8001/api/analytics/agents/stratified-comparison" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "agent_a": "chat_agent",
    "agent_b": "code_analysis_agent",
    "metric": "avg_duration_ms",
    "confounders": "query_complexity,knowledge_base_size",
    "limit": 500
  }'
```

### Response Structure

The response includes strata like:
- `query_complexity:low`
- `query_complexity:medium`
- `query_complexity:high`
- `knowledge_base_size:small`
- `knowledge_base_size:medium`
- `knowledge_base_size:large`

Each stratum shows duration metrics for both agents, allowing you to see:
- Chat agent is faster on small queries
- Code analysis is faster on large/complex tasks
- How much faster/slower in absolute milliseconds per condition

---

## Example 3: Detecting Simpson's Paradox

**Scenario:** Agent A has 80% success rate, Agent B has 70%. But A is better at easy tasks AND hard tasks. What's going on?

This is **Simpson's Paradox**: Agent A is better in every stratum, but when aggregated, appears worse!

### Response Would Show

```json
{
  "overall_advantage": -0.05,
  "strata": {
    "complexity:low": {
      "agent_a": {"metric_value": 95},
      "agent_b": {"metric_value": 70}
    },
    "complexity:high": {
      "agent_a": {"metric_value": 60},
      "agent_b": {"metric_value": 40}
    }
  },
  "confounded_effect": true,
  "confounding_strength": 0.45,
  "true_effect": 0.25,
  "interpretation": "Agent A shows -5% disadvantage overall... After controlling for confounders, the true effect is 0.25. [Agent A is actually 25% better]"
}
```

**What happened:** Agent A got most of the hard tasks, dragging down its overall average even though it's superior at every difficulty level!

---

## Example 4: No Confounding (Genuine Performance Difference)

**Scenario:** Agent X is 12% better than Agent Y across all conditions.

### Response Would Show

```json
{
  "overall_advantage": 0.12,
  "confounded_effect": false,
  "confounding_strength": 0.05,
  "true_effect": 0.12,
  "true_effect_confidence": 0.95,
  "interpretation": "Agent X shows 12% advantage over Agent Y on success_rate... No significant confounding detected. Observed advantage is likely genuine."
}
```

**Key indicators:**
- `confounded_effect: false` ✓
- `confounding_strength < 0.15` ✓
- `true_effect ≈ overall_advantage` ✓
- High confidence (0.95) ✓

The advantage is *real*, not an artifact of task distribution.

---

## Supported Confounders

The system recognizes these built-in confounders. Include task metadata with these keys in `AgentTaskRecord.metadata`:

| Confounder | Key | Binning |
|---|---|---|
| Query Complexity | `query_complexity` (1-5) | low (≤1), medium (≤2), high (>2) |
| Knowledge Base Size | `knowledge_base_size` (KB count) | small (<5K), medium (<50K), large (≥50K) |
| Network Latency | `network_latency_ms` (ms) | low (<100), medium (<500), high (≥500) |
| System Load | `system_load` (0.0-1.0) | low (<0.3), medium (<0.7), high (≥0.7) |
| Task Priority | `task_priority` (1-3) | low (1), medium (2), high (3) |

### How to Add Metadata When Tracking Tasks

```python
from services.agent_analytics import get_agent_analytics

analytics = get_agent_analytics()

# Start tracking with metadata
record = await analytics.track_task_start(
    agent_id="rag_agent",
    agent_type="knowledge",
    task_id="task_123",
    task_name="search_query",
    metadata={
        "query_complexity": 2,           # medium
        "knowledge_base_size": 15000,     # medium
        "network_latency_ms": 250,        # medium
        "system_load": 0.45,              # medium
        "task_priority": 2,               # medium
    }
)

# Later, complete the task
await analytics.track_task_complete(
    task_id="task_123",
    status=TaskStatus.COMPLETED
)
```

---

## Interpretation Guide

### `overall_advantage`
- **Range:** -1.0 to 1.0
- **Positive:** Agent A is better
- **Negative:** Agent B is better
- **0:** Agents are equivalent

### `confounded_effect`
- **True:** Metric varies significantly across strata (confounding is active)
- **False:** Metric is consistent across strata (confounding is unlikely)

### `confounding_strength`
- **Range:** 0.0 to 1.0
- **0.0-0.15:** No meaningful confounding
- **0.15-0.4:** Moderate confounding (affects comparison)
- **>0.4:** Strong confounding (comparison unreliable without stratification)

### `true_effect`
- **The honest advantage** after removing confounding bias
- Compare to `overall_advantage` to see the confounding bias
- High confidence means this estimate is trustworthy

### `sample_coverage`
- **Range:** 0.0 to 1.0
- **>0.8:** Good coverage (most strata have data)
- **0.5-0.8:** Moderate coverage (some sparse strata)
- **<0.5:** Sparse coverage (limited strata available)

---

## Common Patterns

### Pattern 1: Agent A looks better due to easier tasks
```
overall_advantage: 0.15      (Agent A appears 15% better)
confounded_effect: true      (confounding detected)
true_effect: 0.05            (actually only 5% better)
confounding_strength: 0.3    (moderate confounding)
```
→ Agent A was assigned easier tasks historically. It IS better, but not by as much.

### Pattern 2: Agent A is genuinely better
```
overall_advantage: 0.15      (Agent A appears 15% better)
confounded_effect: false     (no confounding)
true_effect: 0.15            (truly 15% better)
confounding_strength: 0.05   (negligible confounding)
```
→ No worries. Agent A is clearly superior across conditions.

### Pattern 3: Simpson's Paradox (A is better everywhere, but looks worse overall)
```
overall_advantage: -0.08     (Agent A appears worse)
confounded_effect: true      (confounding detected)
true_effect: 0.10            (actually 10% better!)
confounding_strength: 0.6    (strong confounding)
```
→ Task distribution is skewed. A got harder tasks but is superior at each difficulty level.

---

## Performance & Limits

- **Max tasks analyzed:** 5,000 per agent (configurable via `limit` parameter)
- **Expected latency:** 200-500ms for 1,000-task histories
- **Min data required:** ≥2 tasks per agent per stratum (enforced)
- **Strata produced:** Depends on confounder values present in data
  - Typical: 3-15 strata (3 complexity levels × 3 KB sizes = 9 total)
  - Maximum: ~50 strata (5 confounders × 3 bins each)

---

## API Endpoint Reference

### Endpoint
```
GET /api/analytics/agents/stratified-comparison
```

### Query Parameters
| Parameter | Type | Default | Description |
|---|---|---|---|
| `agent_a` | string | **required** | First agent ID |
| `agent_b` | string | **required** | Second agent ID |
| `metric` | string | `success_rate` | Metric to compare: `success_rate`, `error_rate`, `avg_duration_ms` |
| `confounders` | string | `query_complexity` | Comma-separated confounder list |
| `limit` | integer | 1000 | Max tasks per agent (10-5000) |

### Response Fields
See `StratifiedComparison.to_dict()` in `confounder_control_analyzer.py` for full schema.

### Error Responses
| Status | Condition |
|---|---|
| 404 | Insufficient data for comparison (agent has <10 tasks or no overlapping strata) |
| 400 | Invalid parameter (metric, confounder) |
| 401 | Missing/invalid authentication |
| 403 | Insufficient permissions |

---

## Implementation Details

### Stratification Algorithm (O(n log n))

1. **Retrieve histories:** Get last N tasks for each agent
2. **Partition by confounder:** For each confounder:
   - Extract confounder value from task metadata
   - Bin to category (low/medium/high)
   - Group tasks
3. **Compute metrics:** Within each stratum:
   - Calculate metric (success_rate, avg_duration_ms, etc.)
   - Compute confidence based on sample size
4. **Detect confounding:** Check if metric variance is large (CV > 0.15)
5. **Estimate true effect:** Compute weighted average of within-stratum differences
6. **Generate interpretation:** Summarize findings in human language

### Confidence Scoring

Sample size confidence (applied to all metrics):
- n=10 → confidence 0.67
- n=50 → confidence 0.89
- n=100+ → confidence 1.0

Formula: `confidence = min(1.0, 0.3 + sqrt(n) / 20)`

### Confounding Detection

Coefficient of variation (CV) across strata:
```
CV = std_dev(metric_values) / mean(metric_values)
confounded = CV > 0.15
strength = min(1.0, CV)
```

CV > 0.15 indicates at least 15% variation in metrics across conditions, suggesting confounding is active.

---

## Testing

Run the test suite:

```bash
python3 -m pytest autobot-backend/tests/api/test_analytics_stratified.py -v
```

Tests cover:
- Stratification by all supported confounders
- Metric computation (success_rate, error_rate, avg_duration_ms)
- Confidence scoring based on sample size
- Confounding detection
- True effect estimation
- Simpson's Paradox scenarios
- JSON serialization
- API error handling

---

## Future Enhancements

Possible extensions (not yet implemented):

1. **Multi-agent comparison** - Compare 3+ agents simultaneously
2. **Interaction effects** - Detect if confounders interact (e.g., complexity + load)
3. **Causal inference** - Use propensity score matching for even stronger control
4. **Dynamic bins** - Auto-determine optimal strata boundaries from data
5. **Temporal stratification** - Compare agents across time periods
6. **Cost-benefit analysis** - Weight agents by cost/latency/quality trade-off
