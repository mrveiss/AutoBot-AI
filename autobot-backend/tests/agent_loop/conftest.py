# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
conftest.py for agent_loop unit tests.

autobot-backend/conftest.py stubs ``agent_loop`` (and sub-modules) to break
the orchestration → agent_loop import chain for orchestration-layer tests.
Tests in this directory need the *real* implementations.

We replace any remaining stub with the real module at conftest load time and
restore what we replaced via ``pytest_unconfigure`` so sibling test
directories are unaffected.

This file must never swap the *package identity* (#13162).  It used to pop
every ``agent_loop*`` key out of ``sys.modules`` and plant a fresh
``agent_loop`` module, which is fatal in a full-suite run: pytest imports this
conftest during collection, long after ``autobot-backend/agent_loop/tests/``
has already been collected and bound ``AgentLoop`` /
``PreActionVerifier`` from the *previous* module objects.  Every
``patch("agent_loop.loop.X")`` in those files then resolved against the new
package and silently patched a different (or mock) object, so the real
module's globals stayed untouched — an inert patch.  That is the same hazard
``tests/orchestration/test_causal_error_recovery.py`` documents for this exact
package ("popping the parent forced a full real ``agent_loop/__init__``
re-import that replaced the package identity mid-session").

The root conftest already plants ``agent_loop`` with a REAL ``__path__`` and
real-loads ``agent_loop.loop`` / ``agent_loop.think_tool`` (#11153), so in
practice this file only has to fill in whatever is still a stub.

Issue #6627, #13162.
"""

from pathlib import Path

from autobot_shared.logging_manager import get_logger
from testkit.module_stubs import StubSet

_BACKEND = Path(__file__).parent.parent.parent  # .../autobot-backend
_AL_DIR = _BACKEND / "agent_loop"

_logger = get_logger(__name__)
_stubs = StubSet()


def _load_best_effort(name: str, rel: str) -> None:
    """Load *name*, tolerating an import failure but never hiding it.

    Some of these pull heavy transitive deps (loop.py reaches events/planner/
    tools) that a lean environment may not satisfy; the tests mock them, so a
    failure here is survivable. Survivable is not the same as invisible: the
    previous version swallowed the exception and stashed it in ``sys.modules``
    under an invented ``_stagnation_load_err_*`` key, which both hid the error
    and leaked a key nothing would ever clean up (#13575).

    ``StubSet.real_load`` removes the half-executed module and re-raises, so the
    only thing left to decide here is whether to continue — and to say why.
    """
    try:
        _stubs.real_load(name, _BACKEND / rel)
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        _logger.warning("agent_loop conftest: %s could not be real-loaded (%s); tests must mock it", name, exc)


# adopt_package, NOT install_package: the root conftest already planted
# ``agent_loop``, and replacing that object is the identity swap #13551 traced.
_stubs.adopt_package("agent_loop", _AL_DIR)

# Dependency order (fingerprint and types have no heavy local deps).
_load_best_effort("agent_loop.fingerprint", "agent_loop/fingerprint.py")
_load_best_effort("agent_loop.types", "agent_loop/types.py")
_load_best_effort("agent_loop.think_tool", "agent_loop/think_tool.py")
_load_best_effort("agent_loop.slack_hook", "agent_loop/slack_hook.py")
_load_best_effort("agent_loop.loop", "agent_loop/loop.py")

# MVA-1407: belief state + extractors package.
_stubs.adopt_package("agent_loop.extractors", _AL_DIR / "extractors")
_load_best_effort("agent_loop.extractors.read_file", "agent_loop/extractors/read_file.py")
_load_best_effort("agent_loop.extractors.run_command", "agent_loop/extractors/run_command.py")
_load_best_effort("agent_loop.extractors.web_search", "agent_loop/extractors/web_search.py")
_stubs.real_load_package("agent_loop.extractors", _AL_DIR / "extractors" / "__init__.py", _AL_DIR / "extractors")
_load_best_effort("agent_loop.belief_state", "agent_loop/belief_state.py")


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Undo exactly what this file changed, and nothing else.

    StubSet.restore() reverses sys.modules entries, parent bindings and __path__
    mutations together. The hand-rolled version let ``_ADDED`` and ``_SAVED``
    overlap, so popping the added key and then restoring the saved one put a
    synthetic ``agent_loop.extractors`` straight back (#13575).
    """
    _stubs.restore()
