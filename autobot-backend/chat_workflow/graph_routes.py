# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Routers split out of ``graph.py`` so the grandfathered file does not grow (#21022)."""

from typing import Any, Dict


def route_after_judge(state: Dict[str, Any]) -> str:
    """Route after inline judge (#10599).

    If the judge set a refinement hint and hasn't exhausted its one-shot
    budget, loop back to generate_response.  Otherwise proceed to persist.
    """
    hint = state.get("rlm_refinement_hint", "")
    judge_count = state.get("judge_count", 0)
    if hint and judge_count == 1:
        # judge_count==1 means the hint was just set on this pass; route back
        # to generate_response for exactly one regeneration.
        return "generate_response"
    return "persist_conversation"
