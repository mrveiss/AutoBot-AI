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
stated rather than silently exempted. The 27 `MIGRATE` AsyncSession doubles that were here moved onto
`FakeAsyncSession` in #18955 and their lines are gone; what remains is not a session (or is the kept exception).
"""

from __future__ import annotations

_B = "autobot-backend/"
_S = "autobot-slm-backend/"

_PIPE = "NOT-A-SESSION: Redis pipeline double (`execute` flushes the pipeline); caught by the name-only matcher"
_CHROMA = "NOT-A-SESSION: Chroma collection double (`add`); caught by the name-only matcher"
_CURSOR = "NOT-A-SESSION: DB-API cursor/connection double for the raw-SQL migration runner (sync `execute`/`commit`)"
_CLI_CURSOR = "NOT-A-SESSION: DB-API cursor/connection double for autobot-admin.py's sync two-database write (#18672)"
_SKILL = "NOT-A-SESSION: skill test double; `execute` is the skill hook, not a session call"

ALLOWLIST: dict[str, str] = {
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
    _B
    + "llc/tests/test_status_comment_is_stored_16017.py::test_a_failed_commit_leaves_no_comment_behind::_FailingCommitSession": "KEEP-EXCEPTION: proxy over a real aiosqlite session, not a stand-in for one",  # noqa: E501
    _B + "memory/verbatim_symbolic_test.py::<module>::_FakePipe": _PIPE,  # noqa: E501
    _B
    + "services/fact_extraction_service_serving_18820_test.py::<module>::_Pipe": _PIPE,  # noqa: E501  train 47: #18945 landed this Redis-pipeline double while #18933 widened the matcher to `execute`
    _B + "services/feature_flags_enforcement_write_test.py::<module>::_FakePipeline": _PIPE,  # noqa: E501
    _B + "services/pricing_refresh_test.py::<module>::_DictPipeline": _PIPE,  # noqa: E501
    _B + "skills/trigger_dispatcher_test.py::<module>::_SecondListener": _SKILL,  # noqa: E501
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
    _B + "services/feature_flags_cache_18998_test.py::<module>::_Pipe": _PIPE,  # noqa: E501
    _S + "migrations/add_audit_logs_canonical_columns_test.py::<module>::_Cursor": _CURSOR,  # noqa: E501
    _S + "migrations/runner_deferral_test.py::<module>::_Cursor": _CURSOR,  # noqa: E501
    _S + "tests/services/test_admin_password_epoch_18672.py::<module>::_Conn": _CLI_CURSOR,  # noqa: E501
    _S + "tests/services/test_admin_password_epoch_18672.py::<module>::_Cursor": _CLI_CURSOR,  # noqa: E501
    _S + "migrations/seed_agents_test.py::<module>::_FakeConnection": _CURSOR,  # noqa: E501
    _S + "migrations/seed_agents_test.py::<module>::_FakeCursor": _CURSOR,  # noqa: E501
    _S + "migrations/utils_test.py::<module>::_FakeCursor": _CURSOR,  # noqa: E501
}

#: The ceiling. Lower it with the list; never raise it.
FROZEN_TOTAL = 31
