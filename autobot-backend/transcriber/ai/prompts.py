# autobot-backend/transcriber/ai/prompts.py
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Domain-agnostic analysis prompts for the transcriber module."""

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
