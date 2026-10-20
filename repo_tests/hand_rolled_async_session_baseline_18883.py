# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frozen allowlist of the hand-rolled fake async sessions that exist today (#18883).

Each key is `<repo path>::<enclosing function>::<class>` (`<module>` at module level; `#2` for a
second same-named class in one function); the value is why it is still hand-rolled. The list may
only SHRINK: a new match fails the guard, and an entry whose class was migrated to
`testkit.fake_async_session.FakeAsyncSession` (or left the tree) fails it too until the line is
deleted. `FROZEN_TOTAL` caps the length.

The guard's matcher was widened (any of commit/refresh/flush/execute/add, sync or async, assigned
or defined, plus `type(...)` fakes, plus `testkit/` helpers), which is the ONLY reason this list
grew from 1 to 53: the extra 52 already existed. The matcher is name-based, so some are not
sessions at all (Redis pipelines, Chroma collections, DB-API cursors); they are frozen with that
stated rather than silently exempted, and the `MIGRATE` ones are follow-up work for #18883.
"""

from __future__ import annotations

_B = "autobot-backend/"
_S = "autobot-slm-backend/"

_PIPE = "NOT-A-SESSION: Redis pipeline double (`execute` flushes the pipeline); caught by the name-only matcher"
_CHROMA = "NOT-A-SESSION: Chroma collection double (`add`); caught by the name-only matcher"
_CURSOR = "NOT-A-SESSION: DB-API cursor/connection double for the raw-SQL migration runner (sync `execute`/`commit`)"
_CLI_CURSOR = "NOT-A-SESSION: DB-API cursor/connection double for autobot-admin.py's sync two-database write (#18672)"
_SKILL = "NOT-A-SESSION: skill test double; `execute` is the skill hook, not a session call"
_GETEXEC = "MIGRATE: session double answering `get` and `execute`; FakeAsyncSession(on_get=, results=) covers both"
_COUNTING = "MIGRATE: counting wrapper over the local execute-only `_FakeSession`; migrates with it"
_EXEC = "MIGRATE: execute-only AsyncSession double; FakeAsyncSession(results=/default_result=) covers it"

ALLOWLIST: dict[str, str] = {
    _B + "api/agent_presence_test.py::<module>::_FakeMembershipSession": _EXEC,  # noqa: E501
    _B + "api/analytics_embedding_patterns_stats_keys_test.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B + "api/analytics_llm_patterns_test.py::<module>::_FakePipe": _PIPE,  # noqa: E501
    _B + "api/knowledge_by_category_payload_test.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B + "chat_history/context_overflow_token_keys_test.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B
    + "code_intelligence/bug_predictor_source_scoping_test.py::<module>::_FakeChromaCollection": _CHROMA,  # noqa: E501
    _B + "tests/fixtures/rag_cache_fakes.py::<module>::FakeCollection": _CHROMA,  # noqa: E501
    _B
    + "code_intelligence/pattern_analysis/clear_patterns_source_scoping_test.py::<module>::_FakeChromaCollection": _CHROMA,  # noqa: E501
    _B
    + "code_intelligence/pattern_analysis/source_scoping_test.py::<module>::_FakeChromaCollection": _CHROMA,  # noqa: E501
    _B + "llc/kb/capability_indexer_wiring_test.py::<module>::_FakeSession": _EXEC,  # noqa: E501
    _B + "llc/tests/test_heartbeat_idle_short_circuit_17726.py::<module>::_RecordingSession": _EXEC,  # noqa: E501
    _B + "llc/tests/test_portability_reporting_lines_14811.py::<module>::_FakeSession": _EXEC,  # noqa: E501
    _B
    + "llc/tests/test_status_comment_is_stored_16017.py::test_a_failed_commit_leaves_no_comment_behind::_FailingCommitSession": "KEEP-EXCEPTION: proxy over a real aiosqlite session, not a stand-in for one",  # noqa: E501
    _B + "llc/tests/test_work_item_relations_async.py::<module>::_FakeSession": _EXEC,  # noqa: E501
    _B
    + "llc/tests/test_work_item_relations_async.py::test_relations_to_list_single_query_for_many_relations::_CountingSession": _COUNTING,  # noqa: E501
    _B + "memory/verbatim_symbolic_test.py::<module>::_FakePipe": _PIPE,  # noqa: E501
    _B
    + "services/fact_extraction_service_serving_18820_test.py::<module>::_Pipe": _PIPE,  # noqa: E501  train 47: #18945 landed this Redis-pipeline double while #18933 widened the matcher to `execute`
    _B + "protocols/agent_presence_feeds_test.py::<module>::_FakeSession": _EXEC,  # noqa: E501
    _B + "services/feature_flags_enforcement_write_test.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B + "services/orphan_repair_test.py::<module>::_Users": _GETEXEC,  # noqa: E501
    _B + "services/pricing_refresh_test.py::<module>::_DictPipeline": _PIPE,  # noqa: E501
    _B + "services/secrets_coordinator_scope_16982_test.py::<module>::_FakeSession": _GETEXEC,  # noqa: E501
    _B + "skills/trigger_dispatcher_test.py::<module>::_SecondListener": _SKILL,  # noqa: E501
    _B + "tests/coordination/test_issue_claims_credential.py::<module>::_DialectSession": _EXEC,  # noqa: E501
    _B + "tests/coordination/test_shared_runtime_bag.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B
    + "tests/coordination/test_shared_runtime_bag.py::test_update_raises_after_max_retries::_AlwaysFailPipeline": _PIPE,  # noqa: E501
    _B + "tests/coordination/test_shared_runtime_bag_integration.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B + "tests/helpers/fake_redis.py::<module>::_Pipeline": _PIPE,  # noqa: E501
    _B + "tests/llm_shared/test_token_budget.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B + "tests/memory_graph/_owner_scope_doubles.py::<module>::_Pipe": _PIPE,  # noqa: E501
    _B + "tests/test_background_vectorization_pending_set.py::<module>::_FakePipe": _PIPE,  # noqa: E501
    _B + "tests/test_cross_worker_registries.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B
    + "utils/long_running_operations/checkpoint_manager_pickle_security_test.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _S + "api/nodes_role_declaration_test.py::<module>::_FakeDb": _EXEC,  # noqa: E501
    _S + "migrations/add_audit_logs_canonical_columns_test.py::<module>::_Cursor": _CURSOR,  # noqa: E501
    _S + "migrations/runner_deferral_test.py::<module>::_Cursor": _CURSOR,  # noqa: E501
    _S + "tests/services/test_admin_password_epoch_18672.py::<module>::_Conn": _CLI_CURSOR,  # noqa: E501
    _S + "tests/services/test_admin_password_epoch_18672.py::<module>::_Cursor": _CLI_CURSOR,  # noqa: E501
    _S + "migrations/seed_agents_test.py::<module>::_FakeConnection": _CURSOR,  # noqa: E501
    _S + "migrations/seed_agents_test.py::<module>::_FakeCursor": _CURSOR,  # noqa: E501
    _S + "migrations/utils_test.py::<module>::_FakeCursor": _CURSOR,  # noqa: E501
    _S + "services/node_capability_test.py::<module>::_Db": _EXEC,  # noqa: E501
    _S + "services/node_gpu_test.py::<module>::_Db": _EXEC,  # noqa: E501
    _S + "tests/api/test_apply_secrets.py::<module>::_FakeDB": _EXEC,  # noqa: E501
    _S
    + "tests/api/test_code_sync_self_update_colocated_limit_15475.py::<module>::_FakeSessionCtx": _EXEC,  # noqa: E501
    _S + "tests/api/test_collect_outdated_node_ids.py::_db_service_mock::_FakeCtx": _EXEC,  # noqa: E501
    _S + "tests/api/test_fleet_services_delegates_17856.py::<module>::_FakeDb": _EXEC,  # noqa: E501
    _S + "tests/api/test_gpu_nodes_route_16281.py::<module>::_Db": _EXEC,  # noqa: E501
    _S
    + "tests/api/test_health_redis_14299.py::test_degrades_when_redis_is_unhealthy_even_if_db_is_fine::_FakeDB": _EXEC,  # noqa: E501
    _S
    + "tests/api/test_health_redis_14299.py::test_healthy_when_both_db_and_redis_agree::_FakeDB": _EXEC,  # noqa: E501
    _S + "tests/api/test_node_post_sync_17455.py::<module>::_Db": _EXEC,  # noqa: E501
    _S + "tests/api/test_service_logs_timeout_vs_empty_15640.py::<module>::_NodeReturningSession": _EXEC,  # noqa: E501
    _S + "tests/api/test_slm_deployed_commit_marker_12202.py::_db_service_mock::_FakeCtx": _EXEC,  # noqa: E501
    _S + "tests/services/schedule_executor_stored_cron_18449_test.py::<module>::_Session": _EXEC,  # noqa: E501
    _S + "tests/services/test_auth_revocation_store_18663.py::<module>::_FakeSession": _EXEC,  # noqa: E501
    _S + "tests/services/test_security_posture_auditor.py::<module>::_FakeSession": _EXEC,  # noqa: E501
    _S + "tests/test_secrets_backup_status_route_18281.py::<module>::_DB": _EXEC,  # noqa: E501
}

#: The ceiling. Lower it with the list; never raise it.
FROZEN_TOTAL = 57
