# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Anthropic Provider - Thin adapter exposing AnthropicProvider in the
llm_interface_pkg.providers namespace (#4096).

All inference logic lives in ``llm_providers.AnthropicProvider``.  This module
re-exports it under the ``llm_interface_pkg.providers`` package so callers that
import from this namespace get the canonical implementation without duplication.
"""

from llm_providers.anthropic_provider import AnthropicProvider

__all__ = ["AnthropicProvider"]
