# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Recursive Language Model (RLM) subsystem.

Provides self-reflection primitives that allow an LLM to evaluate and
recursively refine its own responses.  The main integration point is the
``reflect_on_response`` node wired into the LangGraph chat workflow
(``chat_workflow/graph.py``).

Issue #1373: Initial RLM prototype.
"""

from rlm.evaluator import ResponseQualityEvaluator
from rlm.rag_refiner import AdaptiveRAGRefiner
from rlm.types import ReflectionResult, ReflectionVerdict, RLMConfig

__all__ = [
    "AdaptiveRAGRefiner",
    "ReflectionResult",
    "ReflectionVerdict",
    "ResponseQualityEvaluator",
    "RLMConfig",
]
