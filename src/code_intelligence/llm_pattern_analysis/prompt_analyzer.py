# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Prompt Analyzer Module

Analyzes prompt templates for optimization opportunities.
Detects issues like redundant instructions, excessive context,
and suggests improvements for token efficiency.

Extracted from llm_pattern_analyzer.py as part of Issue #381 refactoring.
"""

from typing import List

from src.code_intelligence.llm_pattern_analysis.data_models import PromptAnalysisResult
from src.code_intelligence.llm_pattern_analysis.types import (
    EXCESSIVE_CONTEXT_PATTERNS,
    FORMAT_INEFFICIENCY_PATTERNS,
    PromptIssueType,
    REDUNDANT_PATTERNS,
    TEMPLATE_VAR_PATTERNS,
)


class PromptAnalyzer:
    """
    Analyzes prompt templates for optimization opportunities.

    Detects issues like redundant instructions, excessive context,
    and suggests improvements for token efficiency.

    Refactored to use PromptAnalysisResult (Issue #312)
    """

    # Issue #380: Class patterns reference module-level pre-compiled patterns
    # (Legacy access preserved for backward compatibility)
    REDUNDANT_PATTERNS = REDUNDANT_PATTERNS
    EXCESSIVE_CONTEXT_MARKERS = EXCESSIVE_CONTEXT_PATTERNS
    FORMAT_INEFFICIENCIES = FORMAT_INEFFICIENCY_PATTERNS

    @classmethod
    def analyze_prompt(cls, prompt: str) -> List[PromptIssueType]:
        """
        Analyze a prompt for potential issues.

        Args:
            prompt: The prompt text to analyze

        Returns:
            List of detected issues
        """
        issues = []

        # Check for redundant patterns (Issue #380: use pre-compiled patterns)
        for pattern in REDUNDANT_PATTERNS:
            if pattern.search(prompt):
                issues.append(PromptIssueType.REDUNDANT_INSTRUCTIONS)
                break

        # Check for excessive context (Issue #380: use pre-compiled patterns)
        for pattern in EXCESSIVE_CONTEXT_PATTERNS:
            if pattern.search(prompt):
                issues.append(PromptIssueType.EXCESSIVE_CONTEXT)
                break

        # Check for format inefficiencies (Issue #380: use pre-compiled patterns)
        for pattern in FORMAT_INEFFICIENCY_PATTERNS:
            if pattern.search(prompt):
                issues.append(PromptIssueType.INEFFICIENT_FORMAT)
                break

        # Check for repetitive content
        words = prompt.lower().split()
        if len(words) > 50:
            word_freq = {}
            for word in words:
                if len(word) > 4:
                    word_freq[word] = word_freq.get(word, 0) + 1
            # If any word appears more than 10% of time, consider repetitive
            for word, count in word_freq.items():
                if count > len(words) * 0.1 and count > 5:
                    issues.append(PromptIssueType.REPETITIVE_CONTENT)
                    break

        return issues

    @classmethod
    def estimate_tokens(cls, text: str) -> int:
        """
        Estimate token count for text.

        Uses a simple heuristic: ~4 characters per token for English text.
        More accurate counting would require the actual tokenizer.

        Args:
            text: The text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4 + 1

    @classmethod
    def extract_variables(cls, template: str) -> List[str]:
        """
        Extract variable placeholders from a prompt template.

        Args:
            template: The template text

        Returns:
            List of variable names found
        """
        # Issue #380: Use pre-compiled patterns for variable extraction
        variables = set()
        for pattern in TEMPLATE_VAR_PATTERNS:
            matches = pattern.findall(template)
            variables.update(matches)

        return list(variables)

    @classmethod
    def suggest_improvements(
        cls, prompt: str, issues: List[PromptIssueType]
    ) -> List[str]:
        """
        Suggest improvements for detected issues.

        DEPRECATED: Use PromptAnalysisResult.get_suggestions() instead.
        Kept for backward compatibility.

        Args:
            prompt: The original prompt
            issues: List of detected issues

        Returns:
            List of improvement suggestions
        """
        result = PromptAnalysisResult(
            issues=issues,
            estimated_tokens=cls.estimate_tokens(prompt),
            variables=cls.extract_variables(prompt),
        )
        return result.get_suggestions(prompt)
