# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
conftest.py for agent_loop unit tests.

autobot-backend/conftest.py stubs ``agent_loop`` (and sub-modules) to break
the orchestration → agent_loop import chain for orchestration-layer tests.
Tests in this directory need the *real* implementations.

We swap stubs for real modules at conftest load time and restore them
via ``pytest_unconfigure`` so sibling test directories are unaffected.

Issue #6627.
"""

import importlib.util
import sys
import types
from pathlib import Path

_BACKEND = Path(__file__).parent.parent.parent  # .../autobot-backend
_AL_DIR = _BACKEND / "agent_loop"

# Keys to save/restore.
_AGENT_LOOP_KEYS = [k for k in sys.modules if k == "agent_loop" or k.startswith("agent_loop.")]
_SAVED: dict[str, object] = {k: sys.modules[k] for k in _AGENT_LOOP_KEYS}


def _load_real(full_name: str, rel: str) -> None:
    """Load a Python file directly and register it under *full_name*."""
    path = _BACKEND / rel
    spec = importlib.util.spec_from_file_location(full_name, str(path))
    if not spec or not spec.loader:
        return
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = full_name.rpartition(".")[0] or full_name
    sys.modules[full_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        # Leave partial module in sys.modules so subsequent imports don't retrigger the error
        sys.modules.setdefault(f"_stagnation_load_err_{full_name}", exc)


# Remove stubs placed by the parent conftest.
for _k in _AGENT_LOOP_KEYS:
    sys.modules.pop(_k, None)

# Plant a real package entry so ``from agent_loop.X import Y`` resolves.
_pkg = types.ModuleType("agent_loop")
_pkg.__path__ = [str(_AL_DIR)]  # type: ignore[assignment]
_pkg.__package__ = "agent_loop"
sys.modules["agent_loop"] = _pkg

# Load in dependency order (fingerprint and types have no heavy local deps).
_load_real("agent_loop.fingerprint", "agent_loop/fingerprint.py")
_load_real("agent_loop.types", "agent_loop/types.py")
# loop.py pulls in events/planner/tools — load best-effort; tests mock these.
_load_real("agent_loop.think_tool", "agent_loop/think_tool.py")
_load_real("agent_loop.slack_hook", "agent_loop/slack_hook.py")
_load_real("agent_loop.loop", "agent_loop/loop.py")


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Restore the original stub state so other directories are unaffected."""
    for k in list(sys.modules):
        if k == "agent_loop" or k.startswith("agent_loop."):
            sys.modules.pop(k, None)
    for k, v in _SAVED.items():
        sys.modules[k] = v  # type: ignore[assignment]
