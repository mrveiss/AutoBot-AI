# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Grandfathered restating docstrings (#17165), measured 2026-09-20.

280 named public non-test symbols already had a docstring that restates their
own name when ``docstring_restatement_guard_17165_test.py`` landed -- fixing all
280 was not this guard's job, catching the *next* one is. This freezes the known
set so the guard blocks any NEW restatement without failing CI on the existing
backlog #17165's drafting batches will work through.

THIS MAPPING ONLY SHRINKS. Fixing one means deleting its entry (or its whole
file key, once empty) here in the SAME commit that fixes the docstring -- never
add an entry to make a new restatement pass.
"""

from __future__ import annotations

KNOWN_RESTATEMENTS: dict[str, frozenset[str]] = {
    "autobot-backend/agents/agent_client.py": frozenset({"register_container_agent", "register_local_agent"}),
    "autobot-backend/agents/interactive_terminal_agent.py": frozenset({"resize_terminal"}),
    "autobot-backend/agents/kb_librarian/formatters.py": frozenset(
        {
            "format_best_practices",
            "format_documentation_examples",
            "format_prerequisites",
            "format_tool_requirements",
            "format_verification_steps",
        }
    ),
    "autobot-backend/agents/web_researcher.py": frozenset({"get_circuit_breaker_status"}),
    "autobot-backend/api/analytics_continuous_learning.py": frozenset({"PatternStatistics"}),
    "autobot-backend/api/analytics_llm_patterns.py": frozenset({"OptimizationRecommendation"}),
    "autobot-backend/api/analytics_precommit.py": frozenset({"get_file_content"}),
    "autobot-backend/api/budget_policies.py": frozenset(
        {"delete_budget_policy", "get_agent_pause_status", "update_budget_policy"}
    ),
    "autobot-backend/api/elevation.py": frozenset({"revoke_elevation_session"}),
    "autobot-backend/api/knowledge_metadata.py": frozenset({"delete_metadata_template"}),
    "autobot-backend/api/long_running_operations.py": frozenset({"initialize_operations_service"}),
    "autobot-backend/api/schemas_agent.py": frozenset({"InferenceOptimizationSettings"}),
    "autobot-backend/api/schemas_analytics.py": frozenset(
        {
            "ArchitectureAnalysisRequest",
            "CFGAnalyzeFileRequest",
            "CompleteTaskRequest",
            "EvolutionAnalysisResponse",
            "PerformanceAnalysisResult",
            "PromptAnalysisRequest",
            "RumSessionMetric",
        }
    ),
    "autobot-backend/api/schemas_knowledge.py": frozenset(
        {
            "ComplianceReportRequest",
            "ConflictSchema",
            "KnowledgeScopeFilter",
            "ResolveConflictRequest",
            "validate_source_type",
        }
    ),
    "autobot-backend/api/schemas_system.py": frozenset(
        {
            "AuditStatisticsResponse",
            "ElementDetectionRequest",
            "FailureAnalysisResponse",
            "HealthCheckResponse",
            "HealthStatusResponse",
            "ScreenAnalysisRequest",
            "ServiceOperationResponse",
            "ServiceStatusResponse",
        }
    ),
    "autobot-backend/api/schemas_workflows.py": frozenset(
        {
            "ApprovalGateResponse",
            "BatchJobStatus",
            "BatchJobType",
            "SystemValidationRequestModel",
            "TaskApprovalLinkResponse",
        }
    ),
    "autobot-backend/api/sequential_thinking_mcp.py": frozenset({"clear_thinking_session"}),
    "autobot-backend/api/terminal_tools.py": frozenset({"check_tool_installed"}),
    "autobot-backend/api/user_management/organizations.py": frozenset(
        {"deactivate_organization", "delete_organization", "get_organization_by_slug"}
    ),
    "autobot-backend/api/user_management/teams.py": frozenset(
        {"delete_team", "list_team_members", "update_member_role"}
    ),
    "autobot-backend/chat_workflow/session_handler.py": frozenset({"get_active_sessions_count"}),
    "autobot-backend/circuit_breaker.py": frozenset({"reset_all_circuit_breakers"}),
    "autobot-backend/code_intelligence/code_review_engine.py": frozenset({"DiffFile"}),
    "autobot-backend/code_intelligence/doc_generation/models.py": frozenset({"add_base_class"}),
    "autobot-backend/code_intelligence/precommit_analyzer.py": frozenset({"add_custom_check"}),
    "autobot-backend/dependency_container.py": frozenset({"add_shutdown_hook"}),
    "autobot-backend/initialization/lifespan_shutdown.py": frozenset({"stop_gateway"}),
    "autobot-backend/knowledge/metadata.py": frozenset({"delete_metadata_template"}),
    "autobot-backend/knowledge/rag_benchmarks.py": frozenset({"test_vector_similarity_computation_benchmark"}),
    "autobot-backend/knowledge/relations.py": frozenset({"get_fact_relations"}),
    "autobot-backend/knowledge_categories.py": frozenset({"get_category_color"}),
    "autobot-backend/knowledge_sync_incremental.py": frozenset({"start_background_sync_daemon"}),
    "autobot-backend/memory/compat.py": frozenset({"cleanup_old_memories"}),
    "autobot-backend/modern_ai_integration.py": frozenset({"AnthropicClaudeProvider", "GoogleGeminiProvider"}),
    "autobot-backend/pki/config.py": frozenset({"CertificateStatus"}),
    "autobot-backend/pki/generator.py": frozenset({"get_certificate_status"}),
    "autobot-backend/planner/planner.py": frozenset({"get_current_step"}),
    "autobot-backend/routers/code_completion.py": frozenset({"ContextAnalysisRequest", "ContextAnalysisResponse"}),
    "autobot-backend/security/enterprise/sso_integration.py": frozenset({"invalidate_sso_session"}),
    "autobot-backend/security/enterprise/threat_detection/models.py": frozenset({"count_recent_api_requests"}),
    "autobot-backend/security/input_validator.py": frozenset(
        {"sanitize_web_content", "validate_research_query", "validate_url"}
    ),
    "autobot-backend/security/secure_web_research.py": frozenset({"reset_security_statistics"}),
    "autobot-backend/services/agent_analytics.py": frozenset({"get_all_agents_metrics"}),
    "autobot-backend/services/codebase_indexing_service.py": frozenset({"index_autobot_codebase", "index_single_file"}),
    "autobot-backend/services/load_balancer.py": frozenset({"get_all_workers"}),
    "autobot-backend/services/npu_worker_manager.py": frozenset({"test_worker_connection"}),
    "autobot-backend/services/redis_service_manager.py": frozenset({"ServiceOperationResult"}),
    "autobot-backend/services/temporal_invalidation_service.py": frozenset({"remove_invalidation_rule"}),
    "autobot-backend/services/wake_word_service.py": frozenset({"remove_callback"}),
    "autobot-backend/services/workflow_automation/models.py": frozenset({"WorkflowStepStatus"}),
    "autobot-backend/temporal_knowledge_manager.py": frozenset({"stop_background_processing"}),
    "autobot-backend/tools/tool_registry.py": frozenset(
        {
            "add_file_to_knowledge_base",
            "bring_window_to_front",
            "execute_system_command",
            "list_system_services",
            "query_system_information",
            "search_knowledge_base",
        }
    ),
    "autobot-backend/utils/advanced_cache_manager.py": frozenset({"get_cached_system_status"}),
    "autobot-backend/utils/async_stream_processor.py": frozenset({"StreamProcessingResult"}),
    "autobot-backend/utils/catalog_http_exceptions.py": frozenset({"raise_validation_error"}),
    "autobot-backend/utils/gpu_optimization/monitoring.py": frozenset(
        {"calculate_memory_efficiency", "calculate_power_efficiency", "calculate_thermal_efficiency"}
    ),
    "autobot-backend/utils/graceful_degradation.py": frozenset({"get_strategy_name"}),
    "autobot-backend/utils/hardware_metrics.py": frozenset({"get_phase9_performance_dashboard"}),
    "autobot-backend/utils/hot_reload_manager.py": frozenset({"get_hot_reload_status"}),
    "autobot-backend/utils/monitoring_alerts.py": frozenset({"add_notification_channel", "remove_alert_rule"}),
    "autobot-backend/utils/paths_manager.py": frozenset(
        {
            "get_backend_log_path",
            "get_debug_log_path",
            "get_error_log_path",
            "get_frontend_log_path",
            "get_rum_log_path",
            "get_system_log_path",
        }
    ),
    "autobot-backend/utils/performance_monitor.py": frozenset({"get_performance_dashboard"}),
    "autobot-backend/utils/service_registry.py": frozenset({"get_ai_stack_url", "get_npu_worker_url"}),
    "autobot-backend/voice_processing/providers/generic_provider.py": frozenset({"provider_name"}),
    "autobot-backend/voice_processing/providers/lv/late_provider.py": frozenset(
        {"provider_name", "supported_languages"}
    ),
    "autobot-backend/voice_processing/providers/lv/tilde_provider.py": frozenset(
        {"provider_name", "supported_languages"}
    ),
    "autobot-infrastructure/shared/docker/ai-stack/ai_api_server.py": frozenset({"global_exception_handler"}),
    "autobot-infrastructure/shared/scripts/analysis/redis_final_analysis.py": frozenset(
        {"test_langchain_db0_workaround"}
    ),
    "autobot-infrastructure/shared/scripts/apply_memory_optimizations.py": frozenset(
        {"apply_global_memory_optimizations", "save_optimization_report"}
    ),
    "autobot-infrastructure/shared/scripts/automated_testing_procedure.py": frozenset(
        {"run_code_quality_tests", "run_integration_tests", "run_performance_tests", "run_security_tests"}
    ),
    "autobot-infrastructure/shared/scripts/backup_manager.py": frozenset(
        {"backup_docker_volume", "create_backup_metadata"}
    ),
    "autobot-infrastructure/shared/scripts/monitor_services.py": frozenset({"stop_monitoring"}),
    "autobot-infrastructure/shared/scripts/populate_kb_fixed.py": frozenset({"populate_knowledge_base_chromadb"}),
    "autobot-infrastructure/shared/scripts/run_code_analysis.py": frozenset(
        {"run_architecture_analysis", "run_code_quality_analysis"}
    ),
    "autobot-infrastructure/shared/scripts/utilities/npu_worker.py": frozenset({"get_npu_temperature"}),
    "autobot-infrastructure/shared/scripts/validation_dashboard_generator.py": frozenset({"generate_html_dashboard"}),
    "autobot-npu-worker/resources/windows-npu-worker/app/worker_inference.py": frozenset({"process_task"}),
    "autobot-npu-worker/resources/windows-npu-worker/app/worker_metrics.py": frozenset(
        {"get_npu_memory_usage", "get_npu_metrics", "get_npu_status"}
    ),
    "autobot-npu-worker/resources/windows-npu-worker/app/worker_startup.py": frozenset({"load_default_models"}),
    "autobot-npu-worker/resources/windows-npu-worker/gui/widgets/metrics_display.py": frozenset(
        {"update_metrics_history_table"}
    ),
    "autobot-npu-worker/resources/windows-npu-worker/gui/windows/log_viewer.py": frozenset({"clear_log_display"}),
    "autobot-npu-worker/resources/windows-npu-worker/gui/windows/settings_dialog.py": frozenset(
        {
            "browse_log_directory",
            "create_logging_settings_tab",
            "create_npu_settings_tab",
            "create_service_settings_tab",
            "create_yaml_editor_tab",
            "load_yaml_file",
        }
    ),
    "autobot-slm-backend/api/agents.py": frozenset({"get_default_agent"}),
    "autobot-slm-backend/api/api_keys.py": frozenset({"revoke_api_key"}),
    "autobot-slm-backend/api/autobot_users.py": frozenset({"delete_autobot_user", "update_autobot_user"}),
    "autobot-slm-backend/api/code_source.py": frozenset({"CodeNotificationResponse"}),
    "autobot-slm-backend/api/errors.py": frozenset(
        {"AlertThresholdResponse", "TestErrorResponse", "TopErrorsResponse"}
    ),
    "autobot-slm-backend/api/nodes.py": frozenset(
        {
            "apply_node_updates",
            "delete_node",
            "get_node_events",
            "renew_node_certificate",
            "update_node",
            "update_node_roles",
        }
    ),
    "autobot-slm-backend/api/orchestration.py": frozenset({"ServiceActionResponse", "ServiceDefinitionResponse"}),
    "autobot-slm-backend/api/performance.py": frozenset(
        {"AlertRuleModel", "AlertRuleUpdateRequest", "delete_alert_rule"}
    ),
    "autobot-slm-backend/api/rdp.py": frozenset(
        {"delete_rdp_credential", "list_node_rdp_credentials", "update_rdp_credential"}
    ),
    "autobot-slm-backend/api/security.py": frozenset(
        {
            "acknowledge_security_event",
            "delete_security_policy",
            "list_security_policies",
            "resolve_security_event",
            "update_security_policy",
        }
    ),
    "autobot-slm-backend/api/services.py": frozenset({"delete_service_conflict"}),
    "autobot-slm-backend/api/slm_users.py": frozenset({"delete_slm_user", "update_slm_user"}),
    "autobot-slm-backend/api/tls.py": frozenset(
        {"delete_tls_credential", "list_node_tls_credentials", "update_tls_credential"}
    ),
    "autobot-slm-backend/api/vnc.py": frozenset(
        {"delete_vnc_credential", "list_node_vnc_credentials", "update_vnc_credential"}
    ),
    "autobot-slm-backend/migrations/runner.py": frozenset({"mark_migration_applied"}),
    "autobot-slm-backend/models/npu_schemas.py": frozenset({"NPUNodeStatusResponse"}),
    "autobot-slm-backend/models/schemas.py": frozenset(
        {
            "AgentCreateRequest",
            "AgentUpdateRequest",
            "BackupResponse",
            "BackupRestoreResponse",
            "BlueGreenActionResponse",
            "CertificateActionResponse",
            "CodeSyncStatusResponse",
            "CodeVersionNotificationResponse",
            "DeploymentResponse",
            "MaintenanceWindowResponse",
            "NodeEventResponse",
            "NodeResponse",
            "RDPCredentialUpdate",
            "ReplicationResponse",
            "RolePurgeResponse",
            "SecurityEventAcknowledge",
            "SecurityEventCreate",
            "SecurityEventResolve",
            "SecurityEventResponse",
            "SecurityPolicyCreate",
            "SecurityPolicyResponse",
            "SecurityPolicyUpdate",
            "ServiceActionResponse",
            "ServiceConflictCreateRequest",
            "ServiceConflictResponse",
            "ServiceListResponse",
            "ServiceLogsRequest",
            "ServiceLogsResponse",
            "SettingResponse",
            "UpdateApplyRequest",
            "UpdateApplyResponse",
            "UpdateInfoResponse",
            "VNCCredentialUpdate",
        }
    ),
    "autobot-slm-backend/services/auth.py": frozenset({"get_user_by_username", "hash_password"}),
    "autobot-slm-backend/user_management/schemas/mfa.py": frozenset({"MFASetupResponse"}),
    "autobot-slm-backend/user_management/services/sso_service.py": frozenset({"SSOProviderNotFoundError"}),
    "autobot_shared/logging_manager.py": frozenset(
        {"get_audit_logger", "get_backend_logger", "get_debug_logger", "get_frontend_logger", "get_llm_logger"}
    ),
    "autobot_shared/monitoring/metrics/claude_api.py": frozenset({"ClaudeAPIMetricsRecorder"}),
    "autobot_shared/monitoring/metrics/frontend.py": frozenset(
        {"record_form_submission", "record_session_duration", "record_time_to_interactive"}
    ),
    "autobot_shared/monitoring/metrics/knowledge_base.py": frozenset(
        {
            "record_cache_eviction",
            "record_cache_hit",
            "record_cache_miss",
            "record_document_operation",
            "record_embedding_operation",
        }
    ),
    "autobot_shared/monitoring/metrics/llm_provider.py": frozenset({"LLMProviderMetricsRecorder"}),
    "autobot_shared/monitoring/metrics/performance.py": frozenset(
        {
            "record_npu_worker_response_time",
            "record_npu_worker_task_completed",
            "record_npu_worker_task_failed",
            "record_optimization_recommendation",
            "record_performance_alert",
            "update_npu_worker_status",
        }
    ),
    "autobot_shared/monitoring/metrics/redis.py": frozenset(
        {"RedisMetricsRecorder", "record_connection_error", "record_key_hit", "record_key_miss", "set_replication_lag"}
    ),
    "autobot_shared/monitoring/metrics/service_health.py": frozenset({"ServiceHealthMetricsRecorder"}),
    "autobot_shared/monitoring/metrics/websocket.py": frozenset({"record_message_dropped"}),
    "autobot_shared/monitoring/prometheus_metrics.py": frozenset(
        {
            "record_claude_api_request",
            "record_claude_api_response_time",
            "record_document_operation",
            "record_embedding_operation",
            "record_frontend_api_error",
            "record_frontend_api_request",
            "record_frontend_critical_issue",
            "record_frontend_form_submission",
            "record_frontend_session_duration",
            "record_frontend_user_action",
            "record_github_commit",
            "record_llm_error",
            "record_llm_request_start",
            "record_operation_duration",
            "record_optimization_recommendation",
            "record_performance_alert",
            "record_redis_operation",
            "record_service_response_time",
            "record_task_execution",
            "record_websocket_disconnection",
            "record_websocket_error",
            "record_workflow_execution",
            "update_service_status",
            "update_task_queue_size",
        }
    ),
    "autobot_shared/redis_client.py": frozenset({"close_all_redis_connections"}),
    "scripts/daily_health_check.py": frozenset({"check_disk_usage", "check_redis_connectivity", "check_slm_health"}),
}
