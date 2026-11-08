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
sessions at all (Chroma collections, DB-API cursors); they are frozen with that
stated rather than silently exempted. The 18 Redis pipeline doubles that were here moved onto
`testkit.fake_redis_pipeline` in #18991 and their lines are gone; `one_fake_redis_pipeline_18991_test` guards that.
The 27 `MIGRATE` AsyncSession doubles that were here moved onto
`FakeAsyncSession` in #18955 and their lines are gone; what remains is not a session (or is the kept exception).
"""

from __future__ import annotations

_B = "autobot-backend/"
_S = "autobot-slm-backend/"

_CHROMA = "NOT-A-SESSION: Chroma collection double (`add`); caught by the name-only matcher"
_CURSOR = "NOT-A-SESSION: DB-API cursor/connection double for the raw-SQL migration runner (sync `execute`/`commit`)"
_CLI_CURSOR = "NOT-A-SESSION: DB-API cursor/connection double for autobot-admin.py's sync two-database write (#18672)"
_SKILL = "NOT-A-SESSION: skill test double; `execute` is the skill hook, not a session call"

ALLOWLIST: dict[str, str] = {
    _B
    + "code_intelligence/bug_predictor_source_scoping_test.py::<module>::_FakeChromaCollection": _CHROMA,  # noqa: E501
    _B + "tests/fixtures/rag_cache_fakes.py::<module>::FakeCollection": _CHROMA,  # noqa: E501
    _B
    + "code_intelligence/pattern_analysis/clear_patterns_source_scoping_test.py::<module>::_FakeChromaCollection": _CHROMA,  # noqa: E501
    _B
    + "code_intelligence/pattern_analysis/source_scoping_test.py::<module>::_FakeChromaCollection": _CHROMA,  # noqa: E501
    _B
    + "llc/tests/test_status_comment_is_stored_16017.py::test_a_failed_commit_leaves_no_comment_behind::_FailingCommitSession": "KEEP-EXCEPTION: proxy over a real aiosqlite session, not a stand-in for one",  # noqa: E501
    _B + "skills/trigger_dispatcher_test.py::<module>::_SecondListener": _SKILL,  # noqa: E501
    _S + "migrations/add_audit_logs_canonical_columns_test.py::<module>::_Cursor": _CURSOR,  # noqa: E501
    _S + "migrations/runner_deferral_test.py::<module>::_Cursor": _CURSOR,  # noqa: E501
    _S + "tests/services/test_admin_password_epoch_18672.py::<module>::_Conn": _CLI_CURSOR,  # noqa: E501
    _S + "tests/services/test_admin_password_epoch_18672.py::<module>::_Cursor": _CLI_CURSOR,  # noqa: E501
    _S + "migrations/seed_agents_test.py::<module>::_FakeConnection": _CURSOR,  # noqa: E501
    _S + "migrations/seed_agents_test.py::<module>::_FakeCursor": _CURSOR,  # noqa: E501
    _S + "migrations/utils_test.py::<module>::_FakeCursor": _CURSOR,  # noqa: E501
}

#: The ceiling. Lower it with the list; never raise it.
FROZEN_TOTAL = 13
