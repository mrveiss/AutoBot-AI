# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The heartbeat scheduler must not queue behind the knowledge-base init (#20232).

Phase 2 ran the knowledge base first, and its first call can download an embedding model
(about 6 minutes on a scratch install), so no cron dispatch ran until it finished. The
scheduler, the routine scheduler and the session recovery that precedes them import only
Redis, the database and LLC modules -- none reads ``app.state`` -- so they have no reason to
wait. Read by path like ``vector_reconciler_is_wired_17548_test.py``: ``lifespan.py`` cannot
be imported on a bare checkout.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_LIFESPAN = repo_root() / "autobot-backend/initialization/lifespan.py"
_EARLY = ("_recover_agent_sessions", "_init_heartbeat_scheduler", "_init_llc_routine_scheduler")


def _phase2_call_order() -> list[str]:
    tree = ast.parse(_LIFESPAN.read_text(encoding="utf-8"))
    func = next(
        n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "initialize_background_services"
    )
    calls = [n for n in ast.walk(func) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    return [c.func.id for c in sorted(calls, key=lambda c: (c.lineno, c.col_offset))]


def test_scheduling_starts_before_the_knowledge_base():
    order = _phase2_call_order()
    kb = order.index("_init_knowledge_base")
    for name in _EARLY:
        assert name in order, f"{name} is no longer started in phase 2"
        assert order.index(name) < kb, f"{name} starts after _init_knowledge_base, behind its model download"


def test_session_recovery_still_precedes_the_heartbeat_scheduler():
    order = _phase2_call_order()
    assert order.index("_recover_agent_sessions") < order.index("_init_heartbeat_scheduler")


def test_the_scheduler_starts_before_the_reconciler_that_repairs_it():
    order = _phase2_call_order()
    assert order.index("_init_llc_routine_scheduler") < order.index("start_background_workers")
