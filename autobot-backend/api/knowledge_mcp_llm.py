# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ChatOllama factory of the knowledge MCP routes.

Split out of ``api/knowledge_mcp.py`` (#16665) so that grandfathered module does not grow.
"""

from autobot_shared.logging_manager import get_logger
from constants.model_constants import ModelConstants
from dependencies import provide_config_manager
from utils.service_registry import get_service_url

logger = get_logger(__name__)


def _get_chat_ollama():
    """Get a ChatOllama instance for LLM calls (langchain 1.x).

    Issue #1047: Replaces LangChainAgentOrchestrator.llm with ChatOllama.
    Uses SSOT config for Ollama endpoint and model selection.
    """
    try:
        from langchain_ollama import ChatOllama
    except ImportError:
        logger.warning("langchain-ollama not installed — QA chain LLM unavailable")
        return None

    try:
        llm_config = provide_config_manager().get_llm_config()
        model = ModelConstants.DEFAULT_OLLAMA_MODEL
        base_url = llm_config.get("ollama", {}).get("base_url", get_service_url("ollama"))
        return ChatOllama(model=model, base_url=base_url, temperature=0.7)
    except Exception as exc:
        logger.warning("Failed to create ChatOllama: %s", exc)
        return None
