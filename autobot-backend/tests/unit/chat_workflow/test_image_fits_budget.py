# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""image_fits_budget gates a screenshot on the history token budget (#11538)."""

from __future__ import annotations

from chat_workflow.vision_capability import image_fits_budget
from context_window_manager import ContextWindowManager


def test_small_prompt_fits_and_oversized_image_cost_does_not():
    budget = ContextWindowManager().get_max_history_tokens("any-model")
    assert image_fits_budget("hi", "any-model", 10)
    assert not image_fits_budget("hi", "any-model", budget + 1)
