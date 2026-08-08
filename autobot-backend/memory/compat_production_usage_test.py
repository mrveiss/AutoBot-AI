# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`memory/compat.py` has live production callers (#13690).

#13690 was filed on the premise that this module had none. That was wrong: the
grep looked for `memory.compat`, and both production callers import through the
package re-export at `memory/__init__.py:42`, which leaves no textual trace of
the originating module.

`tests/memory/test_compat_singletons.py` covers the factories in isolation.
These pin the *production* coupling, so the next audit that considers this
module dead has to contend with a failing test rather than a silent grep.
"""

import inspect

import pytest


class TestLiveProductionCallers:
    def test_orchestrator_constructs_the_legacy_wrapper(self):
        """orchestrator.py:142 — the live consumer the original grep missed."""
        import orchestrator

        source = inspect.getsource(orchestrator)
        assert "LongTermMemoryManager()" in source
        assert "from memory import LongTermMemoryManager" in source

    def test_task_tracker_uses_the_canonical_factory(self):
        """task_execution_tracker.py:52 — get_memory_manager is not legacy."""
        import task_execution_tracker

        source = inspect.getsource(task_execution_tracker)
        assert "get_memory_manager" in source

    def test_the_factories_are_re_exported_from_the_package(self):
        """This re-export is why a `memory.compat` grep finds nothing."""
        import memory

        assert memory.get_memory_manager is not None
        assert memory.LongTermMemoryManager is not None


class TestLifecycleSurfaceIsWhatOrchestratorNeeds:
    """orchestrator calls exactly two methods; both must keep working.

    #13688 changed the signatures of the data-plane methods this wrapper wraps.
    Nothing broke precisely because the live consumer touches neither — these
    assert that stays true.
    """

    @pytest.mark.parametrize("method", ["initialize", "cleanup"])
    def test_lifecycle_methods_take_no_owner_argument(self, method):
        from memory.compat import LongTermMemoryManager

        params = inspect.signature(getattr(LongTermMemoryManager, method)).parameters
        assert "user_id" not in params, f"{method} is lifecycle, not a data-plane call"


class TestDataPlaneWrappersStayTenanted:
    """The dormant methods must not lose their scoping while unused (#13688).

    They have no production callers today. If one appears it should inherit the
    tenancy rather than re-open the gap #13688 closed.
    """

    @pytest.mark.parametrize(
        "method",
        ["store_memory", "retrieve_memories", "search_by_metadata", "search_relevant_context"],
    )
    def test_owner_scope_is_required_and_keyword_only(self, method):
        from memory.compat import LongTermMemoryManager

        params = inspect.signature(getattr(LongTermMemoryManager, method)).parameters
        assert "user_id" in params, f"{method} lost its owner scope"
        assert params["user_id"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["user_id"].default is inspect.Parameter.empty, "scope must be required"
