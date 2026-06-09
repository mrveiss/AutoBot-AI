# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Causal Error Analyzer

Analyzes errors using causal reasoning patterns to identify root causes
and cascading failures, not just symptoms.

Integration point for the Think Tool with causal reasoning guidance.
"""

from dataclasses import dataclass
from typing import Any, Dict

from agent_loop.think_tool import ThinkTool
from agent_loop.types import ThinkCategory, ThinkResult
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass
class CausalErrorAnalysis:
    """Result of causal error analysis."""

    error_description: str
    think_result: ThinkResult
    root_cause: str
    causal_chain: str  # "A → B → C → Observable symptom"
    confounders_identified: list[str]
    confidence: float  # How confident in this causal analysis (0.0-1.0)
    recommended_action: str


class CausalErrorAnalyzer:
    """
    Analyzes errors using causal reasoning to explain WHY errors occur.

    This is distinct from simple error handling (RETRY, SKIP, ABORT).
    It provides deep understanding of error causation for better debugging.
    """

    def __init__(self, think_tool: ThinkTool | None = None):
        """
        Initialize the analyzer.

        Args:
            think_tool: Optional ThinkTool instance (creates new if None)
        """
        self.think_tool = think_tool or ThinkTool()

    async def analyze_error_causally(
        self,
        error: Exception,
        context: Dict[str, Any],
        execution_history: list[Dict[str, Any]] | None = None,
    ) -> CausalErrorAnalysis:
        """
        Analyze an error using causal reasoning.

        Args:
            error: The exception that occurred
            context: Execution context (step info, workflow state, etc.)
            execution_history: Previous execution events for causal chain

        Returns:
            CausalErrorAnalysis with root cause and causal chain
        """
        # Build context for causal analysis
        analysis_context = self._build_analysis_context(error, context, execution_history or [])

        # Use Think Tool with causal reasoning
        think_result = await self.think_tool.think(
            category=ThinkCategory.CAUSAL_ANALYSIS,
            context=analysis_context,
            additional_prompt=(
                "Focus on identifying the causal chain from root cause to "
                "the observable error. Identify confounders that might be "
                "masking the true cause."
            ),
        )

        # Parse the think result into structured analysis
        analysis = self._parse_causal_result(error, think_result)

        logger.info(
            "Causal Error Analysis: root_cause=%s, confidence=%.2f",
            analysis.root_cause,
            analysis.confidence,
        )

        return analysis

    def _build_analysis_context(
        self,
        error: Exception,
        context: Dict[str, Any],
        execution_history: list[Dict[str, Any]],
    ) -> str:
        """Build context string for causal analysis."""
        parts = [
            "# Error Context",
            "",
            f"Error Type: {type(error).__name__}",
            f"Error Message: {str(error)}",
            "",
            "# Execution Context",
        ]

        if context:
            for key, value in context.items():
                if key not in ["error_config"]:  # Skip irrelevant fields
                    parts.append(f"- {key}: {value}")

        if execution_history:
            parts.extend(
                [
                    "",
                    "# Recent Execution History (may reveal causal chain)",
                ]
            )
            for event in execution_history[-5:]:  # Last 5 events
                parts.append(
                    f"- {event.get('timestamp', 'N/A')}: "
                    f"{event.get('event_type', 'unknown')} - "
                    f"{event.get('description', '')}"
                )

        parts.extend(
            [
                "",
                "# Analysis Task",
                "Build a causal chain showing how the error occurred.",
                "Example: Missing index → Full table scan → Timeout",
                "Identify confounders that might mask the true root cause.",
            ]
        )

        return "\n".join(parts)

    def _parse_causal_result(self, error: Exception, think_result: ThinkResult) -> CausalErrorAnalysis:
        """Parse Think Tool result into structured analysis."""
        # Extract key information from the reasoning
        reasoning = think_result.reasoning
        conclusion = think_result.conclusion
        confidence = think_result.confidence

        # Parse causal chain from reasoning (simplified extraction)
        causal_chain = self._extract_causal_chain(reasoning)
        # Prefer conclusion for root cause — it's the ThinkTool's explicit summary;
        # fall back to extracting from raw reasoning when conclusion is empty.
        root_cause = self._extract_root_cause(conclusion or reasoning)

        return CausalErrorAnalysis(
            error_description=str(error),
            think_result=think_result,
            root_cause=root_cause,
            causal_chain=causal_chain,
            confounders_identified=think_result.risks_identified,
            confidence=confidence,
            recommended_action=conclusion,
        )

    @staticmethod
    def _extract_causal_chain(reasoning: str) -> str:
        """Extract the causal chain (A → B → C) from reasoning text."""
        # Look for arrow patterns in reasoning
        lines = reasoning.split("\n")
        for line in lines:
            if "→" in line or "->" in line:
                return line.strip()
        # Fallback: return first substantive line
        for line in lines:
            if line.strip() and not line.strip().startswith("#"):
                return line.strip()
        return "Unknown causal chain"

    @staticmethod
    def _extract_root_cause(reasoning: str) -> str:
        """Extract root cause from reasoning."""
        # Look for "root cause" mentions
        import re

        pattern = r"(?:root cause|fundamental cause)[:\s]+([^.\n]+)"
        match = re.search(pattern, reasoning, re.IGNORECASE)
        if match:
            return match.group(1).strip()

        # Fallback: look for initial cause in causal chain
        lines = reasoning.split("\n")
        for line in lines:
            if "→" in line or "->" in line:
                # Get the first part before the first arrow
                parts = re.split(r"→|->", line)
                if parts:
                    return parts[0].strip()

        return "Undetermined root cause"


# =============================================================================
# Convenience Function
# =============================================================================


async def analyze_error_causally(
    error: Exception,
    step_id: str,
    workflow_id: str | None = None,
    execution_history: list[Dict[str, Any]] | None = None,
) -> CausalErrorAnalysis:
    """
    Convenience function to analyze an error causally.

    Args:
        error: The exception that occurred
        step_id: The step that failed
        workflow_id: Optional workflow ID
        execution_history: Optional execution events

    Returns:
        CausalErrorAnalysis
    """
    context = {
        "step_id": step_id,
        "workflow_id": workflow_id,
        "error_type": type(error).__name__,
    }
    analyzer = CausalErrorAnalyzer()
    return await analyzer.analyze_error_causally(error, context, execution_history)
