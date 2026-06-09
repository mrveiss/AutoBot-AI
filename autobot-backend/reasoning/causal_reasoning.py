# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Causal Reasoning Module

Provides reusable causal reasoning patterns and prompts to guide LLM agents
toward causal thinking rather than correlational observation.

This module encourages agents to reason about cause-and-effect relationships,
identify confounders, and explain WHY interventions produce outcomes.

Key concepts:
- Causal vs. correlational: "Increases cache size correlates with faster
  response" vs. "Increasing cache size CAUSES faster response because it
  reduces database queries"
- Confounder detection: Identify variables that might explain the observed
  relationship
- Causal chain: Document the sequence of events from intervention to outcome
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import List


class CausalReasoningContext(Enum):
    """Contexts where causal reasoning is most valuable."""

    ERROR_ANALYSIS = auto()  # Understanding why errors occur
    DECISION_ANALYSIS = auto()  # Why interventions should be preferred
    PERFORMANCE_ANALYSIS = auto()  # Why performance changes happen
    FAILURE_DIAGNOSIS = auto()  # Why failures cascaded


@dataclass
class CausalChain:
    """Represents a causal chain from action to outcome."""

    intervention: str  # What was done
    direct_effects: List[str]  # Immediate consequences
    secondary_effects: List[str]  # Downstream consequences
    confounders: List[str]  # Variables that might be confusing the causal story
    confidence: float  # 0.0-1.0 confidence in this causal explanation


# =============================================================================
# Causal Reasoning Prompt Template
# =============================================================================

CAUSAL_REASONING_SNIPPET = """
# Causal Reasoning Framework

When analyzing problems or making decisions, reason causally (not just correlatively).

## Pattern: Causal Explanation

Instead of: "Response time increased after caching was enabled"
Use: "Response time decreased BECAUSE caching was enabled, which prevents
repeated database queries. Each cache hit bypasses ~200ms query latency."

## Checklist for Causal Analysis:

1. **Identify the Intervention**: What action or change occurred?
   - Be specific: "Increased Redis memory limit from 1GB to 4GB"

2. **Trace Direct Effects**: What immediately results from this?
   - Example: "More data can be cached in Redis without eviction"

3. **Follow Secondary Effects**: What happens downstream?
   - Example: "Lower cache eviction rate → fewer cache misses →
     faster lookups"

4. **Find Confounders**: What else might explain the outcome?
   - Example: "Traffic decreased at the same time caching was enabled.
     Traffic drop alone could explain faster response times. How to
     disentangle: Compare cache hit ratio before/after."

5. **Build the Causal Chain**: Connect cause → intermediate effects → outcome
   - Increased Redis memory → Lower eviction → Fewer misses →
     Faster queries

6. **State Confidence**: How sure are you of this causal story?
   - High: Direct measurement of the mechanism (e.g., cache hit ratio)
   - Medium: Timing aligns, confounders unlikely
   - Low: Temporal correlation only, many plausible confounders

## Causal vs. Correlational Language:

AVOID: "X is associated with Y" / "X correlates with Y"
USE: "X CAUSES Y BECAUSE [mechanism]"

AVOID: "When A happened, B improved"
USE: "A caused B to improve by [specific mechanism], confirmed by [evidence]"

AVOID: "A and B often occur together"
USE: "A causes B through the following causal chain:
      A → C → D → B"

## Evidence Hierarchy (Strongest to Weakest):

1. Direct mechanism measurement: "Cache hit ratio increased from 45% to 92%"
2. Controlled comparison: "Before/after in production with no other changes"
3. Temporal alignment: "The change happened immediately after intervention"
4. Correlation with timing: "Both X and outcome Y increased over similar period"
5. Plausibility: "It makes sense that X could cause Y"
"""

# =============================================================================
# Causal Reasoning Patterns for Specific Contexts
# =============================================================================

CAUSAL_REASONING_ERROR_ANALYSIS = """
# Causal Error Analysis

Analyze errors by building the causal chain: What action/state caused this error?

## Pattern: Error Cascade Analysis

For cascading failures, trace the causal chain backwards:

1. **Symptom**: "Database query timeout"

2. **Proximate Cause**: "Query exceeded 30-second timeout"
   - Why? Because it scanned 10M rows instead of 1M

3. **Root Cause**: "No index on (user_id, created_at) column pair"
   - Why does this cause full table scan? The query planner can't narrow
     the dataset efficiently without the index

4. **Confounder Check**:
   - Could high load alone cause this? No—load spike alone wouldn't cause
     a full table scan; the query plan is deterministic
   - Could network latency cause this? No—the issue is query duration,
     not transmission time

5. **Causal Chain**:
   Missing index → Query planner chooses full table scan → 10M row scan
   → CPU/disk I/O bottleneck → Query exceeds timeout → Request fails

This causal reasoning is stronger than "query was slow" because it
identifies the specific mechanism (missing index) rather than just the symptom.
"""

CAUSAL_REASONING_DECISION = """
# Causal Decision Analysis

When choosing between options, reason about intervention effects causally.

## Pattern: Intervention Effect Analysis

Claim: "We should increase cache size because cached queries are faster"

Causal breakdown:
1. **Intervention**: "Increase Redis memory from 1GB to 4GB"
2. **Mechanism**: "More hot data stays in cache (lower eviction rate)"
3. **Effect on Cache Hits**: "Expected increase from 70% to 85%"
   - Mechanism: Fewer evictions means more data survives between requests
4. **Effect on Latency**: "Each cache hit is ~5ms vs ~200ms miss"
   - Expected improvement: 15% × (200-5)ms = ~29ms average latency reduction
5. **Confounders to Rule Out**:
   - Is query pattern changing? (Would affect hit rate independent of cache)
   - Is traffic shifting to different endpoints? (Would change which data is hot)
6. **Cost Analysis**:
   - Cost of 3GB more Redis: ~$50/month
   - Benefit: ~29ms latency improvement across 1M daily queries =
     better user experience
   - ROI: Clear benefit justifies cost

This causal reasoning lets you predict the actual effect size (~29ms)
rather than just saying "caching helps."
"""

CAUSAL_REASONING_PERFORMANCE = """
# Causal Performance Analysis

Explain performance changes by identifying the mechanisms at work.

## Pattern: Performance Degradation Root Cause

Observation: "API response time increased from 200ms to 500ms"

Causal investigation:
1. **Timeline**: When exactly did it degrade?
   - 10am Monday: Started degrading
   - 10:15am: Reached new baseline of 500ms

2. **Correlation Check**: What changed around 10am?
   - Deployment at 9:55am? (likely culprit)
   - Traffic spike? (check metrics)
   - Database load? (check connection pool)

3. **Mechanism for Each Suspect**:

   a) New deployment:
      - Hypothesis: New code path is slower
      - Causal chain: Code change → Added database query → Extra 300ms latency
      - Test: Compare query counts before/after

   b) Traffic spike:
      - Hypothesis: Database connection pool exhausted
      - Causal chain: High concurrency → Pool exhaustion → Queue waits →
                      Extra 300ms per request
      - Test: Check connection pool saturation metrics

   c) Database load:
      - Hypothesis: Slow query blocks connection allocation
      - Causal chain: Slow query holds connection → Others wait for pool
                      → Cascading delays
      - Test: Identify the slow query

4. **Strongest Evidence**:
   - "Deployment correlates perfectly with degradation" (timing is tight)
   - "New deployment added SELECT statement to critical path" (mechanism)
   - "Query shows 300ms latency, exactly explains observed slowdown" (evidence)

5. **Causal Conclusion**:
   "The 10am deployment introduced an N+1 query pattern on the user endpoint.
   Each user fetch now triggers 1 base query + 10 follow-up queries
   (one per related entity). At 100 QPS, this creates 1000 database queries
   where we previously had 100. The database connection pool exhaustion
   causes 300ms average wait time per request."
"""

# =============================================================================
# Integration Helper
# =============================================================================


def build_causal_reasoning_prompt(
    context: CausalReasoningContext,
    situation: str,
    additional_guidance: str | None = None,
) -> str:
    """
    Build a complete prompt incorporating causal reasoning.

    Args:
        context: Type of causal reasoning needed
        situation: Description of the situation to analyze
        additional_guidance: Optional extra instructions

    Returns:
        Complete prompt for LLM
    """
    context_prompts = {
        CausalReasoningContext.ERROR_ANALYSIS: CAUSAL_REASONING_ERROR_ANALYSIS,
        CausalReasoningContext.DECISION_ANALYSIS: CAUSAL_REASONING_DECISION,
        CausalReasoningContext.PERFORMANCE_ANALYSIS: CAUSAL_REASONING_PERFORMANCE,
        CausalReasoningContext.FAILURE_DIAGNOSIS: CAUSAL_REASONING_ERROR_ANALYSIS,
    }

    context_prompt = context_prompts.get(context, CAUSAL_REASONING_SNIPPET)

    prompt_parts = [
        CAUSAL_REASONING_SNIPPET,
        "",
        "## Context-Specific Guidance",
        "",
        context_prompt,
        "",
        "## Your Situation",
        "",
        situation,
    ]

    if additional_guidance:
        prompt_parts.extend(["", "## Additional Instructions", "", additional_guidance])

    prompt_parts.extend(
        [
            "",
            "## Your Analysis",
            "",
            "Apply the causal reasoning framework above to analyze this situation.",
            "Build the causal chain, identify confounders, and state your confidence.",
        ]
    )

    return "\n".join(prompt_parts)
