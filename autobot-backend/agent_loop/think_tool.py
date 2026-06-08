# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Think Tool - Reasoning Scratchpad

Implements the Devin-inspired Think Tool for mandatory reasoning before
critical decisions. This provides a structured way for the agent to
reason through complex decisions and record that reasoning.

Mandatory Think Cases (from Devin):
1. Before critical git/GitHub decisions
2. When transitioning from exploring to making changes
3. Before reporting completion to user

The Think Tool:
- Forces explicit reasoning at decision points
- Records reasoning in the event stream
- Improves decision quality through structured thinking
- Provides audit trail for debugging
"""

from dataclasses import dataclass
from typing import Any

from agent_loop.types import ThinkCategory, ThinkResult
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import DEFAULT_LLM_MODEL

logger = get_logger(__name__)


# =============================================================================
# Think Tool Prompts
# =============================================================================

THINK_PROMPTS = {
    ThinkCategory.GIT_DECISION: """
You are about to make a git/GitHub decision. Before proceeding, think through:

1. What git operation am I about to perform?
2. What are the potential consequences?
3. Is this reversible? If not, am I sure this is correct?
4. Have I verified the current state (git status, branch, etc.)?
5. Could this affect other contributors or the remote repository?

Provide your reasoning and conclusion.
""",
    ThinkCategory.TRANSITION: """
You are transitioning from exploration/research to making changes. Think through:

1. Do I have enough information to proceed?
2. What is my plan for making changes?
3. What are the risks of these changes?
4. Have I considered alternative approaches?
5. Should I get user confirmation before proceeding?

Provide your reasoning and conclusion.
""",
    ThinkCategory.COMPLETION: """
You are about to report completion to the user. Think through:

1. Have I actually completed all requested tasks?
2. Have I verified my changes work correctly?
3. Are there any edge cases I haven't handled?
4. Is there anything I should warn the user about?
5. Have I cleaned up any temporary changes or files?

Provide your reasoning and conclusion.
""",
    ThinkCategory.PROBLEM_ANALYSIS: """
Analyze this problem thoroughly:

1. What is the root cause?
2. What are the symptoms vs the actual issue?
3. What information am I missing?
4. What are possible solutions?
5. What are the trade-offs of each solution?

Provide your reasoning and conclusion.
""",
    ThinkCategory.APPROACH_SELECTION: """
I need to select an approach. Think through:

1. What are my options?
2. What are the pros and cons of each?
3. Which aligns best with the project's patterns?
4. Which is most maintainable long-term?
5. What does the user likely prefer?

Provide your reasoning and conclusion.
""",
    ThinkCategory.ERROR_RECOVERY: """
An error has occurred. Think through:

1. What exactly went wrong?
2. What is the root cause?
3. Can I retry with a different approach?
4. Should I escalate to the user?
5. How can I prevent this in the future?

Provide your reasoning and conclusion.
""",
    ThinkCategory.ASSUMPTION_CHECK: """
Validate my assumptions:

1. What am I assuming about the codebase?
2. What am I assuming about the user's intent?
3. What am I assuming about the environment?
4. Which assumptions have I verified?
5. Which assumptions could be wrong?

Provide your reasoning and conclusion.
""",
    ThinkCategory.SELF_REFLECTION: """
Evaluate the quality of this response against the original query (RLM pattern):

1. Does the response directly answer the query?
2. Is the response accurate and complete?
3. Are there important aspects the response missed?
4. Is the reasoning sound and well-structured?
5. Would a follow-up pass with specific guidance produce a better answer?

Provide your quality score (0.0-1.0) and specific critique.
""",
    ThinkCategory.GENERAL: """
Think through this situation:

1. What is the current context?
2. What are my options?
3. What are the trade-offs?
4. What is the best path forward?
5. What should I communicate to the user?

Provide your reasoning and conclusion.
""",
    ThinkCategory.CAUSAL_ANALYSIS: """
Apply a Causal Reasoning Framework to identify WHY, not just WHAT:

1. What is the direct cause? (mechanism, not just correlation)
2. What are the secondary/cascading effects along the causal chain?
3. What confounders could explain the observation without a causal link?
4. How would you isolate the cause from confounders?
5. What is the confidence level and what would change it?

Structure your answer as a causal chain: A → B → C (each arrow is a mechanism).
Distinguish: X CAUSES Y (mechanistic) vs X CORRELATES WITH Y (observational).

Provide your causal reasoning and conclusion.
""",
}


# =============================================================================
# Think Tool Configuration
# =============================================================================


@dataclass
class ThinkToolConfig:
    """Configuration for the Think Tool."""

    # LLM settings
    model: str = DEFAULT_LLM_MODEL
    temperature: float = 0.3  # Lower temperature for reasoning
    max_tokens: int = 1000

    # Timeouts
    timeout_ms: int = 15000

    # Mandatory categories
    mandatory_categories: tuple[ThinkCategory, ...] = (
        ThinkCategory.GIT_DECISION,
        ThinkCategory.TRANSITION,
        ThinkCategory.COMPLETION,
    )

    # Logging
    log_reasoning: bool = True


# =============================================================================
# Think Tool
# =============================================================================


class ThinkTool:
    """
    Structured reasoning tool for critical decision points.

    Implements the Devin pattern of mandatory thinking before
    certain operations.
    """

    def __init__(
        self,
        llm_client: Any | None = None,
        config: ThinkToolConfig | None = None,
    ):
        """
        Initialize the Think Tool.

        Args:
            llm_client: Optional LLM client for reasoning (uses Ollama if None)
            config: Tool configuration
        """
        self.llm_client = llm_client
        self.config = config or ThinkToolConfig()
        self._think_history: list[ThinkResult] = []

    async def think(
        self,
        category: ThinkCategory,
        context: str,
        task_id: str | None = None,
        additional_prompt: str | None = None,
    ) -> ThinkResult:
        """
        Perform structured reasoning for a decision point.

        Args:
            category: The category of thinking required
            context: Current context/situation description
            task_id: Optional task ID for event tracking
            additional_prompt: Optional additional instructions

        Returns:
            ThinkResult with reasoning and conclusion
        """
        logger.info("Think Tool: %s - Starting reasoning", category.name)

        # Build the full prompt
        base_prompt = THINK_PROMPTS.get(category, THINK_PROMPTS[ThinkCategory.GENERAL])
        full_prompt = self._build_prompt(base_prompt, context, additional_prompt)

        # Get reasoning from LLM
        try:
            response = await self._get_llm_response(full_prompt)
            result = self._parse_response(response, category, task_id)
        except Exception as e:
            logger.error("Think Tool failed: %s", e)
            result = ThinkResult(
                category=category,
                reasoning=f"Reasoning failed: {e}",
                conclusion="Unable to complete reasoning - proceeding with caution",
                confidence=0.3,
                risks_identified=["Reasoning process failed"],
                task_id=task_id,
            )

        # Store in history
        self._think_history.append(result)

        if self.config.log_reasoning:
            logger.info(
                "Think Tool: %s - Conclusion: %s (confidence: %.2f)",
                category.name,
                result.conclusion[:100],
                result.confidence,
            )

        return result

    async def think_if_mandatory(
        self,
        category: ThinkCategory,
        context: str,
        task_id: str | None = None,
    ) -> ThinkResult | None:
        """
        Think only if the category is mandatory.

        Args:
            category: The category of thinking
            context: Current context
            task_id: Optional task ID

        Returns:
            ThinkResult if category is mandatory, None otherwise
        """
        if category in self.config.mandatory_categories:
            return await self.think(category, context, task_id)
        return None

    def is_mandatory(self, category: ThinkCategory) -> bool:
        """Check if a category requires mandatory thinking."""
        return category in self.config.mandatory_categories

    def get_history(self, task_id: str | None = None) -> list[ThinkResult]:
        """Get think history, optionally filtered by task."""
        if task_id:
            return [r for r in self._think_history if r.task_id == task_id]
        return self._think_history.copy()

    def clear_history(self) -> None:
        """Clear the think history."""
        self._think_history.clear()

    def _build_prompt(
        self,
        base_prompt: str,
        context: str,
        additional_prompt: str | None,
    ) -> str:
        """Build the full prompt for the LLM."""
        parts = [
            "# Reasoning Task",
            "",
            base_prompt.strip(),
            "",
            "# Current Context",
            "",
            context,
        ]

        if additional_prompt:
            parts.extend(["", "# Additional Instructions", "", additional_prompt])

        parts.extend(
            [
                "",
                "# Response Format",
                "",
                "Provide your response in this format:",
                "",
                "## Reasoning",
                "[Your step-by-step reasoning]",
                "",
                "## Alternatives Considered",
                "- [Alternative 1]",
                "- [Alternative 2]",
                "",
                "## Risks Identified",
                "- [Risk 1]",
                "- [Risk 2]",
                "",
                "## Conclusion",
                "[Your final decision/conclusion]",
                "",
                "## Confidence",
                "[A number from 0.0 to 1.0 indicating your confidence]",
            ]
        )

        return "\n".join(parts)

    async def _get_llm_response(self, prompt: str) -> str:
        """Get a response from the LLM."""
        if self.llm_client:
            # Use provided client
            return await self.llm_client.generate(prompt)

        # Use Ollama directly via the shared helper
        from autobot_shared.ssot_config import get_config
        from llm_shared.ollama_helpers import call_ollama_generate

        ssot = get_config()
        return await call_ollama_generate(
            prompt=prompt,
            model=self.config.model,
            base_url=ssot.ollama_url,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            timeout_ms=self.config.timeout_ms,
        )

    def _parse_response(
        self,
        response: str,
        category: ThinkCategory,
        task_id: str | None,
    ) -> ThinkResult:
        """Parse the LLM response into a ThinkResult."""
        # Extract sections from response
        reasoning = self._extract_section(response, "Reasoning", response)
        alternatives = self._extract_list(response, "Alternatives Considered")
        risks = self._extract_list(response, "Risks Identified")
        conclusion = self._extract_section(response, "Conclusion", "No conclusion")
        confidence = self._extract_confidence(response)

        return ThinkResult(
            category=category,
            reasoning=reasoning,
            conclusion=conclusion,
            confidence=confidence,
            alternatives_considered=alternatives,
            risks_identified=risks,
            task_id=task_id,
        )

    def _extract_section(
        self,
        text: str,
        section_name: str,
        default: str,
    ) -> str:
        """Extract a section from the response."""
        import re

        pattern = rf"##\s*{section_name}\s*\n(.*?)(?=##|\Z)"
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return default

    def _extract_list(self, text: str, section_name: str) -> list[str]:
        """Extract a list from a section."""
        section = self._extract_section(text, section_name, "")
        items = []
        for line in section.split("\n"):
            line = line.strip()
            if line.startswith("-") or line.startswith("*"):
                items.append(line[1:].strip())
        return items

    def _extract_confidence(self, text: str) -> float:
        """Extract confidence score from response."""
        import re

        section = self._extract_section(text, "Confidence", "0.7")
        # Look for a decimal number
        match = re.search(r"(0?\.\d+|1\.0|[01])", section)
        if match:
            try:
                return float(match.group(1))
            except ValueError:
                pass
        return 0.7  # Default confidence


# =============================================================================
# Convenience Functions
# =============================================================================


async def think_before_git(
    context: str,
    think_tool: ThinkTool | None = None,
    task_id: str | None = None,
) -> ThinkResult:
    """
    Convenience function to think before git operations.

    Args:
        context: Description of the git operation
        think_tool: Optional ThinkTool instance
        task_id: Optional task ID

    Returns:
        ThinkResult with reasoning
    """
    tool = think_tool or ThinkTool()
    return await tool.think(ThinkCategory.GIT_DECISION, context, task_id)


async def think_before_completion(
    context: str,
    think_tool: ThinkTool | None = None,
    task_id: str | None = None,
) -> ThinkResult:
    """
    Convenience function to think before reporting completion.

    Args:
        context: Description of what was completed
        think_tool: Optional ThinkTool instance
        task_id: Optional task ID

    Returns:
        ThinkResult with reasoning
    """
    tool = think_tool or ThinkTool()
    return await tool.think(ThinkCategory.COMPLETION, context, task_id)


async def think_before_transition(
    context: str,
    think_tool: ThinkTool | None = None,
    task_id: str | None = None,
) -> ThinkResult:
    """
    Convenience function to think before transitioning modes.

    Args:
        context: Description of the transition
        think_tool: Optional ThinkTool instance
        task_id: Optional task ID

    Returns:
        ThinkResult with reasoning
    """
    tool = think_tool or ThinkTool()
    return await tool.think(ThinkCategory.TRANSITION, context, task_id)


async def think_causally(
    context: str,
    think_tool: ThinkTool | None = None,
    task_id: str | None = None,
) -> ThinkResult:
    """
    Convenience function for causal reasoning — WHY not just WHAT.

    Args:
        context: Situation or problem to analyse causally
        think_tool: Optional ThinkTool instance
        task_id: Optional task ID

    Returns:
        ThinkResult with causal chain reasoning
    """
    tool = think_tool or ThinkTool()
    return await tool.think(ThinkCategory.CAUSAL_ANALYSIS, context, task_id)
