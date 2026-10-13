# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Infrastructure modules allowed to import backend-only packages, each with its reason (#18288).

Data module for ``infra_scripts_no_backend_imports_18288_test.py``. Two kinds of entry:

``BACKEND_TOOLS``
    Audited: the module drives backend internals on purpose, and bootstraps ``autobot-backend`` plus
    the repository root onto its own path, so it runs from any directory with no PYTHONPATH. The guard
    imports each one in a clean interpreter to prove it.
``UNCLASSIFIED``
    Found by the class guard beyond the ten #18288 names, not yet audited. Frozen here so none can be
    added silently; each leaves by a recorded decision under #18289.

The test fails on an entry that no longer imports the backend, so this only shrinks.
"""

from __future__ import annotations

_I = "autobot-infrastructure/"
_P = _I + "shared/scripts/"

BACKEND_TOOLS: dict[str, str] = {
    _P + "analysis/test_service_registry.py": "backend tool: deliberately exercises utils.service_registry",
    _P + "analysis/debug_circuit_breaker.py": "backend tool: inspects the backend's circuit-breaker manager state",
    _P + "analysis/demo_secure_web_research.py": "backend tool: demonstrates the backend's secure web research",
    _P + "analysis/main.py": "backend tool: starts the backend app via app_factory",
    _P + "analysis/simple_kb_test.py": "backend tool: checks the backend's KnowledgeBase",
    _P + "analysis/test_autobot_identity.py": "backend tool: checks the backend's KnowledgeBase",
    _P + "analysis/test_bypass_classification.py": "backend tool: drives the backend's LLM failsafe agent",
    _P
    + "analysis/test_chat_debug.py": "backend tool: debugs the backend's classification agent and async chat workflow",
    _P + "analysis/test_chat_simple.py": "backend tool: runs a message through the backend's async chat workflow",
    _P + "analysis/test_failsafe_sequence.py": "backend tool: drives the backend's LLMInterface failsafe sequence",
    _P + "analysis/test_kb_documentation.py": "backend tool: checks the backend's KnowledgeBase documentation search",
    _P + "analysis/test_kb_search.py": "backend tool: drives the backend's ChatWorkflowManager and KnowledgeBase",
    _P + "analysis/test_llm_config.py": "backend tool: checks the backend's LLM configuration and LLMInterface",
    _P + "analysis/test_llm_direct.py": "backend tool: drives the backend's LLM failsafe and classification agents",
    _P + "analysis/test_npu_code_search.py": "backend tool: drives the backend's NPU code search agents",
    _P + "analysis/test_redis_connection.py": "backend tool: exercises the backend's utils.service_registry",
    _P + "analysis/test_research_dialogue.py": "backend tool: research dialogue via the async chat workflow",
    _P + "analysis/test_research_disabled.py": "backend tool: ChatWorkflowManager, research disabled",
    _P + "analysis/test_web_research_security.py": "backend tool: tests the backend's web research security components",
    _P + "analysis/npu_performance_measurement.py": "backend tool: benchmarks the NPU semantic search",
    _P + "verify_knowledge_consistency.py": "backend tool: verifies KnowledgeBase embedding consistency",
    _P
    + "apply_memory_optimizations.py": (
        "backend tool: drives utils.memory_optimization, its only importer; that module needs "
        "ssot_config and psutil, so it is no pure helper to move to autobot_shared"
    ),
    _P
    + "monitoring/monitoring_backends.py": (
        "backend tool: the launcher's performance and hardware backends, split from start_monitoring.py "
        "(#17906); imports utils.performance_monitor or utils.hardware_metrics when selected"
    ),
    _P
    + "monitoring/start_monitoring.py": (
        "backend tool: the one monitoring launcher (#17906); drives the backend's performance, "
        "hardware and GPU monitors"
    ),
    _P
    + "performance_dashboard.py": (
        "backend tool: renders with backend HTML helpers and drives monitoring_system, which "
        "imports the backend's config and constants"
    ),
    _P + "test_long_running_operations.py": "backend tool: demonstrates utils.long_running_operations_framework",
    _P + "test_phase5_cleanup.py": "backend tool: checks the backend's metrics collectors after the Phase 5 cleanup",
    _P
    + "validation_dashboard_generator.py": (
        "backend tool: reports on the backend's project state (project_state_tracker, "
        "phase_progression_manager); CI runs it in phase_validation.yml"
    ),
    _I
    + "autobot-backend/scripts/migrations/migrate_secrets_ownership.py": (
        "backend tool: re-encrypts stored secrets through the backend's encryption_service"
    ),
    _P
    + "automated_testing_procedure.py": (
        "backend tool: runs the backend app, config and file API through an automated test procedure"
    ),
    _P + "demo/demo_codebase_indexing.py": ("backend tool: demonstrates the backend's codebase indexing service"),
    _P
    + "migrations/migrate_config_users.py": (
        "backend tool: migrates configured users into the backend's user_management database"
    ),
    _P
    + "migrations/migrate_sessions_608.py": (
        "backend tool: migrates chat sessions through the backend's ChatHistoryManager and memory graph"
    ),
    _P + "profile_backend.py": ("backend tool: profiles the backend's app_factory startup"),
    _P + "profile_startup.py": ("backend tool: profiles the backend's startup sequence (app_factory)"),
    _P
    + "security/backfill_session_ownership.py": (
        "backend tool: backfills session ownership through the backend's SessionOwnershipValidator"
    ),
    _P + "security/mtls-migrate.py": ("backend tool: drives the backend's pki generator, configurator and distributor"),
    _P
    + "setup/knowledge/fresh_kb_setup.py": (
        "backend tool: resets and re-initialises the backend's KnowledgeBase (the top-level duplicate retired)"
    ),
    _P + "startup_timing_analysis.py": ("backend tool: times the backend's app_factory startup"),
    _P + "test_configuration.py": ("backend tool: checks the backend's configuration package"),
    _P + "test_llm_awareness.py": ("backend tool: checks the backend's LLM self-awareness and its middleware"),
    _P + "test_phase2_migration.py": ("backend tool: checks the backend's error boundaries and metrics collectors"),
    _P + "trace_backend.py": ("backend tool: traces the backend's app_factory startup"),
    _P + "utilities/manage_classification.py": ("backend tool: manages the backend's workflow classifier"),
    _P
    + "utilities/migrate_encryption.py": (
        "backend tool: migrates chat history through the backend's encryption_service"
    ),
    _P + "validate_timeout_config.py": ("backend tool: validates the backend's ConfigManager timeout settings"),
}

_UNCLASSIFIED_REASON = "not yet classified as shared, backend tool or dead: #18289"

UNCLASSIFIED: frozenset[str] = frozenset(
    {
        "autobot-infrastructure/shared/docker/ai-stack/ai_api_server.py",
        "autobot-infrastructure/shared/mcp/tools/knowledge-base-mcp/autobot_knowledge_mcp/embedded.py",
        "autobot-infrastructure/shared/scripts/direct_kb_populate.py",
        "autobot-infrastructure/shared/scripts/fix_kb_dimensions.py",
        "autobot-infrastructure/shared/scripts/identity_config_utility.py",
        "autobot-infrastructure/shared/scripts/kb_dimension_utility.py",
        "autobot-infrastructure/shared/scripts/populate_docs_knowledge.py",
        "autobot-infrastructure/shared/scripts/populate_kb_fixed.py",
        "autobot-infrastructure/shared/scripts/populate_knowledge_base.py",
        "autobot-infrastructure/shared/scripts/quick_populate_kb.py",
        "autobot-infrastructure/shared/scripts/reset_kb_dimensions.py",
        "autobot-infrastructure/shared/scripts/reset_knowledge_base.py",
        "autobot-infrastructure/shared/scripts/security/seed_enforcement_mode.py",
        "autobot-infrastructure/shared/scripts/sync_kb_docs.py",
        "autobot-infrastructure/shared/scripts/utilities/index_all_man_pages.py",
        "autobot-infrastructure/shared/scripts/utilities/ingest_man_pages.py",
        "autobot-infrastructure/shared/scripts/utilities/integrate_system_knowledge.py",
        "autobot-infrastructure/shared/scripts/utilities/manage_system_knowledge.py",
        "autobot-infrastructure/shared/scripts/utilities/migrate_redis_to_chromadb.py",
        "autobot-infrastructure/shared/scripts/utilities/quick_test_os_context.py",
        "autobot-infrastructure/shared/scripts/utilities/sync_documentation_kb.py",
        "autobot-infrastructure/shared/scripts/utilities/test-authentication-security.py",
        "autobot-infrastructure/shared/scripts/utilities/test_man_page_context.py",
        "autobot-infrastructure/shared/scripts/utilities/validate-security-config.py",
        "autobot-infrastructure/shared/scripts/utilities/validate_chat_knowledge.py",
        "autobot-infrastructure/shared/scripts/utilities/vectorize_existing_docs.py",
        "autobot-infrastructure/shared/scripts/utilities/verify_backend_config.py",
        "autobot-infrastructure/shared/scripts/utilities/verify_ssh_manager.py",
        "autobot-infrastructure/shared/scripts/validate_configuration.py",
        "autobot-infrastructure/shared/tests/conftest.py",
        "autobot-infrastructure/shared/tests/distributed/test_db_initialization.py",
        "autobot-infrastructure/shared/tests/fixtures/mocks.py",
        "autobot-infrastructure/shared/tests/integration/test_architecture_compliance.py",
    }
)

ALLOWLIST: dict[str, str] = {
    **{rel: _UNCLASSIFIED_REASON for rel in UNCLASSIFIED},
    **BACKEND_TOOLS,
}
