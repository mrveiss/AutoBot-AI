# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One after-commit queue: ``defer_until_commit`` owns the hook pair (#21107).

Event wakes and activity publish each carried a copy of the queue in ``llc/services/after_commit.py``; it now lives in ``autobot_shared/after_commit.py``
(queue on ``session.info``, ``after_commit`` runs it, a rollback drops it). Two copies disagree about
SAVEPOINTs and rollbacks, so the hook has one home. The guard fails on an ``event.listen`` /
``listens_for`` of ``"after_commit"`` in non-test backend code outside that home.

The detector resolves the registration by name, not by spelling: ``from sqlalchemy import event as ev``,
``from sqlalchemy.event import listen as hook`` and an event name held in a variable
(``EVT = "after_commit"``) are all caught. A file that does not parse falls back to the regex.

``FROZEN`` names the sites that were not migrated, each with the reason; the set only shrinks.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

HOME = "autobot_shared/after_commit.py"
#: A listener registration that names the after_commit event, on one line or the next two.
_LISTENER = re.compile(r"""(?:event\.listen|listens_for)\(\s*[^)]*?["']after_commit["']""", re.S)
_TEST_MARKERS = ("_test.py", "/tests/", "/test_", "conftest.py")
_ROOTS = ("autobot-backend", "autobot_shared")

FROZEN: dict[str, str] = {
    "autobot-backend/user_management/services/person_copy_sync.py": "waits on #21260 (process-wide listener on the Session class, not a per-session queue)",
}


def _is_test(path: str) -> bool:
    return any(marker in path or path.startswith(marker.lstrip("/")) for marker in _TEST_MARKERS)


_EVENT_NAME = "after_commit"
_REGISTRARS = {"listen", "listens_for", "listen_for"}


def _aliases(tree: ast.AST) -> tuple[set[str], set[str], dict[str, str]]:
    """Names bound to the event module, names bound to a registrar, and string constants."""
    modules: set[str] = {"event"}
    funcs: set[str] = set()
    consts: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in ("sqlalchemy", "sqlalchemy.event"):
            for a in node.names:
                if node.module == "sqlalchemy" and a.name == "event":
                    modules.add(a.asname or a.name)
                elif node.module == "sqlalchemy.event" and a.name in _REGISTRARS:
                    funcs.add(a.asname or a.name)
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "sqlalchemy.event" and a.asname:
                    modules.add(a.asname)
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            for t in node.targets:
                if isinstance(t, ast.Name) and isinstance(node.value.value, str):
                    consts[t.id] = node.value.value
    return modules, funcs, consts


def _is_registrar(func: ast.expr, modules: set[str], funcs: set[str]) -> bool:
    if isinstance(func, ast.Name):
        return func.id in funcs
    return (
        isinstance(func, ast.Attribute)
        and func.attr in _REGISTRARS
        and isinstance(func.value, ast.Name)
        and func.value.id in modules
    )


def _names_event(arg: ast.expr, consts: dict[str, str]) -> bool:
    if isinstance(arg, ast.Constant):
        return arg.value == _EVENT_NAME
    return isinstance(arg, ast.Name) and consts.get(arg.id) == _EVENT_NAME


def listeners_in(text: str) -> int:
    try:
        tree = parse_cache.parse(text)
    except SyntaxError:
        return len(_LISTENER.findall(text))
    modules, funcs, consts = _aliases(tree)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _is_registrar(node.func, modules, funcs)
        and any(_names_event(a, consts) for a in node.args)
    )


def sweep(root: Path, paths: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for rel in paths:
        count = listeners_in((root / rel).read_text(encoding="utf-8", errors="replace"))
        if count:
            found[rel] = count
    return found


def _backend_sources(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, *(f"{prefix}/*.py" for prefix in _ROOTS))
    except EmptyEnumeration:
        return []
    return [p for p in paths if not _is_test(p)]


#: Non-test backend and shared modules. Pinned: the declaration is new, so there is no base to compute from (#19676).
#: 3,303 on 2026-11-11; floor sits mid-window (3,303 - 300 // 2). growth=300 follows the sibling backend-wide sweeps: ordinary
#: backend work adds files with most commits (RATCHET_BASELINES, "does normal work move this number?").
REACH = declare(
    "one-after-commit-queue-21107",
    discover=_backend_sources,
    what="non-test backend and shared modules",
    roots=_ROOTS,
    floor=3153,
    growth=300,
)


def test_control_string_is_caught() -> None:
    assert listeners_in('event.listen(sync, "after_commit", cb)') == 1
    assert listeners_in('@event.listens_for(sess, "after_commit", once=True)') == 1
    assert listeners_in('event.listen(sync, "after_soft_rollback", cb)') == 0


def test_aliased_event_module_is_caught() -> None:
    src = 'from sqlalchemy import event as ev\nev.listen(s, "after_commit", cb)\n'
    assert listeners_in(src) == 1


def test_aliased_listen_function_is_caught() -> None:
    src = 'from sqlalchemy.event import listen as hook\nhook(s, "after_commit", cb)\n'
    assert listeners_in(src) == 1
    src = 'from sqlalchemy.event import listens_for as lf\n@lf(s, "after_commit")\ndef f(x): ...\n'
    assert listeners_in(src) == 1


def test_event_name_in_a_variable_is_caught() -> None:
    src = 'EVT = "after_commit"\nevent.listen(s, EVT, cb)\n'
    assert listeners_in(src) == 1
    assert listeners_in('EVT = "after_rollback"\nevent.listen(s, EVT, cb)\n') == 0


def test_unrelated_listen_is_not_caught() -> None:
    assert listeners_in('from other import listen\nlisten(s, "after_commit", cb)\n') == 0


def test_control_planted_site_fails(tmp_path: Path) -> None:
    (tmp_path / "planted.py").write_text('event.listen(s, "after_commit", cb)\n', encoding="utf-8")
    assert sweep(tmp_path, ["planted.py"]) == {"planted.py": 1}


def test_home_registers_the_hook() -> None:
    assert HOME in sweep(repo_root(), [HOME])


def test_no_second_after_commit_queue() -> None:
    root = repo_root()
    files = REACH.examined(root)
    found = set(sweep(root, files)) - {HOME}
    REACH.completed(files)
    assert found == set(FROZEN), f"after_commit listeners outside {HOME}: {sorted(found ^ set(FROZEN))}"
