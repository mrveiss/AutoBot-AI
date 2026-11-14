# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# autobot-backend/transcriber/ai/prompts.py
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Domain-agnostic analysis prompts for the transcriber module."""

from autobot_shared.env_utils import env_int_clamped

#: Output-token budget for one analysis, shared by both analysis surfaces (#16924).
#: Explicit because ``LLMService.stream()`` otherwise applies the general task
#: default (1024), which cut long summaries off; before that, the providers'
#: own default applied (4096 on most of them).
ANALYSIS_MAX_TOKENS: int = env_int_clamped(
    "AUTOBOT_TRANSCRIPT_ANALYSIS_MAX_TOKENS", default=4096, min_v=256, max_v=32768
)

_PROMPTS = {
    "summarize": (
        "You are an expert analyst. Read the following transcript and write a concise, "
        "structured summary covering the main topics discussed, decisions made, and action items. "
        "Be factual. Use bullet points for clarity."
    ),
    "key_facts": (
        "You are an expert analyst. Extract the key facts, figures, names, dates, and decisions "
        "from the following transcript. Present them as a numbered list."
    ),
    "protocol": (
        "You are an expert secretary. Draft a formal meeting protocol from the following transcript. "
        "Include: attendees (by speaker label), agenda items discussed, decisions made, "
        "action items with responsible parties. Be formal and precise."
    ),
}


def get_system_prompt(action: str, *, custom_question: str | None = None) -> str:
    if action == "custom":
        q = custom_question or "Analyze this transcript."
        return (
            f"You are an expert analyst. Answer the following question about the transcript: {q}\n"
            "Be concise and factual. Reference specific speakers and timestamps where relevant."
        )
    return _PROMPTS.get(action, _PROMPTS["summarize"])
