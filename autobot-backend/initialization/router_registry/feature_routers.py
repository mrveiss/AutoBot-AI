# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feature Router Loader

This module handles loading of feature-specific API routers.
These routers provide various application features like workflow automation,
web research, security, code analysis, and more.

Issue #281: Refactored from 716 lines of repetitive try/except blocks to
data-driven configuration pattern for improved maintainability.
"""

import importlib
import json
import os
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

# #6797: load-result registry — populated by load_feature_routers() so callers
# (health endpoint, dashboards) can introspect what loaded vs failed without
# scraping logs. Each entry: {"name": str, "module": str, "loaded": bool,
# "error": str | None}.
_LOAD_RESULTS: List[Dict[str, Any]] = []

# #6808: Redis key prefix and TTL for cross-worker aggregation.
# Each uvicorn worker publishes its results under its PID so the health
# endpoint can show a unified view regardless of which worker handles the poll.
_REDIS_KEY_PREFIX = "autobot:feature_routers:"
_REDIS_TTL_SECONDS = 600  # 10 min — survives rolling restarts


def _publish_load_results_to_redis(results: List[Dict[str, Any]]) -> None:
    """Best-effort: publish this worker's load results to Redis (#6808).

    Uses the PID as the worker discriminator so the health endpoint can
    aggregate across all workers with ``KEYS autobot:feature_routers:*``.
    Never raises — Redis unavailability must not block startup.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="main")
        if redis is None:
            return
        key = f"{_REDIS_KEY_PREFIX}{os.getpid()}"
        redis.set(key, json.dumps(results), ex=_REDIS_TTL_SECONDS)
    except Exception:
        logger.debug("Could not publish feature-router results to Redis (#6808)", exc_info=True)


def get_cross_worker_load_results() -> Dict[str, Any]:
    """Aggregate load results from all uvicorn workers via Redis (#6808).

    Returns a dict with:
      - ``workers``: mapping of PID → per-worker result list
      - ``aggregated``: union of all workers' results (by router name)
      - ``worker_count``: number of live workers seen
      - ``redis_available``: whether aggregation succeeded

    Falls back to the local ``_LOAD_RESULTS`` when Redis is unavailable.
    """
    try:
        from autobot_shared.redis_client import get_redis_client

        redis = get_redis_client(database="main")
        if redis is None:
            raise RuntimeError("Redis client unavailable")

        # Scan for all worker keys (KEYS is fine here — small keyspace, admin op)
        keys = redis.keys(f"{_REDIS_KEY_PREFIX}*")
        workers: Dict[str, List[Dict[str, Any]]] = {}
        for key in keys:
            pid = key.decode() if isinstance(key, bytes) else key
            pid = pid.removeprefix(_REDIS_KEY_PREFIX)
            raw = redis.get(f"{_REDIS_KEY_PREFIX}{pid}")
            if raw:
                workers[pid] = json.loads(raw)

        if not workers:
            # No Redis data yet — fall back to local (boot race window)
            return {
                "workers": {str(os.getpid()): _LOAD_RESULTS},
                "aggregated": _LOAD_RESULTS,
                "worker_count": 1,
                "redis_available": True,
                "note": "local-only: no other worker keys found in Redis yet",
            }

        # Build union: for each router name, collect all worker statuses
        by_name: Dict[str, Dict[str, Any]] = {}
        for pid, results in workers.items():
            for entry in results:
                name = entry["name"]
                if name not in by_name:
                    by_name[name] = dict(entry)
                    by_name[name]["worker_statuses"] = {}
                by_name[name]["worker_statuses"][pid] = {
                    "loaded": entry["loaded"],
                    "error": entry["error"],
                }
                # Mark as failed if any worker failed to load this router
                if not entry["loaded"]:
                    by_name[name]["loaded"] = False
                    by_name[name]["error"] = entry["error"]

        aggregated = sorted(by_name.values(), key=lambda r: r["name"])
        return {
            "workers": workers,
            "aggregated": aggregated,
            "worker_count": len(workers),
            "redis_available": True,
        }
    except Exception:
        logger.debug("Redis aggregation failed, falling back to local results (#6808)", exc_info=True)
        return {
            "workers": {str(os.getpid()): _LOAD_RESULTS},
            "aggregated": _LOAD_RESULTS,
            "worker_count": 1,
            "redis_available": False,
        }


# Issue #281: Router configurations as data instead of repetitive code blocks
# Format: (module_path, prefix, tags, name)
FEATURE_ROUTER_CONFIGS: List[Tuple[str, str, List[str], str]] = [
    # Core workflow and batch processing
    # Issue #6229: api.websockets and api.live_events promoted to core_routers
    ("api.workflow", "/workflow", ["workflow"], "workflow"),
    # Issue #1287: batch.py consolidated into batch_jobs.py
    (
        "api.batch_jobs",
        "/batch-jobs",
        ["batch-jobs", "management"],
        "batch_jobs",
    ),
    (
        "api.orchestration",
        "/orchestrator",
        ["orchestrator"],
        "orchestrator",
    ),
    # Issue #1285: Consolidated from api/workflow_automation.py to services/ version
    (
        "services.workflow_automation.routes",
        "/workflow-automation",
        ["workflow-automation"],
        "workflow_automation",
    ),
    # Issue #1280: Advanced workflow orchestrator (services/ version, replaces api/ prototype)
    (
        "services.advanced_workflow.routes",
        "/advanced-workflow",
        ["advanced-workflow"],
        "advanced_workflow",
    ),
    # Logging and configuration
    ("api.logs", "/logs", ["logs"], "logs"),
    (
        "api.log_forwarding",
        "/log-forwarding",
        ["log-forwarding"],
        "log_forwarding",
    ),
    ("api.secrets", "/secrets", ["secrets"], "secrets"),
    # Issue #2153: workflow-scoped encrypted credential storage
    (
        "api.workflow_secrets",
        "/workflow-secrets",
        ["workflow-secrets", "secrets"],
        "workflow_secrets",
    ),
    ("api.registry", "/registry", ["registry"], "registry"),
    # AI and embeddings
    ("api.embeddings", "/embeddings", ["embeddings"], "embeddings"),
    ("api.multimodal", "/multimodal", ["multimodal"], "multimodal"),
    (
        "api.llm_optimization",
        "/llm-optimization",
        ["llm-optimization"],
        "llm_optimization",
    ),
    ("api.llm_awareness", "/llm-awareness", ["llm-awareness"], "llm_awareness"),
    # Issue #4258: Dynamic endpoint capability discovery for LLM self-awareness
    (
        "api.self_capabilities",
        "",
        ["self-capabilities"],
        "self_capabilities",
    ),
    # Web research and browser automation
    (
        "api.research_browser",
        "/research-browser",
        ["research-browser"],
        "research_browser",
    ),
    ("api.playwright", "/playwright", ["playwright"], "playwright"),
    ("api.vision", "/vision", ["vision", "gui-automation"], "vision"),
    (
        "api.web_research_settings",
        "/web-research-settings",
        ["web-research-settings"],
        "web_research_settings",
    ),
    ("api.captcha", "", ["captcha", "web-research"], "captcha"),
    # State and project management
    (
        "api.state_tracking",
        "/state-tracking",
        ["state-tracking"],
        "state_tracking",
    ),
    ("api.project_state", "/project-state", ["project-state"], "project_state"),
    # Issue #3331: api.phase_management removed — its /phases prefix conflicted and its
    # scripts.phase_validation_system import never existed; replaced by api.phases below.
    # Issue #3331: /api/project/* and /api/phases/* endpoints for PhaseProgressionIndicator
    ("api.project", "/project", ["project"], "project"),
    ("api.phases", "/phases", ["phases"], "phases"),
    # Services and infrastructure
    ("api.services", "/services", ["services"], "services"),
    ("api.elevation", "/elevation", ["elevation"], "elevation"),
    ("api.hot_reload", "/hot-reload", ["hot-reload"], "hot_reload"),
    ("api.startup", "/startup", ["startup"], "startup"),
    # Enterprise and scheduling
    ("api.enterprise_features", "/enterprise", ["enterprise"], "enterprise"),
    ("api.scheduler", "/scheduler", ["scheduler"], "scheduler"),
    ("api.templates", "/templates", ["templates"], "templates"),
    # Security and sandbox
    ("api.sandbox", "/sandbox", ["sandbox"], "sandbox"),
    # GH#7409: Sandbox-scoped file CRUD surface
    ("api.sandbox_files", "/sandbox/files", ["sandbox", "files"], "sandbox_files"),
    ("api.security", "/security", ["security"], "security"),
    # SEC-2 Phase 3 (#6473): run-JWT refresh endpoint
    ("api.run_jwt_router", "", ["security", "run-jwt"], "run_jwt"),
    (
        "api.security_assessment",
        "",
        ["security-assessment"],
        "security_assessment",
    ),
    # Permission system v2 (Claude Code-style)
    ("api.permissions", "", ["permissions"], "permissions"),
    # Issue #2323: Workflow RBAC — moved from core_routers for graceful degradation
    ("api.workflow_permissions", "", ["workflow-permissions"], "workflow_permissions"),
    # Personality profiles (Issue #964)
    ("api.personality", "/personality", ["personality"], "personality"),
    # Self-improving tasks — adaptive task refinement and outcome learning (Issue #930)
    (
        "api.agents_self_improvement",
        "/agents",
        ["self-improvement", "agents"],
        "agents_self_improvement",
    ),
    # Code analysis and search
    ("api.analytics_code", "/analytics/code", ["analytics", "code-analysis"], "analytics_code"),
    ("api.code_search", "/code-search", ["code-search"], "code_search"),
    (
        "api.anti_pattern",
        "/anti-pattern",
        ["anti-pattern", "code-analysis"],
        "anti_pattern",
    ),
    (
        "api.code_intelligence",
        "/code-intelligence",
        ["code-intelligence", "code-analysis"],
        "code_intelligence",
    ),
    (
        "api.merge_conflict_resolution",
        "/code-intelligence/merge-conflicts",
        ["merge-conflicts", "code-intelligence", "git"],
        "merge_conflict_resolution",
    ),
    # Issue #3355: moved prefix from APIRouter() into registry (was "")
    (
        "api.natural_language_search",
        "/nl-search",
        ["natural-language-search", "code-search"],
        "natural_language_search",
    ),
    (
        "api.ide_integration",
        "/ide",
        ["ide", "code-intelligence", "real-time"],
        "ide_integration",
    ),
    (
        "routers.code_completion",
        "/code-completion",
        ["code-completion", "patterns", "ml"],
        "code_completion",
    ),
    (
        "routers.model_management",
        "/code-completion/model",
        ["ml-models", "training", "serving"],
        "model_management",
    ),
    (
        "routers.feedback",
        "/code-completion/feedback",
        ["feedback", "learning-loop"],
        "feedback",
    ),
    # Caching
    (
        "api.cache_management",
        "/cache",
        ["cache"],
        "cache_management",
    ),
    # Enhanced features
    (
        "api.enhanced_search",
        "/enhanced-search",
        ["enhanced-search"],
        "enhanced_search",
    ),
    (
        "api.enhanced_memory",
        "/enhanced-memory",
        ["enhanced-memory"],
        "enhanced_memory",
    ),
    (
        "api.development_speedup",
        "/dev-speedup",
        ["dev-speedup"],
        "development_speedup",
    ),
    (
        "api.advanced_control",
        "/advanced-control",
        ["advanced-control"],
        "advanced_control",
    ),
    # Issue #1407: Heartbeat system - scheduled agent wakeups and session persistence
    (
        "api.heartbeat",
        "/heartbeat",
        ["heartbeat", "agents"],
        "heartbeat",
    ),
    # Issue #6470: Budget policy CRUD API and hard-stop auto-pause
    (
        "api.budget_policies",
        "/api",
        ["budget-policies"],
        "budget_policies",
    ),
    # GH#6471: per-task git worktree workspace info
    (
        "api.task_workspace",
        "/api",
        ["task-workspace"],
        "task_workspace",
    ),
    # Long-running and validation
    # Moved back from core_routers — has _OPERATIONS_AVAILABLE graceful degradation (Issue #6306)
    (
        "api.long_running_operations",
        "/long-running",
        ["long-running-operations"],
        "long_running_operations",
    ),
    (
        "api.system_validation",
        "/system-validation",
        ["system-validation"],
        "system_validation",
    ),
    (
        "api.validation_dashboard",
        "/validation-dashboard",
        ["validation-dashboard"],
        "validation_dashboard",
    ),
    # Knowledge and conversation
    # Issue #7401: Unified scrape endpoint (Jina/BS4/Playwright, optional KB ingest)
    (
        "api.knowledge_scrape",
        "/knowledge",
        ["knowledge-scrape"],
        "knowledge_scrape",
    ),
    # Issue #7403: Domain URL enumeration via sitemap.xml or BFS crawl
    (
        "api.knowledge_site_map",
        "/knowledge",
        ["knowledge-site-map"],
        "knowledge_site_map",
    ),
    # Issue #7508: BFS web crawl with optional KB ingest
    (
        "api.knowledge_crawl",
        "/knowledge",
        ["knowledge-crawl"],
        "knowledge_crawl",
    ),
    # Issue #7405: Schema-driven structured data extraction from a URL via LLM
    (
        "api.knowledge_extract",
        "/knowledge",
        ["knowledge-extract"],
        "knowledge_extract",
    ),
    # Issue #1256: Observable Research Panel — live browser WS stream
    (
        "api.knowledge_research_ws",
        "",
        ["knowledge-research", "websockets"],
        "knowledge_research_ws",
    ),
    (
        "api.knowledge_test",
        "/knowledge-test",
        ["knowledge-test"],
        "knowledge_test",
    ),
    (
        "api.knowledge_maintenance",
        "/knowledge-maintenance",
        ["knowledge-maintenance"],
        "knowledge_maintenance",
    ),
    # Issue #1279: Fact-to-fact graph relations + hybrid search
    (
        "api.knowledge_relations",
        "/knowledge-relations",
        ["knowledge-relations"],
        "knowledge_relations",
    ),
    # NOTE (#4203): knowledge_search_aggregator, knowledge_ai_stack, knowledge_debug,
    # knowledge_boards, knowledge_vectorization removed from here — already registered
    # unconditionally in core_routers.py (_get_knowledge_routers). Duplicate registration
    # caused the same routes to appear twice in the OpenAPI schema.
    (
        "api.conversation_files",
        "/conversation-files",
        ["conversation-files"],
        "conversation_files",
    ),
    (
        "api.chat_knowledge",
        "/chat-knowledge",
        ["chat-knowledge"],
        "chat_knowledge",
    ),
    # Issue #3402: KB Librarian agent HTTP surface — registered
    (
        "api.kb_librarian",
        "/kb-librarian",
        ["kb-librarian", "knowledge"],
        "kb_librarian",
    ),
    # NPU and Redis
    ("api.npu_workers", "", ["npu-workers"], "npu_workers"),
    ("api.redis_service", "/redis-service", ["redis-service"], "redis_service"),
    # Issue #729: infrastructure_nodes removed - now served by slm-server
    # Fleet host list for HostSelector (SSH/VNC terminal in chat)
    (
        "api.infrastructure",
        "/infrastructure",
        ["infrastructure"],
        "infrastructure",
    ),
    # Graph and entity features
    (
        "api.entity_extraction",
        "/entities",
        ["entity-extraction"],
        "entity_extraction",
    ),
    ("api.graph_rag", "/graph-rag", ["graph-rag"], "graph_rag"),
    # AI Stack integration (Issue #708 consolidation from app_factory_enhanced)
    (
        "api.ai_stack_integration",
        "/ai-stack",
        ["ai-stack"],
        "ai_stack_integration",
    ),
    (
        "api.knowledge_rag",
        "/knowledge_base/rag",
        ["knowledge-rag"],
        "knowledge_rag",
    ),
    # Admin feature flags and access control
    (
        "api.feature_flags",
        "/admin",
        ["admin", "feature-flags"],
        "feature_flags",
    ),
    # Issue #6590: Virtual LLM API keys with per-key budgets
    (
        "api.llm_keys",
        "/llm-keys",
        ["llm-keys", "admin", "security"],
        "llm_keys",
    ),
    # Issue #4203: External tool integrations consolidated into integration_routers.py
    # Skills repo management, governance, and hub MUST be registered before the base
    # skills router so their static path prefixes take precedence over /{name} param.
    # Issue #4412: community skill hub
    ("api.skills_hub", "/skills/hub", ["skills-hub"], "skills-hub"),
    ("api.skills_repos", "/skills/repos", ["skills"], "skills-repos"),
    (
        "api.skills_governance",
        "/skills/governance",
        ["skills"],
        "skills-governance",
    ),
    # Skills system base (Issue #731) - registered AFTER sub-routers (see above)
    ("api.skills", "/skills", ["skills"], "skills"),
    # A2A (Agent2Agent) protocol (Issue #961)
    ("api.a2a", "/a2a", ["a2a"], "a2a"),
    # Knowledge graph pipeline (Issue #759)
    (
        "api.knowledge_graph_routes",
        "/knowledge-graph",
        ["knowledge-graph", "ecl-pipeline"],
        "knowledge_graph",
    ),
    # Natural language database queries - Vanna.ai integration (Issue #723)
    (
        "api.nl_database",
        "/nl-database",
        ["nl-database", "vanna", "natural-language-sql"],
        "nl_database",
    ),
    # Issue #1295: Saved analytics reports CRUD + run
    (
        "api.bi_export_endpoints",
        "/bi",
        ["bi-reports"],
        "bi_reports",
    ),
    # Issue #2597: AutoResearch experiment runner (Milestone 1 of #1440)
    (
        "services.autoresearch.routes",
        "/autoresearch",
        ["autoresearch"],
        "autoresearch",
    ),
    # Issue #2165: Workflow export/import/sharing
    (
        "api.workflow_export",
        "/workflow-export",
        ["workflow-export"],
        "workflow_export",
    ),
    # Issue #2139: Event-driven trigger system for workflows
    (
        "api.triggers",
        "",
        ["triggers", "workflow"],
        "triggers",
    ),
    # Issue #1808: Conversation export and import
    (
        "api.conversation_export",
        "/conversations",
        ["conversation-export"],
        "conversation_export",
    ),
    # Issue #3407: SLM Docker deployment bridge
    (
        "api.slm.deployments",
        "",
        ["slm-deployments"],
        "slm_deployments",
    ),
    # Issue #3245: Persistent editable AI output documents
    (
        "api.documents",
        "",
        ["ai-documents"],
        "ai_documents",
    ),
    # Issue #4342: Error resilience monitoring endpoints (circuit breakers, error budgets)
    # Router defines prefix="/api/resilience" internally — use "" here to avoid double-prefix
    (
        "api.error_resilience",
        "",
        ["resilience", "monitoring"],
        "error_resilience",
    ),
    # NOTE (#4203): user_management and plugin_manager removed from here — already registered
    # unconditionally in core_routers.py. Duplicate registration caused routes to appear twice.
    # Issue #1803: Plugin and agent marketplace — community catalog
    ("api.marketplace", "/marketplace", ["marketplace", "plugins"], "marketplace"),
    # Issue #6481: User-extensible marketplace sources (custom marketplaces)
    # #6523: prefix moved off `/plugins` (was shadowed by plugin_manager's
    # `/plugins/{plugin_name}` wildcard). Routes now under `/marketplace-sources`.
    ("api.marketplace_sources", "/marketplace-sources", ["marketplace", "plugins"], "marketplace_sources"),
    # Issue #5070: verbatim conversational-memory lane
    ("api.verbatim_memory", "/verbatim-memory", ["memory"], "verbatim_memory"),
    # Issue #5071: per-agent diary with background append and runtime discovery
    ("api.agent_diary", "/agent-diary", ["agents"], "agent_diary"),
    # Partially wired or legacy feature routers
    ("api.chat_sessions", "", ["chat-sessions"], "chat_sessions"),
    # Issue #5061: First-run onboarding presets + doctor
    ("api.onboarding", "/onboarding", ["onboarding"], "onboarding"),
    # NOTE (#4203): api.diagnostics removed — already registered in monitoring_routers.py
    # at prefix "" (routes define their own /diagnostics path prefix internally).
    (
        "api.presence_ws",
        "",
        ["collaboration", "websocket", "presence"],
        "presence_ws",
    ),
    # GH#8251: LLC (Lean Lifecycle Controller) module skeleton
    ("llc.api", "", ["llc"], "llc"),
    # GH#7342: Backend SDP proxy for OpenAI Realtime WebRTC
    (
        "api.realtime_session",
        "/voice/realtime",
        ["voice", "realtime", "webrtc"],
        "realtime_session",
    ),
]


def _load_single_router(module_path: str, prefix: str, tags: List[str], name: str) -> Tuple | None:
    """
    Load a single router with graceful fallback.

    Issue #281: Extracted helper for loading individual routers to eliminate
    repetitive try/except blocks and enable data-driven router loading.

    #6797: appends a structured result entry to ``_LOAD_RESULTS`` so callers
    can introspect load status without scraping logs.

    Args:
        module_path: Full Python module path (e.g., 'backend.api.workflow')
        prefix: URL prefix for the router (e.g., '/workflow')
        tags: List of OpenAPI tags for the router
        name: Human-readable name for logging

    Returns:
        Tuple of (router, prefix, tags, name) if successful, None otherwise
    """
    try:
        module = importlib.import_module(module_path)
        router = getattr(module, "router")
        logger.info("✅ Optional router loaded: %s", name)
        _LOAD_RESULTS.append({"name": name, "module": module_path, "loaded": True, "error": None})
        return (router, prefix, tags, name)
    except ImportError as e:
        logger.warning("⚠️ Optional router not available: %s - %s", name, e)
        _LOAD_RESULTS.append(
            {
                "name": name,
                "module": module_path,
                "loaded": False,
                "error": f"ImportError: {e}",
            }
        )
        return None
    except AttributeError as e:
        logger.warning("⚠️ Router not found in module %s: %s - %s", module_path, name, e)
        _LOAD_RESULTS.append(
            {
                "name": name,
                "module": module_path,
                "loaded": False,
                "error": f"AttributeError: {e}",
            }
        )
        return None


def get_feature_router_load_results() -> List[Dict[str, Any]]:
    """Return the current load-results registry (#6797).

    Used by the /api/health/feature-routers endpoint and any operator tooling
    that wants to surface partial-boot state without scraping logs. Returns
    a copy so callers can mutate freely.
    """
    return list(_LOAD_RESULTS)


def load_feature_routers() -> List[Tuple]:
    """
    Dynamically load feature API routers with graceful fallback.

    Issue #281: Refactored to use data-driven configuration pattern.
    Original implementation had 53 repetitive try/except blocks (~716 lines).
    Now uses FEATURE_ROUTER_CONFIGS list and _load_single_router helper.

    #6797: When fewer routers loaded than configured, escalate the summary log
    to ERROR (was always INFO) so the partial-boot state is loud at deploy
    time. Optional strict mode via ``AUTOBOT_FEATURE_ROUTERS_STRICT=1`` raises
    instead of warning, for production deploys that want hard guarantees.

    Returns:
        list: List of tuples in format (router, prefix, tags, name)
              Only includes routers that successfully imported.
    """
    # Reset results — supports test environments that load_feature_routers()
    # multiple times in a single process.
    _LOAD_RESULTS.clear()

    optional_routers = []

    for module_path, prefix, tags, name in FEATURE_ROUTER_CONFIGS:
        result = _load_single_router(module_path, prefix, tags, name)
        if result:
            optional_routers.append(result)

    loaded = len(optional_routers)
    expected = len(FEATURE_ROUTER_CONFIGS)
    if loaded < expected:
        # #6797: escalate from INFO so partial-boot state is visible.
        failed = [r for r in _LOAD_RESULTS if not r["loaded"]]
        logger.error(
            "📊 Loaded %s/%s feature routers — %s FAILED: %s",
            loaded,
            expected,
            len(failed),
            ", ".join(r["name"] for r in failed),
        )
        if config.misc.feature_routers_strict.lower() in {"1", "true", "yes"}:
            raise RuntimeError(
                f"AUTOBOT_FEATURE_ROUTERS_STRICT=1 — {len(failed)} feature router(s) "
                f"failed to load: {', '.join(r['name'] for r in failed)}"
            )
    else:
        logger.info("📊 Loaded %s/%s feature routers", loaded, expected)
    # #6808: publish this worker's results to Redis so the health endpoint can
    # aggregate across all workers instead of returning a per-worker snapshot.
    _publish_load_results_to_redis(_LOAD_RESULTS)
    return optional_routers
