# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Library modules whose ``__main__`` block does not yet call ``setup_logging()`` (#20894).

BOUNDARY: the entry points `entry_points_start_file_logging_20894_test.py` discovers, minus those
that call the function and those exempt there. Every entry here is a library module with a demo or
self-test ``__main__`` block; run directly it logs to the console only. Services, workers and ops CLIs
are not here -- they call it.

Frozen at the #20894 PR: 76 modules, derived by the detector itself -- 75 library demo blocks plus
one ops script over the 600-line ceiling (enhance_workflow_ui.py; one more line fails the size
check, so it is wired with its split). Not wired in that PR because it sits near the 100-changed-file
cap and 30+ of these are at their size pin. Wiring them is #21272.
Each entry only goes DOWN: the guard fails on one that now calls the function or stopped being an
entry point.
"""

PENDING: frozenset[str] = frozenset(
    {
        "autobot-backend/advanced_rag_optimizer.py",
        "autobot-backend/agent_tier_classifier.py",
        "autobot-backend/agents/classification_agent.py",
        "autobot-backend/agents/gemma_classification_agent.py",
        "autobot-backend/agents/man_page_knowledge_integrator.py",
        "autobot-backend/api/api_benchmarks.py",
        "autobot-backend/api/chat_knowledge_manager.py",
        "autobot-backend/api/codebase_analytics/config_duplication_detector.py",
        "autobot-backend/api/registry_update.py",
        "autobot-backend/app_factory.py",
        "autobot-backend/benchmarks/cache_benchmark.py",
        "autobot-backend/benchmarks/verbatim_symbolic_benchmark.py",
        "autobot-backend/code_analysis/auto-tools/playwright_sanitizer.py",
        "autobot-backend/code_analysis/auto-tools/security_deep_sanitizer.py",
        "autobot-backend/code_analysis/auto-tools/security_sanitizer.py",
        "autobot-backend/code_analysis/auto-tools/security_verification.py",
        "autobot-backend/code_analysis/auto-tools/vue_quality_tool.py",
        "autobot-backend/code_analysis/scripts/analyze_critical_env_vars.py",
        "autobot-backend/code_analysis/scripts/analyze_duplicates.py",
        "autobot-backend/code_analysis/src/anti_pattern_detector.py",
        "autobot-backend/code_analysis/src/api_consistency_analyzer.py",
        "autobot-backend/code_analysis/src/architectural_pattern_analyzer.py",
        "autobot-backend/code_analysis/src/code_analyzer.py",
        "autobot-backend/code_analysis/src/code_quality_dashboard.py",
        "autobot-backend/code_analysis/src/env_analyzer.py",
        "autobot-backend/code_analysis/src/frontend_analyzer.py",
        "autobot-backend/code_analysis/src/ownership_analyzer.py",
        "autobot-backend/code_analysis/src/patch_generator.py",
        "autobot-backend/code_analysis/src/testing_coverage_analyzer.py",
        "autobot-backend/command_manual_manager.py",
        "autobot-backend/diagnostics.py",
        "autobot-backend/event_manager.py",
        "autobot-backend/gui_controller.py",
        "autobot-backend/intelligence/demos/run_intelligent_agent.py",
        "autobot-backend/intelligence/demos/run_streaming_executor.py",
        "autobot-backend/intelligence/goal_processor.py",
        "autobot-backend/intelligence/intelligent_agent.py",
        "autobot-backend/intelligence/os_detector.py",
        "autobot-backend/intelligence/streaming_executor.py",
        "autobot-backend/knowledge/rag_benchmarks.py",
        "autobot-backend/llm_self_awareness.py",
        "autobot-backend/project_state_manager.py",
        "autobot-backend/project_state_tracker.py",
        "autobot-backend/protocols/agent_communication_demo.py",
        "autobot-backend/rlm/benchmark.py",
        "autobot-backend/secure_command_executor.py",
        "autobot-backend/security/intelligent_agent_security.py",
        "autobot-backend/security/prompt_injection_detector.py",
        "autobot-backend/security/secure_llm_command_parser.py",
        "autobot-backend/security/threat_intelligence.py",
        "autobot-backend/security_layer.py",
        "autobot-backend/startup_validation.py",
        "autobot-backend/system_integration.py",
        "autobot-backend/utils/adaptive_timeouts.py",
        "autobot-backend/utils/claude_api_integration.py",
        "autobot-backend/utils/encoding_utils.py",
        "autobot-backend/utils/error_boundary_examples.py",
        "autobot-backend/utils/gpu_acceleration_optimizer.py",
        "autobot-backend/utils/graceful_degradation.py",
        "autobot-backend/utils/hardware_metrics.py",
        "autobot-backend/utils/llm_config_sync.py",
        "autobot-backend/utils/long_running_operations_framework.py",
        "autobot-backend/utils/operation_timeout_integration.py",
        "autobot-backend/utils/payload_optimizer.py",
        "autobot-backend/utils/performance_monitor.py",
        "autobot-backend/utils/request_batcher.py",
        "autobot-backend/utils/system_context.py",
        "autobot-backend/utils/timeout_migration_examples.py",
        "autobot-backend/utils/todowrite_optimizer.py",
        "autobot-backend/utils/tool_pattern_analyzer.py",
        "autobot-backend/voice_interface.py",
        "autobot-backend/workflow_classifier.py",
        "autobot-infrastructure/shared/scripts/utilities/enhance_workflow_ui.py",
        "autobot-infrastructure/shared/scripts/analysis/npu_performance_measurement.py",
        "autobot_shared/circuit_breaker.py",
        "autobot_shared/coordination/issue_claims.py",
    }
)
