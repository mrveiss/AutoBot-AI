#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test colocation migration script for Issue #734.

Moves test files from autobot-infrastructure/shared/tests/ to sit next to their
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
    # Direct name matches -> autobot-backend root
    "advanced_rag_optimizer": "autobot-backend",
    "chat_intent_detector": "autobot-backend",
    "circuit_breaker": "autobot-backend",
    "encryption_service": "autobot-backend",
    "slash_command_handler": "autobot-backend",
    "worker_node": "autobot-backend",
    # code_intelligence/
    "anti_pattern_detector": "autobot-backend/code_intelligence",
    "bug_predictor": "autobot-backend/code_intelligence",
    "code_fingerprinting": "autobot-backend/code_intelligence",
    "code_review_engine": "autobot-backend/code_intelligence",
    "conversation_flow_analyzer": "autobot-backend/code_intelligence",
    "llm_code_generator": "autobot-backend/code_intelligence",
    "llm_pattern_analyzer": "autobot-backend/code_intelligence",
    "log_pattern_miner": "autobot-backend/code_intelligence",
    "performance_analyzer": "autobot-backend/code_intelligence",
    "precommit_analyzer": "autobot-backend/code_intelligence",
    "redis_optimizer": "autobot-backend/code_intelligence",
    "security_analyzer": "autobot-backend/code_intelligence",
    # services/
    "chat_knowledge_service": "autobot-backend/services",
    "graph_rag_service": "autobot-backend/services",
    "redis_service_manager": "autobot-backend/services",
    "security_workflow_manager": "autobot-backend/services",
    "terminal_completion_service": "autobot-backend/services",
    "terminal_history_service": "autobot-backend/services",
    # knowledge/
    "embedding_cache": "autobot-backend/knowledge",
    "search_quality": "autobot-backend/knowledge",
    # api/
    "knowledge_categories": "autobot-backend/api",
    "knowledge_vectorization": "autobot-backend/api",
    # utils/
    "config_manager": "autobot-backend/utils",
    "operation_timeout_integration": "autobot-backend/utils",
    # security/
    "input_validator": "autobot-backend/security",
    # agents/
    "graph_entity_extractor": "autobot-backend/agents",
    # autobot_shared/
    "error_boundaries": "autobot_shared",
    "ssot_config": "autobot_shared",
    # --- Tests mapped by import analysis (no direct name match) ---
    # src.extensions.base
    "extension_hooks": "autobot-backend/extensions",
    # src.monitoring.prometheus_metrics
    "redis_prometheus_metrics": "autobot-backend/monitoring",
    # src.utils.errors
    "repairable_exception": "autobot-backend/utils",
    # src.code_intelligence.shared.ast_cache
    "shared_caches": "autobot-backend/code_intelligence/shared",
    # src.chat_workflow.models
    "streaming_message": "autobot-backend/chat_workflow",
    # src.agents.hierarchical_agent
    "subordinate_delegation": "autobot-backend/agents",
    # src.llm_interface_pkg.tiered_routing
    "tiered_routing": "autobot-backend/llm_interface_pkg",
    # src.config
    "timeout_configuration": "autobot-backend/config",
    # backend.api.codebase_analytics.*
    "call_graph_resolution": "autobot-backend/api/codebase_analytics",
    "codebase_stats_endpoint": "autobot-backend/api/codebase_analytics",
    "parallel_processing": "autobot-backend/api/codebase_analytics",
    "technical_debt_detection": "autobot-backend/api/codebase_analytics",
    # backend.type_defs.common
    "chat_merge_messages": "autobot-backend/type_defs",
    # backend.dependencies
    "dependency_injection": "autobot-backend",
    # backend.services.*
    "rag_integration": "autobot-backend/services",
    "wake_word_detection": "autobot-backend/services",
    # Self-contained/general tests -> component root
    "agent_optimizer": "autobot-backend/agents",
    "api_endpoint_migrations": "autobot-backend/api",
    "code_semantic_search": "autobot-backend/knowledge",
    "config_registry": "autobot-backend/config",
    "conversation_file_manager_init": "autobot-backend",
    "escape_character_handling": "autobot-backend/utils",
    "file_locking": "autobot-backend/utils",
    "hallucination_prevention": "autobot-backend/knowledge",
    "helpers_reorganization": "autobot-backend/utils",
    "knowledge_base_async": "autobot-backend/knowledge",
    "mcp_cache": "autobot-backend/mcp",
    "persist_conversation_dedup": "autobot-backend/chat_history",
    "respond_tool": "autobot-backend/tools",
    "stats_counter_parsing": "autobot-backend/utils",
    "thread_safety": "autobot-backend/utils",
    "workflow_plan_approval": "autobot-backend/chat_workflow",
    # --- Root-level test mappings (autobot-infrastructure/shared/tests/test_*.py) ---
    # Direct name matches
    "api_responses": "autobot-backend/utils",
    "async_initializable": "autobot-backend/utils",
    "security_layer": "autobot-backend",
    "hardware_metrics": "autobot-backend/utils",
    "knowledge_manager": "autobot-backend/agents",
    "lazy_singleton": "autobot-backend/utils",
    "monitoring_alerts": "autobot-backend/utils",
    "retry_mechanism": "autobot-backend",
    "secure_command_executor": "autobot-backend",
    "secure_terminal_websocket": "autobot-backend/api",
    "system_integration": "autobot-backend",
    "system_validation": "autobot-backend/api",
    "terminal_input_handler": "autobot-backend/utils",
    "tool_discovery": "autobot-backend",
    "validators": "autobot-backend/utils",
    "error_catalog": "autobot-backend/utils",
    "error_metrics": "autobot-backend/utils",
    # Import-analysis mapped
    "atomic_facts_extraction": "autobot-backend/agents",
    "computer_vision_refactoring": "autobot-backend/computer_vision",
    "entity_resolution": "autobot-backend/utils",
    "gpu_performance": "autobot-backend/utils",
    "intent_classification": "autobot-backend",
    "kb_optimization": "autobot-backend/knowledge",
    "llm_interface_core": "autobot-backend/llm_interface_pkg",
    "memory_package": "autobot-backend",
    "model_optimizer_refactoring": "autobot-backend/utils",
    "memory_consolidation": "autobot-backend",
    "control_panel": "autobot-backend",
    "multimodal_ai": "autobot-backend/computer_vision",
    "queue_integration": "autobot-backend/services",
    "redis_consolidation": "autobot-backend/utils",
    "redis_thread_safety": "autobot-backend/utils",
    "security_api": "autobot-backend/api",
    "security_integration": "autobot-backend/security",
    "semantic_chunking": "autobot-backend/utils",
    "settings_debug": "autobot-backend/services",
    "temporal_invalidation": "autobot-backend/services",
    # Self-contained/general tests
    "cache_consolidation_p4": "autobot-backend/cache",
    "comprehensive_system_validation": "autobot-backend",
    "concurrency_safety": "autobot-backend/utils",
    "config_consolidation_p2": "autobot-backend/config",
    "config": "autobot-backend/config",
    "file_upload_comprehensive": "autobot-backend/api",
    "gpu_kb_integration": "autobot-backend/knowledge",
    "minimal_backend": "autobot-backend",
    "monitoring_and_alerts": "autobot-backend/monitoring",
    "multi_agent_workflow_validation": "autobot-backend/agents",
    "session_validation": "autobot-backend/security",
    "simple_optimization": "autobot-backend/utils",
}

# Additional mappings for unit/ subdirectories
UNIT_SUBDIR_MAPPINGS = {
    # llm_interface_pkg/ subdir
    "llm_interface_pkg": "autobot-backend/llm_interface_pkg",
    # monitoring/ subdir
    "monitoring": "autobot-backend/monitoring",
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
        return str(src_path.relative_to(PROJECT_ROOT)), str(dest_path.relative_to(PROJECT_ROOT))

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

    return str(src_path.relative_to(PROJECT_ROOT)), str(dest_path.relative_to(PROJECT_ROOT))


def migrate_unit_tests(dry_run: bool = True) -> list[tuple[str, str]]:
    """Migrate unit tests from autobot-infrastructure/shared/tests/unit/."""
    results = []
    unit_dir = PROJECT_ROOT / "autobot-infrastructure" / "shared" / "tests" / "unit"

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
                    logger.info(f"  WARNING: No mapping for subdir " f"{subdir.name}/{test_file.name}")

    return results


def migrate_root_tests(
    dry_run: bool = True,
    already_migrated: set[str] | None = None,
) -> list[tuple[str, str]]:
    """Migrate root-level test files from autobot-infrastructure/shared/tests/."""
    results = []
    tests_dir = PROJECT_ROOT / "autobot-infrastructure" / "shared" / "tests"
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
            dest_dir = PROJECT_ROOT / "autobot-backend"

        result = migrate_file(test_file, dest_dir, dry_run)
        results.append(result)

    return results


def migrate_infra_component_tests(
    dry_run: bool = True,
) -> list[tuple[str, str]]:
    """Migrate autobot-infrastructure/<component>/tests/ to component dirs."""
    results = []

    # autobot-backend API tests
    api_tests = PROJECT_ROOT / "autobot-infrastructure" / "autobot-backend" / "tests"
    if api_tests.exists():
        for test_file in api_tests.rglob("test_*.py"):
            # Preserve relative path structure
            rel = test_file.relative_to(api_tests)
            dest_dir = PROJECT_ROOT / "autobot-backend" / rel.parent
            result = migrate_file(test_file, dest_dir, dry_run)
            results.append(result)

    # autobot-slm-backend tests
    slm_tests = PROJECT_ROOT / "autobot-infrastructure" / "autobot-slm-backend" / "tests"
    if slm_tests.exists():
        for test_file in slm_tests.rglob("test_*.py"):
            rel = test_file.relative_to(slm_tests)
            dest_dir = PROJECT_ROOT / "autobot-slm-backend" / rel.parent
            result = migrate_file(test_file, dest_dir, dry_run)
            results.append(result)

    # autobot-npu-worker tests
    npu_tests = PROJECT_ROOT / "autobot-infrastructure" / "autobot-npu-worker" / "tests"
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

    logger.info("\nTest Migration Script (Issue #734)")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'EXECUTE'}")
    logger.info(f"Phase: {args.phase}")

    all_results = []
    migrated_destinations = set()

    if args.phase in ("unit", "all"):
        results = migrate_unit_tests(args.dry_run)
        print_report(results, "Phase 1: Unit Tests (autobot-infrastructure/shared/tests/unit/)")
        all_results.extend(results)
        migrated_destinations = {new_path for _, new_path in results}

    if args.phase in ("root", "all"):
        results = migrate_root_tests(args.dry_run, migrated_destinations)
        print_report(results, "Phase 2: Root Tests (autobot-infrastructure/shared/tests/test_*.py)")
        all_results.extend(results)

    if args.phase in ("infra", "all"):
        results = migrate_infra_component_tests(args.dry_run)
        print_report(results, "Phase 3: Infra Component Tests (autobot-infrastructure/*/tests/)")
        all_results.extend(results)

    logger.info(f"\n{'='*60}")
    logger.info(f"  TOTAL: {len(all_results)} files migrated")
    logger.info(f"{'='*60}")

    if args.dry_run:
        logger.info("\n  This was a dry run. Run without --dry-run to execute.")


if __name__ == "__main__":
    main()
