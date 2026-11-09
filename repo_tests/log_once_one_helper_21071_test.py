# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One log-once helper, no hand-rolled copies (#21071).

"Log this once per process" had been written by hand in about two dozen modules: a module-level
``set`` or flag plus a private ``_warn_once``. Each kept its own state, key scheme and locking, so a
fix to one never reached the rest. ``autobot_shared.logging_once`` is the one implementation.

The population is **discovered, not listed**: any module- or class-level binding whose name says
"warned / logged / reported" and whose value is an empty container or ``False``, plus any
``def _warn_once`` / ``def _log_once``. A list of the known copies would be satisfied by the next one.

Two tables describe what the sweep is allowed to find, and both are exact:

* ``_NOT_LOG_ONCE`` -- bindings that are not log-once (they reset, or dedupe consecutive values), each
  with the reason. Nothing else may join without a reason.
* ``_DEFERRED`` -- genuine copies whose file belongs to an open PR waiting on a train; the set must
  equal what the tree still contains, so a migrated entry fails until it is removed (the ratchet only
  goes down) and a new copy fails until it is migrated.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import tracked_paths

_HELPER = "autobot_shared/logging_once.py"
_NAME = re.compile(r"(warned|logged|reported)", re.IGNORECASE)
_DEF_NAMES = {"_warn_once", "_log_once"}
_SKIP = re.compile(r"(^|/)(repo_tests|tests|testkit|node_modules|e2e)/|(_test\.py|/test_[^/]*\.py|conftest\.py)$")

#: Not log-once: the state is reset, or it compares consecutive values. Each says why.
_NOT_LOG_ONCE = {
    ("autobot-slm-backend/services/git_tracker.py", "_missing_repo_warned"): "reset when the repo recovers",
    ("autobot-backend/services/telegram_polling.py", "_token_unreadable_reported"): "reset when the token reads again",
    ("autobot-slm-backend/services/self_update_log_reader.py", "_reported_runs"): "last run key per state, not a set",
}

#: Real copies in files an open, approved PR still holds. Migrate when that PR lands, then delete the entry.
_DEFERRED = {
    ("autobot-backend/middleware/service_auth_enforcement.py", "_rate_limit_disabled_logged"): "#21046",
}

#: Floor on files EXAMINED (not on findings: finding nothing is also what a broken sweep reports).
_MIN_FILES_PARSED = 2000


def _is_empty_state(value: ast.AST | None) -> bool:
    if isinstance(value, ast.Constant):
        return value.value is False
    if isinstance(value, ast.Dict):
        return not value.keys
    if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
        return value.func.id in {"set", "frozenset", "dict"} and not value.args
    return False


def _target_names(node: ast.AST) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [t.id for t in targets if isinstance(t, ast.Name)]


def hand_rolled_in(source: str) -> list[str]:
    """Names of hand-rolled once-state and ``_warn_once`` defs at module or class level in *source*."""
    found: list[str] = []
    scopes = [parse_cache.parse(source)]
    scopes += [n for n in ast.walk(scopes[0]) if isinstance(n, ast.ClassDef)]
    for scope in scopes:
        for node in scope.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in _DEF_NAMES:
                found.append(node.name)
            elif isinstance(node, (ast.Assign, ast.AnnAssign)) and _is_empty_state(node.value):
                found += [n for n in _target_names(node) if _NAME.search(n)]
    return found


def _sweep() -> tuple[set[tuple[str, str]], int]:
    root = repo_root()
    found: set[tuple[str, str]] = set()
    parsed = 0
    for rel in tracked_paths(root, "*.py", "**/*.py"):
        if rel == _HELPER or _SKIP.search(rel):
            continue
        parsed += 1
        found |= {(rel, n) for n in hand_rolled_in(Path(root, rel).read_text(encoding="utf-8"))}
    return found, parsed


def test_the_detector_sees_a_planted_copy() -> None:
    """Control: each shape of the pattern is found, and an unrelated binding is not."""
    planted = (
        "_seen_warned: set[str] = set()\n"
        "_flag_logged = False\n"
        "def _warn_once(key): ...\n"
        "class C:\n    _use_reported = False\n"
        "_cache = {}\n"
        "_logged_total = 0\n"
    )
    assert sorted(hand_rolled_in(planted)) == ["_flag_logged", "_seen_warned", "_use_reported", "_warn_once"]


def test_no_new_hand_rolled_log_once() -> None:
    """Every once-state is in the helper; the only exceptions are the two tables, exactly."""
    found, parsed = _sweep()
    assert parsed >= _MIN_FILES_PARSED, f"sweep examined {parsed} files; it is not looking at the tree"
    copies = found - set(_NOT_LOG_ONCE)
    new = sorted(copies - set(_DEFERRED))
    assert not new, f"hand-rolled log-once outside {_HELPER} (use log_once / first_time): {new}"
    migrated = sorted(set(_DEFERRED) - copies)
    assert (
        not migrated
    ), f"_DEFERRED entries no longer in the tree; delete them (the ratchet only goes down): {migrated}"
    stale = sorted(set(_NOT_LOG_ONCE) - found)
    assert not stale, f"_NOT_LOG_ONCE entries no longer match anything: {stale}"
