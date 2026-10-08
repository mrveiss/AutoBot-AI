# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``api/batch_jobs.py`` must not import a module that does not exist (#13558).

Three functions did ``from fast_app_factory_fix import app``. That module was
deleted in #567 (it had been archived first, so the deletion looked safe) and
nothing in the tree has defined it since, so every one of those calls raised
``ModuleNotFoundError``.

Two of the three failed *silently*, which is why this survived so long:

* ``get_chat_sessions`` is gathered with ``return_exceptions=True``, so the chat
  UI initialised with an empty session list and no error anywhere.
* ``get_settings`` had the import inside its own ``try``, so even the hardcoded
  defaults below it were unreachable and it returned ``{}`` forever.

Both now take the live ``app`` from the route's ``request.app`` -- the pattern the
rest of ``api/`` already uses -- rather than importing one.

## Why these tests parse instead of grep

The obvious check, "no ``fast_app_factory_fix`` in the file", is wrong in both
directions here. This very file mentions the name repeatedly in prose, and so does
``batch_jobs.py``: the comment at the ``tasks.batch_job_tasks`` import used to cite
the broken imports as precedent for local importing, and the corrected comment still
has to name what it is correcting. A text search cannot tell a removed import from a
sentence about one. `test_an_import_in_prose_is_not_an_import` holds that apart with a
fixture carrying the string in a docstring, a comment and a string literal and in no
executable import; `test_the_detector_finds_a_real_import` is the matching positive
control, because a detector that finds nothing anywhere would pass the first test
while asserting nothing.

## What is NOT fixed here

``batch_load`` (``POST /api/batch-jobs/load``) keeps its dead import, so the
assertions above are scoped to the three repaired functions by name rather than to
the file as a whole. Repairing it means making live an endpoint that carries no
``Depends(get_current_user)`` while all fourteen of its siblings in this file do --
a decision about an authentication surface, not a crash fix. The PR body carries
the options and the evidence.

No test here enshrines that broken state. A guard asserting the import is still
present would fail on the day someone fixes it, which is worse than no guard.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from api.batch_jobs import get_chat_sessions, get_settings

_SOURCE = Path(__file__).with_name("batch_jobs.py")
_DEAD_MODULE = "fast_app_factory_fix"


def _imported_module_names(source: str) -> set[str]:
    """Every module name reached by an executable ``import`` in *source*.

    Both statement forms, at any nesting depth -- these imports are function-local,
    so a module-level-only walk would report the file clean while three functions
    still carried them.
    """
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
    return names


def _function(source: str, name: str) -> ast.AST:
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found in batch_jobs.py")


def test_the_detector_finds_a_real_import() -> None:
    """Positive control: without this, an empty result proves nothing below."""
    found = _imported_module_names(f"def f():\n    from {_DEAD_MODULE} import app\n")
    assert _DEAD_MODULE in found, "detector cannot see a function-local import"
    assert "asyncio" in _imported_module_names(
        _SOURCE.read_text(encoding="utf-8")
    ), "detector found none of batch_jobs.py's known real imports"


def test_an_import_in_prose_is_not_an_import() -> None:
    """Contrast fixture: the name in a docstring, a comment and a literal only."""
    prose_only = f'''
"""Once did `from {_DEAD_MODULE} import app`, which is the bug."""
# from {_DEAD_MODULE} import app
NOTE = "from {_DEAD_MODULE} import app"
import asyncio
'''
    assert prose_only.count(_DEAD_MODULE) == 3, "fixture lost the strings it exists to carry"
    found = _imported_module_names(prose_only)
    assert _DEAD_MODULE not in found, "a comment, docstring or literal registered as an import"
    assert "asyncio" in found, "fixture's one real import was missed"


def test_the_repaired_helpers_no_longer_import_the_dead_module() -> None:
    source = _SOURCE.read_text(encoding="utf-8")
    for name in ("get_chat_sessions", "get_settings", "batch_chat_initialization"):
        fn = _function(source, name)
        assert _DEAD_MODULE not in _imported_module_names(ast.unparse(fn)), f"{name} still imports {_DEAD_MODULE}"


def test_the_repaired_helpers_take_the_app_as_a_parameter() -> None:
    """They must receive the live app, not reach for a global one."""
    source = _SOURCE.read_text(encoding="utf-8")
    for name in ("get_chat_sessions", "get_settings"):
        args = [a.arg for a in _function(source, name).args.args]
        assert args == ["app"], f"{name} takes {args}, expected ['app']"


def test_the_route_supplies_request_app_to_both_helpers() -> None:
    """A parameter nothing passes is no better than a dead import."""
    fn = _function(_SOURCE.read_text(encoding="utf-8"), "batch_chat_initialization")
    assert "request" in [a.arg for a in fn.args.args], "route takes no Request to source the app from"
    passed = {
        call.func.id: ast.unparse(call.args[0])
        for call in ast.walk(fn)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.args
    }
    assert passed.get("get_chat_sessions") == "request.app"
    assert passed.get("get_settings") == "request.app"


@pytest.mark.asyncio
async def test_get_settings_returns_its_defaults_instead_of_an_empty_dict() -> None:
    """Pre-fix the dead import sat inside the try, so `{}` came back every call."""
    settings = await get_settings(SimpleNamespace(state=SimpleNamespace()))
    assert settings["theme"] == "light"
    assert settings["language"] == "en"


@pytest.mark.asyncio
async def test_get_settings_prefers_live_app_state() -> None:
    app = SimpleNamespace(state=SimpleNamespace(settings={"theme": "dark"}))
    assert await get_settings(app) == {"theme": "dark"}


@pytest.mark.asyncio
async def test_get_chat_sessions_reaches_the_chat_history_manager() -> None:
    """Pre-fix this raised ModuleNotFoundError before touching app.state."""
    manager = Mock()
    manager._get_chats_directory = Mock(return_value="/nonexistent-batch-jobs-probe")
    app = SimpleNamespace(state=SimpleNamespace(chat_history_manager=manager))
    result = await get_chat_sessions(app)
    assert result == {"sessions": []}
    # Reaching the mock at all is the proof: the probe directory does not exist, so a
    # pre-fix ModuleNotFoundError died before app.state was ever touched. `assert_called()`
    # takes no message, so this rationale is a comment -- as a trailing string it built a
    # tuple that was evaluated and discarded, which read like an assertion message.
    manager._get_chats_directory.assert_called()


@pytest.mark.asyncio
async def test_get_chat_sessions_without_a_manager_is_empty_not_an_error() -> None:
    assert await get_chat_sessions(SimpleNamespace(state=SimpleNamespace())) == {"sessions": []}
