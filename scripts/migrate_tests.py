#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test colocation migration script for Issue #734.

Moves test files from infrastructure/shared/tests/ to sit next to their
source modules. Renames test_X.py -> X_test.py and fixes imports.

Usage:
    python scripts/migrate_tests.py --dry-run    # Preview changes
    python scripts/migrate_tests.py              # Execute migration
"""

import argparse
import logging
import re
import subprocess
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent

# Mapping: test filename (without test_ prefix and .py suffix) -> target directory
# relative to PROJECT_ROOT. The test will be placed in target_dir/{name}_test.py
UNIT_TEST_MAPPINGS = {
    # Direct name matches -> autobot-user-backend root
    "advanced_rag_optimizer": "autobot-user-backend",
    "chat_intent_detector": "autobot-user-backend",
    "circuit_breaker": "autobot-user-backend",
    "encryption_service": "autobot-user-backend",
    "slash_command_handler": "autobot-user-backend",
    "worker_node": "autobot-user-backend",
    # code_intelligence/
    "anti_pattern_detector": "autobot-user-backend/code_intelligence",
    "bug_predictor": "autobot-user-backend/code_intelligence",
    "code_fingerprinting": "autobot-user-backend/code_intelligence",
    "code_review_engine": "autobot-user-backend/code_intelligence",
    "conversation_flow_analyzer": "autobot-user-backend/code_intelligence",
    "llm_code_generator": "autobot-user-backend/code_intelligence",
    "llm_pattern_analyzer": "autobot-user-backend/code_intelligence",
    "log_pattern_miner": "autobot-user-backend/code_intelligence",
    "performance_analyzer": "autobot-user-backend/code_intelligence",
    "precommit_analyzer": "autobot-user-backend/code_intelligence",
    "redis_optimizer": "autobot-user-backend/code_intelligence",
    "security_analyzer": "autobot-user-backend/code_intelligence",
    # services/
    "chat_knowledge_service": "autobot-user-backend/services",
    "graph_rag_service": "autobot-user-backend/services",
    "redis_service_manager": "autobot-user-backend/services",
    "security_workflow_manager": "autobot-user-backend/services",
    "terminal_completion_service": "autobot-user-backend/services",
    "terminal_history_service": "autobot-user-backend/services",
    # knowledge/
    "embedding_cache": "autobot-user-backend/knowledge",
    "search_quality": "autobot-user-backend/knowledge",
    # api/
    "knowledge_categories": "autobot-user-backend/api",
    "knowledge_vectorization": "autobot-user-backend/api",
    # utils/
    "config_manager": "autobot-user-backend/utils",
    "operation_timeout_integration": "autobot-user-backend/utils",
    # security/
    "input_validator": "autobot-user-backend/security",
    # agents/
    "graph_entity_extractor": "autobot-user-backend/agents",
    # autobot-shared/
    "error_boundaries": "autobot-shared",
    "ssot_config": "autobot-shared",
    # --- Tests mapped by import analysis (no direct name match) ---
    # src.extensions.base
    "extension_hooks": "autobot-user-backend/extensions",
    # src.monitoring.prometheus_metrics
    "redis_prometheus_metrics": "autobot-user-backend/monitoring",
    # src.utils.errors
    "repairable_exception": "autobot-user-backend/utils",
    # src.code_intelligence.shared.ast_cache
    "shared_caches": "autobot-user-backend/code_intelligence/shared",
    # src.chat_workflow.models
    "streaming_message": "autobot-user-backend/chat_workflow",
    # src.agents.hierarchical_agent
    "subordinate_delegation": "autobot-user-backend/agents",
    # src.llm_interface_pkg.tiered_routing
    "tiered_routing": "autobot-user-backend/llm_interface_pkg",
    # src.config
    "timeout_configuration": "autobot-user-backend/config",
    # backend.api.codebase_analytics.*
    "call_graph_resolution": "autobot-user-backend/api/codebase_analytics",
    "codebase_stats_endpoint": "autobot-user-backend/api/codebase_analytics",
    "parallel_processing": "autobot-user-backend/api/codebase_analytics",
    "technical_debt_detection": "autobot-user-backend/api/codebase_analytics",
    # backend.type_defs.common
    "chat_merge_messages": "autobot-user-backend/type_defs",
    # backend.dependencies
    "dependency_injection": "autobot-user-backend",
    # backend.services.*
    "rag_integration": "autobot-user-backend/services",
    "wake_word_detection": "autobot-user-backend/services",
    # Self-contained/general tests -> component root
    "agent_optimizer": "autobot-user-backend/agents",
    "api_endpoint_migrations": "autobot-user-backend/api",
    "code_semantic_search": "autobot-user-backend/knowledge",
    "config_registry": "autobot-user-backend/config",
    "conversation_file_manager_init": "autobot-user-backend",
    "escape_character_handling": "autobot-user-backend/utils",
    "file_locking": "autobot-user-backend/utils",
    "hallucination_prevention": "autobot-user-backend/knowledge",
    "helpers_reorganization": "autobot-user-backend/utils",
    "knowledge_base_async": "autobot-user-backend/knowledge",
    "mcp_cache": "autobot-user-backend/mcp",
    "persist_conversation_dedup": "autobot-user-backend/chat_history",
    "respond_tool": "autobot-user-backend/tools",
    "stats_counter_parsing": "autobot-user-backend/utils",
    "thread_safety": "autobot-user-backend/utils",
    "workflow_plan_approval": "autobot-user-backend/chat_workflow",
    # --- Root-level test mappings (infrastructure/shared/tests/test_*.py) ---
    # Direct name matches
    "api_responses": "autobot-user-backend/utils",
    "async_initializable": "autobot-user-backend/utils",
    "enhanced_security_layer": "autobot-user-backend",
    "hardware_metrics": "autobot-user-backend/utils",
    "knowledge_manager": "autobot-user-backend/agents",
    "lazy_singleton": "autobot-user-backend/utils",
    "monitoring_alerts": "autobot-user-backend/utils",
    "retry_mechanism": "autobot-user-backend",
    "secure_command_executor": "autobot-user-backend",
    "secure_terminal_websocket": "autobot-user-backend/api",
    "system_integration": "autobot-user-backend",
    "system_validation": "autobot-user-backend/api",
    "terminal_input_handler": "autobot-user-backend/utils",
    "tool_discovery": "autobot-user-backend",
    "validators": "autobot-user-backend/utils",
    "error_catalog": "autobot-user-backend/utils",
    "error_metrics": "autobot-user-backend/utils",
    # Import-analysis mapped
    "atomic_facts_extraction": "autobot-user-backend/agents",
    "computer_vision_refactoring": "autobot-user-backend/computer_vision",
    "entity_resolution": "autobot-user-backend/utils",
    "gpu_performance": "autobot-user-backend/utils",
    "intent_classification": "autobot-user-backend",
    "kb_optimization": "autobot-user-backend/knowledge",
    "llm_interface_core": "autobot-user-backend/llm_interface_pkg",
    "memory_package": "autobot-user-backend",
    "model_optimizer_refactoring": "autobot-user-backend/utils",
    "phase7_enhanced_memory": "autobot-user-backend",
    "phase8_control_panel": "autobot-user-backend",
    "phase9_multimodal_ai": "autobot-user-backend/computer_vision",
    "queue_integration": "autobot-user-backend/services",
    "redis_consolidation": "autobot-user-backend/utils",
    "redis_thread_safety": "autobot-user-backend/utils",
    "security_api": "autobot-user-backend/api",
    "security_integration": "autobot-user-backend/security",
    "semantic_chunking": "autobot-user-backend/utils",
    "settings_debug": "autobot-user-backend/services",
    "temporal_invalidation": "autobot-user-backend/services",
    # Self-contained/general tests
    "cache_consolidation_p4": "autobot-user-backend/cache",
    "comprehensive_system_validation": "autobot-user-backend",
    "concurrency_safety": "autobot-user-backend/utils",
    "config_consolidation_p2": "autobot-user-backend/config",
    "config": "autobot-user-backend/config",
    "file_upload_comprehensive": "autobot-user-backend/api",
    "gpu_kb_integration": "autobot-user-backend/knowledge",
    "minimal_backend": "autobot-user-backend",
    "monitoring_and_alerts": "autobot-user-backend/monitoring",
    "multi_agent_workflow_validation": "autobot-user-backend/agents",
    "session_validation": "autobot-user-backend/security",
    "simple_optimization": "autobot-user-backend/utils",
}

# Additional mappings for unit/ subdirectories
UNIT_SUBDIR_MAPPINGS = {
    # llm_interface_pkg/ subdir
    "llm_interface_pkg": "autobot-user-backend/llm_interface_pkg",
    # monitoring/ subdir
    "monitoring": "autobot-user-backend/monitoring",
}

# Import replacements: old prefix -> new prefix
IMPORT_REPLACEMENTS = [
    # src.X -> X (remove src. prefix)
    (r"from src\.", "from "),
    (r"import src\.", "import "),
    # backend.X -> X (remove backend. prefix)
    (r"from backend\.", "from "),
    (r"import backend\.", "import "),
    # tests.mock_llm_interface -> mock references (comment out broken imports)
    (
        r"from tests\.mock_llm_interface",
        "# TODO: fix import - from tests.mock_llm_interface",
    ),
]


def fix_imports(content: str) -> str:
    """Fix import statements in test file content."""
    for pattern, replacement in IMPORT_REPLACEMENTS:
        content = re.sub(pattern, replacement, content)
    return content


def get_new_filename(old_name: str) -> str:
    """Convert test_X.py to X_test.py naming convention."""
    if old_name.startswith("test_"):
        base = old_name[5:]  # Remove test_ prefix
        return base.replace(".py", "_test.py")
    return old_name


def migrate_file(
    src_path: Path,
    dest_dir: Path,
    dry_run: bool = True,
) -> tuple[str, str]:
    """Migrate a single test file.

    Returns (old_path, new_path) tuple.
    """
    old_name = src_path.name
    new_name = get_new_filename(old_name)
    dest_path = dest_dir / new_name

    if dry_run:
        return str(src_path.relative_to(PROJECT_ROOT)), str(
            dest_path.relative_to(PROJECT_ROOT)
        )

    # Ensure dest directory exists
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Read and fix imports
    content = src_path.read_text(encoding="utf-8")
    fixed_content = fix_imports(content)

    # Write to new location
    dest_path.write_text(fixed_content, encoding="utf-8")

    # Git add new file and remove old
    subprocess.run(
        ["git", "add", str(dest_path)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "rm", "--quiet", str(src_path)],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
    )

    return str(src_path.relative_to(PROJECT_ROOT)), str(
        dest_path.relative_to(PROJECT_ROOT)
    )


def migrate_unit_tests(dry_run: bool = True) -> list[tuple[str, str]]:
    """Migrate unit tests from infrastructure/shared/tests/unit/."""
    results = []
    unit_dir = PROJECT_ROOT / "infrastructure" / "shared" / "tests" / "unit"

    if not unit_dir.exists():
        logger.info(f"  Unit test dir not found: {unit_dir}")
        return results

    for test_file in sorted(unit_dir.glob("test_*.py")):
        name = test_file.stem[5:]  # Remove test_ prefix
        if name in UNIT_TEST_MAPPINGS:
            dest_dir = PROJECT_ROOT / UNIT_TEST_MAPPINGS[name]
            result = migrate_file(test_file, dest_dir, dry_run)
            results.append(result)
        else:
            logger.info(f"  WARNING: No mapping for {test_file.name}, skipping")

    # Handle subdirectories (llm_interface_pkg/, monitoring/)
    for subdir in unit_dir.iterdir():
        if subdir.is_dir() and subdir.name != "__pycache__":
            for test_file in sorted(subdir.glob("test_*.py")):
                if subdir.name in UNIT_SUBDIR_MAPPINGS:
                    dest_dir = PROJECT_ROOT / UNIT_SUBDIR_MAPPINGS[subdir.name]
                    result = migrate_file(test_file, dest_dir, dry_run)
                    results.append(result)
                else:
                    logger.info(
                        f"  WARNING: No mapping for subdir "
                        f"{subdir.name}/{test_file.name}"
                    )

    return results


def migrate_root_tests(
    dry_run: bool = True,
    already_migrated: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Migrate root-level test files from infrastructure/shared/tests/."""
    results = []
    tests_dir = PROJECT_ROOT / "infrastructure" / "shared" / "tests"
    skip = already_migrated or set()

    # These are the root-level test_*.py files (not in subdirs)
    for test_file in sorted(tests_dir.glob("test_*.py")):
        name = test_file.stem[5:]  # Remove test_ prefix

        # Skip if same-named test was already migrated from unit/
        new_filename = get_new_filename(test_file.name)
        if name in UNIT_TEST_MAPPINGS:
            dest_path = PROJECT_ROOT / UNIT_TEST_MAPPINGS[name] / new_filename
            dest_key = str(dest_path.relative_to(PROJECT_ROOT))
            if dest_key in skip:
                logger.info(f"  SKIP (duplicate): {test_file.name} -> {dest_key}")
                continue
            dest_dir = PROJECT_ROOT / UNIT_TEST_MAPPINGS[name]
        else:
            dest_dir = PROJECT_ROOT / "autobot-user-backend"

        result = migrate_file(test_file, dest_dir, dry_run)
        results.append(result)

    return results


def migrate_infra_component_tests(
    dry_run: bool = True,
) -> list[tuple[str, str]]:
    """Migrate infrastructure/<component>/tests/ to component dirs."""
    results = []

    # autobot-user-backend API tests
    api_tests = PROJECT_ROOT / "infrastructure" / "autobot-user-backend" / "tests"
    if api_tests.exists():
        for test_file in api_tests.rglob("test_*.py"):
            # Preserve relative path structure
            rel = test_file.relative_to(api_tests)
            dest_dir = PROJECT_ROOT / "autobot-user-backend" / rel.parent
            result = migrate_file(test_file, dest_dir, dry_run)
            results.append(result)

    # autobot-slm-backend tests
    slm_tests = PROJECT_ROOT / "infrastructure" / "autobot-slm-backend" / "tests"
    if slm_tests.exists():
        for test_file in slm_tests.rglob("test_*.py"):
            rel = test_file.relative_to(slm_tests)
            dest_dir = PROJECT_ROOT / "autobot-slm-backend" / rel.parent
            result = migrate_file(test_file, dest_dir, dry_run)
            results.append(result)

    # autobot-npu-worker tests
    npu_tests = PROJECT_ROOT / "infrastructure" / "autobot-npu-worker" / "tests"
    if npu_tests.exists():
        for test_file in npu_tests.rglob("test_*.py"):
            rel = test_file.relative_to(npu_tests)
            dest_dir = PROJECT_ROOT / "autobot-npu-worker" / rel.parent
            result = migrate_file(test_file, dest_dir, dry_run)
            results.append(result)

    return results


def print_report(results: list[tuple[str, str]], phase: str) -> None:
    """Print migration report."""
    logger.info(f"\n{'='*60}")
    logger.info(f"  {phase}")
    logger.info(f"{'='*60}")
    for old_path, new_path in results:
        logger.info(f"  {old_path}")
        logger.info(f"    -> {new_path}")
    logger.info(f"\n  Total: {len(results)} files")


def main() -> None:
    """Run the test migration."""
    parser = argparse.ArgumentParser(description="Migrate tests to colocated layout")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without moving files",
    )
    parser.add_argument(
        "--phase",
        choices=["unit", "root", "infra", "all"],
        default="all",
        help="Which phase to run",
    )
    args = parser.parse_args()

    logger.info(f"\nTest Migration Script (Issue #734)")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    logger.info(f"Phase: {args.phase}")

    all_results = []
    migrated_destinations = set()

    if args.phase in ("unit", "all"):
        results = migrate_unit_tests(args.dry_run)
        print_report(results, "Phase 1: Unit Tests (infrastructure/shared/tests/unit/)")
        all_results.extend(results)
        migrated_destinations = {new_path for _, new_path in results}

    if args.phase in ("root", "all"):
        results = migrate_root_tests(args.dry_run, migrated_destinations)
        print_report(
            results, "Phase 2: Root Tests (infrastructure/shared/tests/test_*.py)"
        )
        all_results.extend(results)

    if args.phase in ("infra", "all"):
        results = migrate_infra_component_tests(args.dry_run)
        print_report(
            results, "Phase 3: Infra Component Tests (infrastructure/*/tests/)"
        )
        all_results.extend(results)

    logger.info(f"\n{'='*60}")
    logger.info(f"  TOTAL: {len(all_results)} files migrated")
    logger.info(f"{'='*60}")

    if args.dry_run:
        logger.info("\n  This was a dry run. Run without --dry-run to execute.")


if __name__ == "__main__":
    main()
