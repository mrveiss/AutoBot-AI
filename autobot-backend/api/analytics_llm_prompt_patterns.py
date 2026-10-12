# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regex rules that assign a prompt to a ``PromptCategory`` for LLM usage-pattern analytics.

Split out of ``api/analytics_llm_patterns.py`` (#16375) so that router stays under its size ceiling.
"""

from api.schemas_analytics import PromptCategory

# Pattern detection rules for prompt categorization
PROMPT_PATTERNS = {
    PromptCategory.CODE_GENERATION: [
        r"generate\s+(?:code|function|class|method)",
        r"write\s+(?:a\s+)?(?:python|javascript|typescript)",
        r"create\s+(?:a\s+)?(?:function|class|script)",
        r"implement\s+",
        r"code\s+(?:for|that|to)\s+",
    ],
    PromptCategory.CODE_REVIEW: [
        r"review\s+(?:this\s+)?code",
        r"check\s+(?:for\s+)?(?:bugs|errors|issues)",
        r"improve\s+(?:this\s+)?code",
        r"refactor\s+",
        r"optimize\s+(?:this\s+)?code",
    ],
    PromptCategory.DOCUMENTATION: [
        r"document\s+",
        r"write\s+(?:a\s+)?docstring",
        r"add\s+(?:comments|documentation)",
        r"explain\s+(?:this\s+)?code",
        r"readme\s+",
    ],
    PromptCategory.ANALYSIS: [
        r"analyze\s+",
        r"find\s+(?:bugs|issues|problems)",
        r"debug\s+",
        r"investigate\s+",
        r"diagnose\s+",
    ],
    PromptCategory.TASK_PLANNING: [
        r"plan\s+(?:the\s+)?(?:task|project|implementation)",
        r"break\s+down\s+",
        r"steps\s+to\s+",
        r"how\s+(?:should|would)\s+(?:I|we)",
        r"strategy\s+for\s+",
    ],
    PromptCategory.TRANSLATION: [
        r"translate\s+",
        r"convert\s+(?:to|from)\s+",
        r"rewrite\s+in\s+",
    ],
    PromptCategory.SUMMARIZATION: [
        r"summarize\s+",
        r"summary\s+of\s+",
        r"tldr\s+",
        r"brief\s+overview",
    ],
}
