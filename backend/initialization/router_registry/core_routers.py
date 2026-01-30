# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Core Router Loader

This module handles loading of core API routers that are essential for
basic AutoBot functionality. These routers should always be available
and are imported at module level to fail fast if missing.
"""

# Core router imports - these are required for basic functionality
from backend.api.agent import router as agent_router
from backend.api.agent_config import router as agent_config_router
from backend.api.browser_mcp import router as browser_mcp_router
from backend.api.overseer_handlers import router as overseer_router
from backend.api.chat import router as chat_router
from backend.api.database_mcp import router as database_mcp_router
from backend.api.developer import router as developer_router
from backend.api.files import router as files_router
from backend.api.filesystem_mcp import router as filesystem_mcp_router
from backend.api.frontend_config import router as frontend_config_router
from backend.api.git_mcp import router as git_mcp_router
from backend.api.http_client_mcp import router as http_client_mcp_router
from backend.api.intelligent_agent import router as intelligent_agent_router
from backend.api.knowledge import router as knowledge_router
from backend.api.knowledge_mcp import router as knowledge_mcp_router
from backend.api.knowledge_population import router as knowledge_population_router
from backend.api.knowledge_search import router as knowledge_search_router
from backend.api.knowledge_categories import router as knowledge_categories_router
from backend.api.knowledge_collections import router as knowledge_collections_router
from backend.api.knowledge_suggestions import router as knowledge_suggestions_router
from backend.api.knowledge_metadata import router as knowledge_metadata_router
from backend.api.knowledge_tags import router as knowledge_tags_router
from backend.api.llm import router as llm_router
from backend.api.mcp_registry import router as mcp_registry_router
from backend.api.memory import router as memory_router
from backend.api.prometheus_mcp import router as prometheus_mcp_router
from backend.api.prompts import router as prompts_router
from backend.api.redis import router as redis_router
from backend.api.sequential_thinking_mcp import router as sequential_thinking_mcp_router
from backend.api.settings import router as settings_router
from backend.api.data_storage import router as data_storage_router
from backend.api.structured_thinking_mcp import router as structured_thinking_mcp_router
from backend.api.system import router as system_router
from backend.api.vnc_manager import router as vnc_router
from backend.api.vnc_mcp import router as vnc_mcp_router
from backend.api.vnc_proxy import router as vnc_proxy_router
from backend.api.voice import router as voice_router
from backend.api.wake_word import router as wake_word_router
# Issue #729: infrastructure_hosts removed - now served by slm-server


def _get_system_routers() -> list:
    """Get system and settings routers (Issue #560: extracted)."""
    return [
        (chat_router, "", ["chat"], "chat"),
        (system_router, "/system", ["system"], "system"),
        (settings_router, "/settings", ["settings"], "settings"),
        (data_storage_router, "", ["data-storage"], "data_storage"),
        (prompts_router, "/prompts", ["prompts"], "prompts"),
        (frontend_config_router, "", ["frontend-config"], "frontend_config"),
    ]


def _get_knowledge_routers() -> list:
    """Get knowledge base routers (Issue #560: extracted)."""
    return [
        (knowledge_router, "/knowledge_base", ["knowledge"], "knowledge"),
        (knowledge_search_router, "/knowledge_base", ["knowledge-search"], "knowledge_search"),
        (knowledge_tags_router, "/knowledge_base", ["knowledge-tags"], "knowledge_tags"),
        (knowledge_categories_router, "/knowledge_base", ["knowledge-categories"], "knowledge_categories"),
        (knowledge_collections_router, "/knowledge_base", ["knowledge-collections"], "knowledge_collections"),
        (knowledge_suggestions_router, "/knowledge_base", ["knowledge-suggestions"], "knowledge_suggestions"),
        (knowledge_metadata_router, "/knowledge_base", ["knowledge-metadata"], "knowledge_metadata"),
        (knowledge_population_router, "/knowledge_base", ["knowledge-population"], "knowledge_population"),
    ]


def _get_service_routers() -> list:
    """Get LLM, Redis, voice, and VNC routers (Issue #560: extracted, Issue #729: infrastructure removed)."""
    routers = [
        (llm_router, "/llm", ["llm"], "llm"),
        (redis_router, "/redis", ["redis"], "redis"),
        (voice_router, "/voice", ["voice"], "voice"),
        (wake_word_router, "/wake_word", ["wake_word", "voice"], "wake_word"),
        (vnc_router, "/vnc", ["vnc"], "vnc"),
        (vnc_proxy_router, "/vnc-proxy", ["vnc-proxy"], "vnc_proxy"),
        # Issue #729: infrastructure_hosts removed - now served by slm-server
    ]
    return routers


def _get_mcp_routers() -> list:
    """Get MCP bridge routers (Issue #560: extracted)."""
    return [
        (knowledge_mcp_router, "/knowledge", ["knowledge_mcp", "mcp"], "knowledge_mcp"),
        (vnc_mcp_router, "/vnc", ["vnc", "mcp"], "vnc_mcp"),
        (mcp_registry_router, "/mcp", ["mcp", "registry"], "mcp_registry"),
        (sequential_thinking_mcp_router, "/sequential_thinking", ["sequential_thinking_mcp", "mcp"], "sequential_thinking_mcp"),
        (structured_thinking_mcp_router, "/structured_thinking", ["structured_thinking_mcp", "mcp"], "structured_thinking_mcp"),
        (filesystem_mcp_router, "/filesystem", ["filesystem_mcp", "mcp"], "filesystem_mcp"),
        (browser_mcp_router, "/browser", ["browser_mcp", "mcp"], "browser_mcp"),
        (http_client_mcp_router, "/http_client", ["http_client_mcp", "mcp"], "http_client_mcp"),
        (database_mcp_router, "/database", ["database_mcp", "mcp"], "database_mcp"),
        (git_mcp_router, "/git", ["git_mcp", "mcp"], "git_mcp"),
        (prometheus_mcp_router, "/prometheus", ["prometheus_mcp", "mcp"], "prometheus_mcp"),
    ]


def _get_agent_routers() -> list:
    """Get agent and utility routers (Issue #560: extracted)."""
    return [
        (agent_router, "/agent", ["agent"], "agent"),
        (agent_config_router, "/agent_config", ["agent_config"], "agent_config"),
        (intelligent_agent_router, "/intelligent_agent", ["intelligent_agent"], "intelligent_agent"),
        (overseer_router, "/overseer", ["overseer", "agent"], "overseer"),
        (files_router, "/files", ["files"], "files"),
        (developer_router, "/developer", ["developer"], "developer"),
        (memory_router, "/memory", ["memory"], "memory"),
    ]


def load_core_routers():
    """
    Load and return core API routers (Issue #560: decomposed).

    Core routers provide essential functionality and should always be available.
    These routers are imported at module level to ensure they fail fast if missing.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              - router: FastAPI APIRouter instance
              - prefix: URL prefix for the router (e.g., "/system")
              - tags: List of OpenAPI tags for documentation
              - name: Identifier for logging/debugging
    """
    routers = []
    routers.extend(_get_system_routers())
    routers.extend(_get_knowledge_routers())
    routers.extend(_get_service_routers())
    routers.extend(_get_mcp_routers())
    routers.extend(_get_agent_routers())
    return routers
