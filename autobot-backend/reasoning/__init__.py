# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Reasoning Module

Provides structured reasoning patterns for agent decision-making, including
causal reasoning frameworks to guide LLM agents toward causal thinking.
"""

from reasoning.causal_reasoning import (
    CausalChain,
    CausalReasoningContext,
    build_causal_reasoning_prompt,
)

__all__ = [
    "CausalChain",
    "CausalReasoningContext",
    "build_causal_reasoning_prompt",
]
