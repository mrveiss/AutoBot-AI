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

import importlib.util
import sys
import types
from pathlib import Path

_BACKEND = Path(__file__).parent.parent.parent  # .../autobot-backend
_AL_DIR = _BACKEND / "agent_loop"

# Only the entries this file actually replaces are saved — restoring keys we
# never touched is what made the old save/pop/restore cycle destructive.
_SAVED: dict[str, object] = {}
_ADDED: set = set()


def _bind_on_parent(full_name: str, mod: object) -> None:
    """Bind *mod* as an attribute of its parent package.

    Load-bearing for ``unittest.mock.patch`` (#11532/#11618): it resolves
    ``"agent_loop.loop.X"`` via ``getattr(sys.modules["agent_loop"], "loop")``,
    NOT via ``sys.modules["agent_loop.loop"]``.  A module registered in
    ``sys.modules`` by hand — as ``_load_real`` does — never gets that bind
    from the import machinery, so without this every such patch target either
    raised ``AttributeError`` or (against the root conftest's catch-all
    package stub) silently patched a MagicMock.
    """
    parent, _, child = full_name.rpartition(".")
    if parent and parent in sys.modules:
        setattr(sys.modules[parent], child, mod)


def _load_real(full_name: str, rel: str) -> None:
    """Register the REAL module for *full_name*, unless it already is real.

    Re-executing a module that is already loaded from this same file builds a
    second set of class objects while every importer keeps referencing the
    first — the identity split that #13162 traced.  An already-real entry is
    therefore left alone and only (re)bound on its parent.
    """
    path = _BACKEND / rel
    existing = sys.modules.get(full_name)
    if existing is not None and getattr(existing, "__file__", None) == str(path):
        _bind_on_parent(full_name, existing)
        return
    spec = importlib.util.spec_from_file_location(full_name, str(path))
    if not spec or not spec.loader:
        return
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = full_name.rpartition(".")[0] or full_name
    if existing is None:
        _ADDED.add(full_name)
    else:
        _SAVED.setdefault(full_name, existing)
    sys.modules[full_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        # Leave partial module in sys.modules so subsequent imports don't retrigger the error
        sys.modules.setdefault(f"_stagnation_load_err_{full_name}", exc)
    _bind_on_parent(full_name, mod)


# Reuse the session's ``agent_loop`` package object rather than planting a new
# one — see the module docstring.  The root conftest already gives it a real
# ``__path__``; assert that here so ``from agent_loop.X import Y`` resolves the
# light submodules straight from disk even if this file is the first to need
# them.
_pkg = sys.modules.get("agent_loop")
if _pkg is None:
    _pkg = types.ModuleType("agent_loop")
    _pkg.__package__ = "agent_loop"
    sys.modules["agent_loop"] = _pkg
    _ADDED.add("agent_loop")
_pkg.__path__ = [str(_AL_DIR)]  # type: ignore[assignment]

# Load in dependency order (fingerprint and types have no heavy local deps).
_load_real("agent_loop.fingerprint", "agent_loop/fingerprint.py")
_load_real("agent_loop.types", "agent_loop/types.py")
# loop.py pulls in events/planner/tools — load best-effort; tests mock these.
_load_real("agent_loop.think_tool", "agent_loop/think_tool.py")
_load_real("agent_loop.slack_hook", "agent_loop/slack_hook.py")
_load_real("agent_loop.loop", "agent_loop/loop.py")

# MVA-1407: belief state + extractors package — reuse an existing entry for the
# same identity reason as the parent package above.
_ext_pkg = sys.modules.get("agent_loop.extractors")
if _ext_pkg is None:
    _ext_pkg = types.ModuleType("agent_loop.extractors")
    _ext_pkg.__package__ = "agent_loop.extractors"
    sys.modules["agent_loop.extractors"] = _ext_pkg
    _ADDED.add("agent_loop.extractors")
_ext_pkg.__path__ = [str(_AL_DIR / "extractors")]  # type: ignore[assignment]
_pkg.extractors = _ext_pkg  # type: ignore[attr-defined]
_load_real("agent_loop.extractors.read_file", "agent_loop/extractors/read_file.py")
_load_real("agent_loop.extractors.run_command", "agent_loop/extractors/run_command.py")
_load_real("agent_loop.extractors.web_search", "agent_loop/extractors/web_search.py")
_load_real("agent_loop.extractors", "agent_loop/extractors/__init__.py")
_load_real("agent_loop.belief_state", "agent_loop/belief_state.py")


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Undo exactly what this file changed, and nothing else.

    Sweeping every ``agent_loop*`` key out of ``sys.modules`` here would drop
    submodules other collectors imported on their own during the session.
    """
    for k in _ADDED:
        sys.modules.pop(k, None)
    for k, v in _SAVED.items():
        sys.modules[k] = v  # type: ignore[assignment]
