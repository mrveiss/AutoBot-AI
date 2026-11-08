# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hand-written test-file-name rules still outside `autobot_shared.testfile_names` (#21078). SHRINK-ONLY.

Each entry is a repo-relative path and how many rule literals it holds (see the guard for what counts).
The guard fails when a file is missing from here or holds more than listed, and when it holds fewer
(lower the number -- never raise it). Three groups:

* NOT_A_FILE_NAME_PREDICATE -- the literal answers another question (each reason beside the entry);
* DELIBERATELY_NOT_CANONICAL -- a different rule on purpose (reason beside the entry);
* NOT_YET_MIGRATED -- a hand-written copy beyond the sites #21078 enumerated, left so the PR stays under the
  100-file ceiling. Each is to move to `is_test_filename` (keeping its directory rule); the follow-up is
  tracked in #21161.

The totals are pinned by `repo_tests/test_name_predicate_single_home_21078_test.py`
(`MAX_ENTRIES`, `MAX_SITES`): adding an entry or raising a count fails there as well as in the guard.
"""

# Deliberately not canonical, and invisible to the detector so it has no entry below:
# `pipeline-scripts/audit_unwired_trackers.py` (`TEST_PATH_FRAGMENTS`, `is_test_path`) matches `_test.` and `.test.`
# anywhere in a path, any extension, and leaves out `/test_` on purpose because pytest `tmp_path` directories embed
# `test_<name>/`; the canonical base-name rule would change what it audits. The reason is recorded here rather than
# in the file because that file fails its flake8 hook today (#21164), so editing it would trip the hook.

BASELINE: dict[str, int] = {
    # --- NOT_A_FILE_NAME_PREDICATE ---
    # derives the tested module from `x_test.py`, a name-to-module mapping, not a test-file test
    "autobot-backend/code_intelligence/testing_pattern_analyzer.py": 1,
    # strips a TEST FUNCTION name's `_test` suffix; not a file name
    "autobot-backend/code_analysis/src/testing_coverage_analyzer.py": 1,
    # `_test.py` here selects files whose source lines are not read; its own question
    "tools/lint/check_no_local_schemas.py": 1,
    # identifies the ONE `conftest.py` that installed a module (identity, not a class)
    "repo_tests/sys_modules_leak_guard.py": 2,
    # classifies module NAMES during collection by `_test`/`_examples` suffix, not file names
    "autobot-backend/conftest.py": 1,
    # Deliberately not canonical: the rule scans `conftest.py` today, and migrating to the canonical rule would
    # silently exempt it (#21078). Nothing in its own test requires that; this entry is what keeps it deliberate.
    "tools/lint/canonical/rules/py_celery_private_event_loop.py": 1,
    # --- NOT_YET_MIGRATED ---
    # Pre-commit hook runs under the system interpreter, which autobot_shared's import-time floor refuses (#20903);
    # migrate once the hook runs on the project interpreter.
    "tools/lint/check_no_direct_redis.py": 2,
    "autobot-backend/agents/agent_orchestration/librarian_user_19591_test.py": 1,
    "autobot-backend/api/codebase_analytics/endpoints/duplicates_source_resolution_17982_test.py": 1,
    "autobot-backend/auth_rbac_admin_guard_test.py": 1,
    "autobot-backend/chat_history/add_message_call_sites_test.py": 1,
    "autobot-backend/code_analysis/src/analyzer_construction_15914_test.py": 1,
    "autobot-backend/config/logging_key_parity_test.py": 1,
    "autobot-backend/config/logging_reader_effect_parity_test.py": 1,
    "autobot-backend/initialization/system_knowledge_import_19347_test.py": 1,
    "autobot-backend/integrations/integration_unknown_action_contract_test.py": 1,
    "autobot-backend/knowledge/connectors/egress_policy_test.py": 1,
    "autobot-backend/llc/tests/test_activity_record_commit_scope_20101.py": 1,
    "autobot-backend/llc/tests/test_event_wake_guard_19582.py": 1,
    "autobot-backend/llc/tests/test_every_service_has_an_activity_log_20101.py": 1,
    "autobot-backend/llc/tests/test_kb_collection_names_19519.py": 1,
    "autobot-backend/llc/tests/test_kb_collections_lazy_19725.py": 2,
    "autobot-backend/security/prompt_injection_detector_strict_mode_test.py": 1,
    "autobot-backend/services/rag_single_definition_19280_test.py": 1,
    "autobot-backend/tests/agents/test_declared_scopes_guard.py": 1,
    "autobot-backend/tests/api/test_response_helper_footgun.py": 1,
    "autobot-backend/tests/memory_graph/test_graph_callers_exist_18414.py": 1,
    "autobot-backend/tests/migrations/test_schema_authority.py": 1,
    "autobot-backend/tests/services/test_scheduler_registry.py": 1,
    "autobot-backend/tests/test_startup_imports.py": 3,
    "autobot-slm-backend/services/node_ssh_password_20046_test.py": 1,
    "autobot-slm-backend/tests/api/test_require_permission.py": 1,
    "autobot-slm-backend/tests/api/test_resolve_deletion_guard_13851.py": 1,
    "autobot-slm-backend/tests/services/one_deploy_path_19352_test.py": 1,
    "autobot-slm-backend/tests/services/test_enrollment_keeps_password_19483_test.py": 1,
    "autobot-slm-backend/tests/test_canonical_ssh_key.py": 1,
    "autobot_shared/plugin_sdk/plugin_load_visibility_test.py": 1,
    "autobot_shared/slm_rest_url_test.py": 1,
    "repo_tests/ai_line_single_policy_18430_test.py": 1,
    "repo_tests/anti_pattern_type_emitted_18189_test.py": 1,
    "repo_tests/audit_write_failure_counted_test.py": 1,
    "repo_tests/audit_writer_single_source_17225_test.py": 1,
    "repo_tests/background_task_retention_ratchet_test.py": 1,
    "repo_tests/chat_history_async_calls_awaited_18316_test.py": 1,
    "repo_tests/chat_single_delete_implementation_18316_test.py": 1,
    "repo_tests/compat_module_needs_importer_18552_test.py": 1,
    "repo_tests/conftest_stub_no_autovivify_test.py": 1,
    "repo_tests/conftest_stubset_primitives_13596_test.py": 1,
    "repo_tests/connector_redaction_guard_test.py": 1,
    "repo_tests/container_hardening_single_source_17267_test.py": 1,
    "repo_tests/conversation_turn_single_store_18293_test.py": 1,
    "repo_tests/credential_vault_resolution_guard_test.py": 1,
    "repo_tests/data_db_path_single_source_test.py": 1,
    "repo_tests/defined_twice_18094_test.py": 2,
    "repo_tests/direct_secrets_service_callers_17773_test.py": 1,
    "repo_tests/egress_default_guard_17576_test.py": 2,
    "repo_tests/embedding_model_one_resolver_19377_test.py": 1,
    "repo_tests/env_var_bare_cast_test.py": 1,
    "repo_tests/file_type_sets_one_home_19339_test.py": 2,
    "repo_tests/github_api_single_module_15411_test.py": 1,
    "repo_tests/global_channel_carries_no_tenant_payload_17354_test.py": 1,
    "repo_tests/hardcoded_ui_literal_ratchet_12732_test.py": 3,
    "repo_tests/hosted_model_literal_guard_15501_test.py": 1,
    "repo_tests/infra_libs_test_wiring_guard_15051_test.py": 1,
    "repo_tests/infra_monitoring_import_path_15643_test.py": 1,
    "repo_tests/install_and_code_sync_modes_19503_test.py": 1,
    "repo_tests/internal_paths_denied_at_edge_20046_test.py": 1,
    "repo_tests/kb_admin_read_bypass_guard_test.py": 2,
    "repo_tests/kb_content_redaction_chokepoint_guard_test.py": 1,
    "repo_tests/kb_populate_one_home_19339_test.py": 1,
    "repo_tests/kb_read_visibility_guard_test.py": 2,
    "repo_tests/kb_write_chokepoint_19517_test.py": 2,
    "repo_tests/knowledge_metadata_parse_canonical_18220_test.py": 1,
    "repo_tests/lint/canonical/rules/test_py_celery_private_event_loop.py": 2,
    "repo_tests/llc_scheduler_task_registration_16817_test.py": 1,
    "repo_tests/marker_suite_root_coverage_test.py": 1,
    "repo_tests/model_revision_pinning_enforced_17804_test.py": 1,
    "repo_tests/model_tier_single_definition_15502_test.py": 1,
    "repo_tests/monitoring_launcher_single_17906_test.py": 1,
    "repo_tests/no_created_by_admin_literal_test.py": 1,
    "repo_tests/no_doubled_api_prefix_18722_test.py": 1,
    "repo_tests/no_feature_restricted_by_tier_19984_test.py": 1,
    "repo_tests/no_literal_secret_default_16299_test.py": 1,
    "repo_tests/oauth_bundle_no_app_secret_13630_test.py": 1,
    "repo_tests/one_anthropic_message_split_16815_test.py": 1,
    "repo_tests/one_backoff_formula_15402_test.py": 2,
    "repo_tests/one_bm25_formula_18183_test.py": 1,
    "repo_tests/one_brand_mark_and_announcer_18240_test.py": 2,
    "repo_tests/one_circuit_breaker_18554_test.py": 2,
    "repo_tests/one_claim_model_18086_test.py": 1,
    "repo_tests/one_claim_registry_16653_test.py": 1,
    "repo_tests/one_content_digest_15722_test.py": 1,
    "repo_tests/one_doc_indexer_18129_test.py": 1,
    "repo_tests/one_fact_read_authorization_18184_test.py": 1,
    "repo_tests/one_gateway_adapter_package_15024_test.py": 3,
    "repo_tests/one_hybrid_search_17599_test.py": 1,
    "repo_tests/one_internal_api_key_reader_17856_test.py": 1,
    "repo_tests/one_knowledge_base_store_18122_test.py": 2,
    "repo_tests/one_permission_gate_18263_test.py": 1,
    "repo_tests/one_rbac_middleware_18088_test.py": 1,
    "repo_tests/one_semantic_chunker_14485_test.py": 1,
    "repo_tests/one_serving_predicate_18820_test.py": 2,
    "repo_tests/one_session_ownership_validator_14016_test.py": 1,
    "repo_tests/one_session_scope_15068_test.py": 1,
    "repo_tests/one_shared_authority_callers_17855_test.py": 1,
    "repo_tests/one_ssh_restart_executor_18186_test.py": 1,
    "repo_tests/one_sync_command_runner_18180_test.py": 1,
    "repo_tests/optimization_taxonomies_13049_test.py": 2,
    "repo_tests/pr_comment_upsert_12984_test.py": 1,
    "repo_tests/provenance_accessor_17527_test.py": 1,
    "repo_tests/provider_key_env_reads_route_through_vault_18094_test.py": 2,
    "repo_tests/redaction_concept_census_test.py": 2,
    "repo_tests/redis_keys_runtime_18999_test.py": 2,
    "repo_tests/remote_command_quoting_18359_test.py": 1,
    "repo_tests/scan_helpers_vacuity_test.py": 1,
    "repo_tests/sentence_model_pinned_19430_test.py": 1,
    "repo_tests/sigterm_grace_one_home_19340_test.py": 1,
    "repo_tests/single_attribute_writer_18240_test.py": 2,
    "repo_tests/slm_backend_no_embedded_playbook_18606_test.py": 1,
    "repo_tests/slm_frontend_calls_reach_served_routes_test.py": 2,
    "repo_tests/slm_logs_no_database_url_18664_test.py": 1,
    "repo_tests/slm_node_enum_members_exist_test.py": 1,
    "repo_tests/store_fact_chokepoint_guard_test.py": 2,
    "repo_tests/symbol_fork_ratchet_17312_test.py": 2,
    "repo_tests/test_agent_venv_isolation_14278.py": 2,
    "repo_tests/test_dockerignore_test_file_coverage_14127.py": 1,
    "repo_tests/test_module_path_anchors_15181_test.py": 2,
    "repo_tests/tool_effect_single_source_18294_test.py": 2,
    "repo_tests/torch_pair_one_home_19330_test.py": 1,
    "repo_tests/transformers_resume_download_guard_test.py": 1,
    "repo_tests/uninstall_covers_role_components_18653_test.py": 2,
    "repo_tests/websocket_subprotocol_echo_guard_test.py": 1,
    "repo_tests/whisper_one_path_17780_test.py": 2,
    "repo_tests/with_error_handling_single_definition_test.py": 1,
    "repo_tests/workflow_planner_deprecation_test.py": 1,
}
