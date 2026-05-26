# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Core Router Loader

This module handles loading of core API routers that are essential for
basic AutoBot functionality. These routers should always be available
and are imported at module level to fail fast if missing.
"""

import api.pricing_health  # noqa: F401 — registers KnownProbes.PRICING probe (GH#6480)

# Core router imports - these are required for basic functionality
from api.adapters import router as adapters_router  # Issue #1403
from api.admin_event_logs import router as admin_event_logs_router  # Issue #4461
from api.admin_pricing import router as admin_pricing_router  # GH#6480
from api.admin_schedulers import router as admin_schedulers_router  # GH#6594
from api.agent import router as agent_router
from api.agent_config import router as agent_config_router
from api.agent_org import router as agent_org_router  # #1405
from api.approval_gates import router as approval_gates_router  # #1402
from api.audit import router as audit_router
from api.auth import router as auth_router
from api.browser_mcp import router as browser_mcp_router
from api.canvas import router as canvas_router  # MVA-359
from api.chat import router as chat_router
from api.chat_compare import router as chat_compare_router  # Issue #4414
from api.chat_presets import router as chat_presets_router  # GH#8595
from api.collaboration import router as collaboration_router
from api.config_revisions import router as config_revisions_router  # #1404
from api.data_storage import router as data_storage_router
from api.database_mcp import router as database_mcp_router
from api.developer import router as developer_router
from api.files import router as files_router
from api.filesystem_mcp import router as filesystem_mcp_router
from api.frontend_config import router as frontend_config_router
from api.git_mcp import router as git_mcp_router
from api.http_client_mcp import router as http_client_mcp_router
from api.intelligent_agent import router as intelligent_agent_router
from api.knowledge import router as knowledge_router
from api.knowledge_ai_stack import router as knowledge_ai_stack_router
from api.knowledge_audit import router as knowledge_audit_router
from api.knowledge_boards import router as knowledge_boards_router
from api.knowledge_categories import router as knowledge_categories_router
from api.knowledge_cognition import router as knowledge_cognition_router
from api.knowledge_collaboration import router as knowledge_collaboration_router
from api.knowledge_collections import router as knowledge_collections_router
from api.knowledge_connectors import router as knowledge_connectors_router
from api.knowledge_debug import router as knowledge_debug_router
from api.knowledge_grounding import router as knowledge_grounding_router
from api.knowledge_mcp import router as knowledge_mcp_router
from api.knowledge_metadata import router as knowledge_metadata_router
from api.knowledge_organization import router as knowledge_organization_router
from api.knowledge_ownership import router as knowledge_ownership_router
from api.knowledge_population import router as knowledge_population_router
from api.knowledge_rag_feedback import router as knowledge_rag_feedback_router
from api.knowledge_search import router as knowledge_search_router
from api.knowledge_search_aggregator import router as knowledge_search_aggregator_router
from api.knowledge_search_scoped import router as knowledge_search_scoped_router
from api.knowledge_suggestions import router as knowledge_suggestions_router
from api.knowledge_sync_queue import router as knowledge_sync_queue_router  # Issue #4453
from api.knowledge_tags import router as knowledge_tags_router
from api.knowledge_vectorization import router as knowledge_vectorization_router
from api.knowledge_verification import router as knowledge_verification_router
from api.live_events import router as live_events_router  # Issue #6229
from api.llm import router as llm_router
from api.llm_providers import router as llm_providers_router
from api.manual_mcp import router as manual_mcp_router
from api.mcp_registry import router as mcp_registry_router
from api.memory import router as memory_router
from api.models import router as models_router
from api.overseer_handlers import router as overseer_router
from api.process_management import router as process_management_router  # Issue #1406
from api.prometheus_mcp import router as prometheus_mcp_router
from api.prompts import router as prompts_router
from api.redis import router as redis_router
from api.redis_mcp import router as redis_mcp_router  # Issue #2511
from api.sequential_thinking_mcp import router as sequential_thinking_mcp_router
from api.service_messages import router as service_messages_router
from api.settings import router as settings_router
from api.structured_thinking_mcp import router as structured_thinking_mcp_router
from api.system import router as system_router
from api.usage import router as usage_router  # Issue #1807
from api.user_management.router import router as user_management_router  # Issue #1801
from api.vnc_manager import router as vnc_router
from api.vnc_mcp import router as vnc_mcp_router
from api.vnc_proxy import router as vnc_proxy_router
from api.voice import realtime_router as voice_realtime_router
from api.voice import router as voice_router
from api.voice_stream import router as voice_stream_router
from api.wake_word import router as wake_word_router
from api.websockets import router as websockets_router  # Issue #6229
from plugin_manager import router as plugin_manager_router
from services.knowledge_sync_service import router as knowledge_sync_router

# Issue #729: infrastructure_hosts removed - now served by slm-server


def _get_system_routers() -> list:
    """Get system and settings routers (Issue #560: extracted, #1281: audit, #4461: event-logs)."""
    return [
        (admin_event_logs_router, "", ["admin", "compliance"], "admin_event_logs"),  # Issue #4461
        (admin_pricing_router, "", ["admin", "pricing"], "admin_pricing"),  # GH#6480
        (admin_schedulers_router, "", ["admin", "schedulers"], "admin_schedulers"),  # GH#6594
        (audit_router, "", ["audit"], "audit"),
        (auth_router, "/auth", ["auth"], "auth"),
        (service_messages_router, "", ["service-messages"], "service_messages"),
        (chat_router, "", ["chat"], "chat"),
        (chat_compare_router, "", ["chat", "compare"], "chat_compare"),  # Issue #4414
        (chat_presets_router, "", ["chat"], "chat_presets"),  # GH#8595
        (collaboration_router, "", ["collaboration"], "collaboration"),
        (system_router, "/system", ["system"], "system"),
        (settings_router, "/settings", ["settings"], "settings"),
        (usage_router, "/usage", ["usage", "analytics"], "usage"),  # Issue #1807
        (user_management_router, "", ["user-management"], "user_management"),  # Issue #1801
        (data_storage_router, "", ["data-storage"], "data_storage"),
        (prompts_router, "/prompts", ["prompts"], "prompts"),
        (frontend_config_router, "", ["frontend-config"], "frontend_config"),
    ]


def _get_core_knowledge_routers() -> list:
    """Get core knowledge base routers.

    Helper for _get_knowledge_routers() (Issue #679).
    """
    return [
        (knowledge_router, "/knowledge_base", ["knowledge"], "knowledge"),
        (knowledge_audit_router, "", ["knowledge-audit"], "knowledge_audit"),
        (
            knowledge_search_router,
            "/knowledge_base",
            ["knowledge-search"],
            "knowledge_search",
        ),
        (
            knowledge_search_scoped_router,
            "",
            ["knowledge-search-scoped"],
            "knowledge_search_scoped",
        ),
        (
            knowledge_verification_router,
            "/knowledge_base",
            ["knowledge-verification"],
            "knowledge_verification",
        ),
        (
            knowledge_rag_feedback_router,
            "/knowledge_base",
            ["knowledge-rag-feedback"],
            "knowledge_rag_feedback",
        ),
        (
            knowledge_cognition_router,
            "/knowledge",
            ["knowledge-cognition"],
            "knowledge_cognition",
        ),
    ]


def _get_knowledge_organization_routers() -> list:
    """Get knowledge organization and metadata routers.

    Helper for _get_knowledge_routers() (Issue #679).
    """
    return [
        (
            knowledge_tags_router,
            "/knowledge_base",
            ["knowledge-tags"],
            "knowledge_tags",
        ),
        (
            knowledge_categories_router,
            "/knowledge_base",
            ["knowledge-categories"],
            "knowledge_categories",
        ),
        (
            knowledge_collections_router,
            "/knowledge_base",
            ["knowledge-collections"],
            "knowledge_collections",
        ),
        (
            knowledge_suggestions_router,
            "/knowledge_base",
            ["knowledge-suggestions"],
            "knowledge_suggestions",
        ),
        (
            knowledge_metadata_router,
            "/knowledge_base",
            ["knowledge-metadata"],
            "knowledge_metadata",
        ),
        (
            knowledge_connectors_router,
            "",
            ["knowledge-connectors"],
            "knowledge_connectors",
        ),
        (
            knowledge_population_router,
            "/knowledge_base",
            ["knowledge-population"],
            "knowledge_population",
        ),
    ]


def _get_knowledge_collaboration_routers() -> list:
    """Get knowledge collaboration routers (Issue #688, #679, #1284: sync).

    Helper for _get_knowledge_routers() (Issue #679).
    """
    return [
        (
            knowledge_ownership_router,
            "/knowledge_base",
            ["knowledge-ownership"],
            "knowledge_ownership",
        ),
        (
            knowledge_collaboration_router,
            "",
            ["knowledge-collaboration"],
            "knowledge_collaboration",
        ),
        (
            knowledge_organization_router,
            "",
            ["knowledge-organization"],
            "knowledge_organization",
        ),
        (
            knowledge_sync_router,
            "",
            ["knowledge-sync"],
            "knowledge_sync",
        ),
    ]


def _get_knowledge_feature_routers() -> list:
    """Get additional knowledge feature routers."""
    return [
        (
            knowledge_ai_stack_router,
            "/knowledge_base",
            ["knowledge-enhanced", "knowledge-ai"],
            "knowledge_ai_stack",
        ),
        (
            knowledge_boards_router,
            "/knowledge_base",
            ["knowledge-boards"],
            "knowledge_boards",
        ),
        (
            knowledge_debug_router,
            "/knowledge_base",
            ["knowledge-debug"],
            "knowledge_debug",
        ),
        (
            knowledge_grounding_router,
            "/knowledge_base",
            ["knowledge-grounding"],
            "knowledge_grounding",
        ),
        (
            knowledge_search_aggregator_router,
            "/knowledge_base",
            ["knowledge-unified", "knowledge-search"],
            "knowledge_search_aggregator",
        ),
        (
            knowledge_vectorization_router,
            "/knowledge_base",
            ["knowledge-vectorization"],
            "knowledge_vectorization",
        ),
        # Issue #4453: document sync queue admin endpoints
        (
            knowledge_sync_queue_router,
            "",
            ["knowledge-sync-queue"],
            "knowledge_sync_queue",
        ),
    ]


def _get_knowledge_routers() -> list:
    """Get knowledge base routers (Issue #560: extracted, #688: ownership, #679: full collaboration)."""
    return (
        _get_core_knowledge_routers()
        + _get_knowledge_organization_routers()
        + _get_knowledge_collaboration_routers()
        + _get_knowledge_feature_routers()
    )


def _get_service_routers() -> list:
    """Get LLM, Redis, voice, and VNC routers (#560: extracted, #729: infra removed)."""
    routers = [
        (llm_router, "/llm", ["llm"], "llm"),
        (llm_providers_router, "/llm", ["llm", "providers"], "llm_providers"),
        (models_router, "/models", ["models"], "models"),
        (adapters_router, "/adapters", ["adapters"], "adapters"),
        (redis_router, "/redis", ["redis"], "redis"),
        (voice_realtime_router, "/voice", ["voice"], "voice_realtime"),
        (voice_router, "/voice", ["voice"], "voice"),
        (voice_stream_router, "/voice", ["voice", "websocket"], "voice_stream"),
        (wake_word_router, "/wake_word", ["wake_word", "voice"], "wake_word"),
        (websockets_router, "", ["websockets"], "websockets"),  # Issue #6229
        (live_events_router, "", ["live-events"], "live_events"),  # Issue #6229
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
        (
            sequential_thinking_mcp_router,
            "/sequential_thinking",
            ["sequential_thinking_mcp", "mcp"],
            "sequential_thinking_mcp",
        ),
        (
            structured_thinking_mcp_router,
            "/structured_thinking",
            ["structured_thinking_mcp", "mcp"],
            "structured_thinking_mcp",
        ),
        (
            filesystem_mcp_router,
            "/filesystem",
            ["filesystem_mcp", "mcp"],
            "filesystem_mcp",
        ),
        (browser_mcp_router, "/browser", ["browser_mcp", "mcp"], "browser_mcp"),
        (
            http_client_mcp_router,
            "/http_client",
            ["http_client_mcp", "mcp"],
            "http_client_mcp",
        ),
        (database_mcp_router, "/database", ["database_mcp", "mcp"], "database_mcp"),
        (git_mcp_router, "/git", ["git_mcp", "mcp"], "git_mcp"),
        (
            prometheus_mcp_router,
            "/prometheus",
            ["prometheus_mcp", "mcp"],
            "prometheus_mcp",
        ),
        (redis_mcp_router, "/redis", ["redis_mcp", "mcp"], "redis_mcp"),  # Issue #2511
        (manual_mcp_router, "/manual", ["manual_mcp", "mcp"], "manual_mcp"),  # Issue #4256
    ]


def _get_agent_routers() -> list:
    """Get agent and utility routers (Issue #560: extracted)."""
    return [
        (agent_router, "/agent", ["agent"], "agent"),
        (approval_gates_router, "", ["approval-gates"], "approval_gates"),
        (config_revisions_router, "", ["config-revisions"], "config_revisions"),
        (agent_config_router, "/agent_config", ["agent_config"], "agent_config"),
        (
            intelligent_agent_router,
            "/intelligent_agent",
            ["intelligent_agent"],
            "intelligent_agent",
        ),
        (overseer_router, "/overseer", ["overseer", "agent"], "overseer"),
        (agent_org_router, "/agents", ["agent-org"], "agent_org"),
        (files_router, "/files", ["files"], "files"),
        (developer_router, "/developer", ["developer"], "developer"),
        (memory_router, "/memory", ["memory"], "memory"),
        (
            process_management_router,
            "",
            ["process-management"],
            "process_management",
        ),
    ]


def _get_plugin_routers() -> list:
    """Get plugin management routers (Issue #730).

    plugin_manager.py routes already include /plugins in their paths,
    so registration prefix must be empty to avoid double-prefix (#1105).
    """
    return [
        (plugin_manager_router, "", ["plugins"], "plugin_manager"),
    ]


def _get_canvas_routers() -> list:
    """Canvas routers (MVA-359)."""
    return [
        (canvas_router, "", ["canvas"], "canvas"),
    ]


def load_core_routers():
    """
    Load and return core API routers (Issue #560: decomposed, #730: plugins).

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
    routers.extend(_get_plugin_routers())
    routers.extend(_get_canvas_routers())
    return routers
