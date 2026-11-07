# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one summarisation prompt (#20852), split out of context_overflow.py to keep that file's size ceiling."""

SUMMARIZATION_PROMPT = (
    "You are summarizing a conversation to preserve context after compaction. "
    "Produce a structured summary that lets the conversation continue seamlessly.\n\n"
    "Use this format:\n\n"
    "## Conversation Summary\n"
    "**Turns summarized:** {{count}}\n\n"
    "### User Goal\n"
    "One sentence describing what the user is trying to accomplish.\n\n"
    "### What Was Done\n"
    "- Bullet points of completed actions, decisions made, and key outputs\n"
    "- Include specific file paths, function names, variable names, URLs, and config values\n"
    "- Note any errors encountered and how they were resolved\n\n"
    "### Current State\n"
    "What is the system/task state right now? What was the last thing discussed?\n\n"
    "### Pending / Next Steps\n"
    "- What remains to be done\n"
    "- Any open questions or blockers\n\n"
    "### Key Context\n"
    "- Every constraint, requirement, preference and decision the user or assistant stated "
    "(for example 'must', 'never', 'always', 'only', 'we decided'): keep each one, "
    "worded as stated, and never drop one to save space\n"
    "- Specific values: model names, ports, paths, credentials references, versions\n\n"
    "If the conversation starts with a previous summary, fold it in: carry forward every "
    "constraint and decision it lists, then add what the newer turns changed.\n\n"
    "Keep the summary under 1000 tokens. Be dense — every token should carry information.\n\n"
    "Conversation to summarize:\n"
    "{{conversation}}\n\n"
    "Provide ONLY the structured summary above — no preamble or meta-commentary."
)
