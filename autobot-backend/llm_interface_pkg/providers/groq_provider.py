# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Groq Provider - Thin adapter exposing GroqProvider in the
llm_interface_pkg.providers namespace (#4096).

All inference logic lives in ``llm_providers.GroqProvider``.  This module
re-exports it under the ``llm_interface_pkg.providers`` package so callers that
import from this namespace get the canonical implementation without duplication.
"""

from llm_providers.groq_provider import GroqProvider

__all__ = ["GroqProvider"]
