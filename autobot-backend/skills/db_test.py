# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for the skills DB engine manager (Issue #13082).

Reproduces the self-deadlock: ``get_session_factory()`` previously acquired
its own non-reentrant ``threading.Lock`` and, while still holding it, called
``get()``, which tried to acquire the *same* lock again on the same thread.
On the very first call in a process (before ``initialization/lifespan.py``
has warmed up the engine), this was an unconditional self-deadlock with no
timeout anywhere in the path. Reproduced against the real, unmocked path via
``skills/governance_test.py::test_semi_auto_requires_review`` (#10691
baseline audit).
"""

import threading

from skills.db import _SkillsEngineManager

# Generous but bounded: a genuine deadlock never returns, so any finite
# timeout proves the hang; this just avoids a slow CI run on the passing path.
_DEADLOCK_DETECTION_TIMEOUT_SECONDS = 5


def test_get_session_factory_does_not_deadlock_on_cold_start():
    """First-ever call to get_session_factory() must return, not hang.

    Uses a *fresh* manager instance (not the module-level singleton, which
    other tests may have already warmed up) to reliably reproduce the
    cold-start condition: both ``_engine`` and ``_session_factory`` are
    ``None`` when ``get_session_factory()`` acquires ``self._lock`` and
    (previously) re-entered it via ``self.get()``.
    """
    manager = _SkillsEngineManager()
    result: dict = {}

    def call_get_session_factory() -> None:
        try:
            result["factory"] = manager.get_session_factory()
        except Exception as e:  # pragma: no cover - defensive, not the bug under test
            result["error"] = e

    thread = threading.Thread(target=call_get_session_factory, daemon=True)
    thread.start()
    thread.join(timeout=_DEADLOCK_DETECTION_TIMEOUT_SECONDS)

    assert not thread.is_alive(), (
        "get_session_factory() deadlocked (Issue #13082): the non-reentrant "
        "threading.Lock was re-entered on the same thread via self.get()."
    )
    assert "error" not in result, f"Unexpected error: {result.get('error')}"
    assert result["factory"] is not None
