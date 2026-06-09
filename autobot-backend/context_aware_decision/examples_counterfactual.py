# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Examples: Counterfactual Reasoning Integration

Demonstrates how to use CounterfactualReasoner with DecisionEngine
to preview consequences before committing to decisions.

Not included in package; for development and documentation only.
"""

import time

from autobot_shared.async_compat import run_or_schedule

from .counterfactual_reasoner import CounterfactualReasoner
from .decision_engine import DecisionEngine
from .models import ContextElement, DecisionContext
from .types import ContextType, DecisionType

# =============================================================================
# Example 1: Network Timeout Scenario
# =============================================================================


async def example_network_timeout():
    """
    Scenario: Automation fails with network timeout. What should we do?

    Options:
    1. Retry the request (might work if network recovers)
    2. Escalate to human (slow but safe)
    3. Wait and try later (might miss deadline)

    Counterfactual reasoning helps decide which is best.
    """
    print("\n" + "=" * 70)
    print("Example 1: Network Timeout - What should we do?")
    print("=" * 70)

    # Create context: automation failed due to network
    context = DecisionContext(
        decision_id="timeout-decision-001",
        decision_type=DecisionType.AUTOMATION_ACTION,
        primary_goal="Complete database sync",
        context_elements=[
            ContextElement(
                context_id="ce-001",
                context_type=ContextType.SYSTEM_STATE,
                content={"network_status": "timeout", "error_code": 504},
                confidence=0.95,
                relevance_score=0.9,
                timestamp=time.time(),
                source="network_monitor",
                metadata={"type": "network", "severity": "high"},
            ),
        ],
        constraints=[],
        available_actions=[
            {
                "action": "retry",
                "action_type": "retry",
                "confidence": 0.6,
                "description": "Retry the network request",
            },
            {
                "action": "escalate",
                "action_type": "escalation",
                "confidence": 0.9,
                "description": "Escalate to human operator",
            },
            {
                "action": "wait",
                "action_type": "monitoring",
                "confidence": 0.5,
                "description": "Wait 30 seconds and retry",
            },
        ],
        risk_factors=[
            {
                "risk_type": "network_timeout",
                "severity": "high",
                "description": "Network connectivity issue",
            }
        ],
        user_preferences={"automation_level": "high", "confirmation_required": False},
        system_state={"load": "normal", "deadline_minutes": 5},
        historical_patterns=[
            {
                "pattern_type": "timeout_recovery",
                "success_rate": 0.75,
                "avg_recovery_time_seconds": 15,
            }
        ],
        timestamp=time.time(),
    )

    # Initialize reasoner
    reasoner = CounterfactualReasoner()

    print("\nContext: Database sync automation failed with network timeout")
    print("Deadline: 5 minutes")
    print("\nAvailable options:")
    for action in context.available_actions:
        print(f"  - {action['action']}: {action['description']}")

    # Predict outcomes for each option
    print("\n" + "-" * 70)
    print("COUNTERFACTUAL PREDICTIONS:")
    print("-" * 70)

    outcomes = {}
    for action in context.available_actions:
        outcome = await reasoner.what_if(action["action"], context, action)
        outcomes[action["action"]] = outcome

        print(f"\nOption: {action['action'].upper()}")
        print(f"  Predicted Success: {outcome.predicted_success_rate:.0%}")
        print(f"  Confidence: {outcome.confidence:.0%} ({outcome.prediction_source})")
        print(f"  Estimated Time: {outcome.estimated_latency_ms}ms")
        print(f"  Fallback Risk: {outcome.fallback_risk}")
        print("  Side Effects:")
        for effect in outcome.side_effects:
            print(
                f"    - {effect['type']}: {effect.get('frequency', 1):.0%} frequency, "
                f"{effect.get('severity', 'unknown')} severity"
            )
        print(f"  Reasoning: {outcome.reasoning}")

    # Make informed decision
    print("\n" + "-" * 70)
    print("DECISION:")
    print("-" * 70)

    best_option = max(outcomes.items(), key=lambda x: x[1].predicted_success_rate)
    print(f"\nRecommended: {best_option[0].upper()}")
    print(f"  Why: {best_option[1].reasoning}")
    print(f"  Success likelihood: {best_option[1].predicted_success_rate:.0%}")


# =============================================================================
# Example 2: Database Connection Pool Exhaustion
# =============================================================================


async def example_database_exhaustion():
    """
    Scenario: Database connection pool exhausted. What should we do?

    Options:
    1. Automate: Create connection pool expansion script (risky, irreversible)
    2. Escalate: Get DBA to manually expand pool (safe but slow)
    3. Retry: Wait for existing connections to drain and retry (fast if works)

    Counterfactual reasoning helps weigh safety vs speed.
    """
    print("\n" + "=" * 70)
    print("Example 2: Database Connection Pool - Safety vs Speed")
    print("=" * 70)

    context = DecisionContext(
        decision_id="db-decision-001",
        decision_type=DecisionType.AUTOMATION_ACTION,
        primary_goal="Execute critical reporting query",
        context_elements=[
            ContextElement(
                context_id="ce-001",
                context_type=ContextType.SYSTEM_STATE,
                content={
                    "db_pool_size": 100,
                    "db_pool_used": 100,
                    "db_pool_pending": 45,
                },
                confidence=0.99,
                relevance_score=0.95,
                timestamp=time.time(),
                source="db_monitor",
                metadata={"type": "database"},
            ),
        ],
        constraints=[],
        available_actions=[
            {
                "action": "automate",
                "action_type": "automation",
                "confidence": 0.7,
                "description": "Run pool expansion script",
                "resource_intensive": True,
            },
            {
                "action": "escalate",
                "action_type": "escalation",
                "confidence": 0.95,
                "description": "Page on-call DBA",
            },
            {
                "action": "retry",
                "action_type": "retry",
                "confidence": 0.4,
                "description": "Wait for connections to drain",
            },
        ],
        risk_factors=[
            {
                "risk_type": "resource_exhaustion",
                "severity": "high",
                "description": "All connections in use",
            }
        ],
        user_preferences={"automation_level": "medium", "risk_tolerance": "low"},
        system_state={"load": "high", "deadline_minutes": 2},
        historical_patterns=[
            {
                "pattern_type": "pool_recovery",
                "success_rate": 0.3,
                "avg_recovery_time_seconds": 120,
            },
            {
                "pattern_type": "pool_expansion",
                "success_rate": 0.95,
                "avg_time_seconds": 30,
            },
        ],
        timestamp=time.time(),
    )

    reasoner = CounterfactualReasoner()

    print("\nContext: Database connection pool 100% exhausted")
    print("Deadline: 2 minutes (reporting SLA)")
    print("Risk tolerance: Low")

    print("\nAvailable options:")
    for action in context.available_actions:
        print(f"  - {action['action']}: {action['description']}")

    print("\n" + "-" * 70)
    print("COUNTERFACTUAL ANALYSIS:")
    print("-" * 70)

    outcomes = {}
    for action in context.available_actions:
        outcome = await reasoner.what_if(action["action"], context, action)
        outcomes[action["action"]] = outcome

        print(f"\n{action['action'].upper()}:")
        print(f"  Success Rate: {outcome.predicted_success_rate:.0%}")
        print(f"  Confidence: {outcome.confidence:.0%}")
        print(f"  Est. Time: {outcome.estimated_latency_ms}ms")
        if outcome.fallback_risk:
            print(f"  ⚠ Risk if fails: {outcome.fallback_risk}")
        if outcome.side_effects:
            print("  Side effects:")
            for effect in outcome.side_effects:
                print(f"    • {effect['type']}: {effect.get('description', '')}")

    print("\n" + "-" * 70)
    print("ANALYSIS:")
    print("-" * 70)

    automate_outcome = outcomes["automate"]
    escalate_outcome = outcomes["escalate"]
    retry_outcome = outcomes["retry"]

    print(f"\nAutomate: {automate_outcome.predicted_success_rate:.0%} success")
    print(f"  ✓ Fast ({automate_outcome.estimated_latency_ms}ms)")
    print("  ✗ High risk (irreversible state mutation)")
    print(f"  ✗ Low confidence ({automate_outcome.confidence:.0%})")

    print(f"\nEscalate: {escalate_outcome.predicted_success_rate:.0%} success")
    print("  ✓ Very safe (professional DBA)")
    print(f"  ✓ High confidence ({escalate_outcome.confidence:.0%})")
    print(f"  ✗ Slow ({escalate_outcome.estimated_latency_ms}ms > 2min deadline)")

    print(f"\nRetry: {retry_outcome.predicted_success_rate:.0%} success")
    print("  ✓ Fastest")
    print("  ✗ Only 40% likely to succeed (pool won't drain in time)")
    print(f"  ✗ Low confidence ({retry_outcome.confidence:.0%})")

    print("\nRECOMMENDATION: Escalate to DBA")
    print("  • High success rate (95%) beats speed here")
    print("  • 2-minute deadline is tight, but DBA can decide if automated expansion is safe")
    print("  • Avoid automation (irreversible state mutation in high-load condition)")


# =============================================================================
# Example 3: Integration with Decision Engine
# =============================================================================


async def example_enhanced_decision():
    """
    Show how to enhance Decision objects with counterfactual predictions.

    This demonstrates the integration pattern: DecisionEngine makes decision,
    CounterfactualReasoner adds "what if" insights to all alternatives.
    """
    print("\n" + "=" * 70)
    print("Example 3: Enhanced Decisions with Counterfactual Insights")
    print("=" * 70)

    # Create minimal context
    context = DecisionContext(
        decision_id="enhanced-001",
        decision_type=DecisionType.AUTOMATION_ACTION,
        primary_goal="Test decision",
        context_elements=[],
        constraints=[],
        available_actions=[
            {"action": "retry", "confidence": 0.6},
            {"action": "escalate", "confidence": 0.9},
        ],
        risk_factors=[],
        user_preferences={},
        system_state={},
        historical_patterns=[],
        timestamp=time.time(),
    )

    # Make decision with engine
    engine = DecisionEngine()
    decision = await engine.make_decision(context)

    print(f"\nDecision: {decision.chosen_action['action'].upper()}")
    print(f"Confidence: {decision.confidence:.0%}")

    # Enhance with counterfactual reasoning
    reasoner = CounterfactualReasoner()

    print("\nAdding counterfactual predictions...")
    for action in context.available_actions:
        outcome = await reasoner.what_if(action["action"], context, action)
        decision.intervention_effects.append(outcome)

    print(f"Enhanced decision now includes {len(decision.intervention_effects)} predictions:")
    for effect in decision.intervention_effects:
        print(
            f"  • {effect.option}: {effect.predicted_success_rate:.0%} "
            f"({effect.prediction_source}, confidence {effect.confidence:.0%})"
        )

    # Show serialization
    print("\nSerialized decision.to_dict():")
    decision_dict = decision.to_dict()
    print(f"  intervention_effects: {len(decision_dict['intervention_effects'])} entries")
    for ie in decision_dict["intervention_effects"]:
        print(f"    - {ie['option']}: {ie['predicted_success_rate']:.0%}")


# =============================================================================
# Main
# =============================================================================


async def main():
    """Run all examples."""
    await example_network_timeout()
    await example_database_exhaustion()
    await example_enhanced_decision()


if __name__ == "__main__":
    run_or_schedule(main())
