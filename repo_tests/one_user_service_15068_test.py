#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One ``UserService``, shared by both services (#15068).

Each backend carried its own ``user_service.py`` (900 and 863 lines). The copies
differed in four hunks, every one a capability one side had and the other
lacked, so a fix to account handling reached one service only. The class now
lives in ``autobot_shared/user_management/user_service*.py``; each backend keeps
a binding subclass that sets ``user_model`` and, in the backend only, the two
hooks.

This guard pins that shape by BEHAVIOUR, not by name: a class anywhere in the
two services that carries the account-handling methods is a second
implementation whatever it is called, and the error classes and the race-safe
insert have exactly one definition each.

Reach: the sweep runs over ``check_symbol_forks``' population and binds to its
declared floor (``MIN_FILES_PARSED``), the same one the symbol-fork ratchet uses,
so an enumeration that collapses fails here instead of reading as clean.
"""

from __future__ import annotations

import ast
import functools
import sys
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

sys.path.insert(0, str(repo_root() / "tools" / "lint"))
import check_symbol_forks as detector  # noqa: E402

SHARED_DIR = "autobot_shared/user_management"
CANONICAL = frozenset(
    f"{SHARED_DIR}/{name}.py"
    for name in (
        "user_service",
        "user_service_base",
        "user_service_lifecycle",
        "user_service_access",
        "user_service_conflict",
        "user_service_errors",
    )
)
BINDINGS = {
    "autobot-backend/user_management/services/user_service.py": {
        "invalidate_other_sessions",
        "reassign_memory",
        "reassign_sessions",
    },
    "autobot-slm-backend/user_management/services/user_service.py": set(),
}
SINGLE_DEFINITIONS = (
    "UserServiceError",
    "UserNotFoundError",
    "DuplicateUserError",
    "InvalidCredentialsError",
    "insert_user_or_raise_duplicate",
)
#: Methods only an account-handling service carries. Two on one class is a copy.
BEHAVIOUR = frozenset(
    {"create_user", "change_password", "delete_user", "authenticate", "_persist_user", "get_user_permissions"}
)
MAX_BINDING_LINES = 45


def _copies_user_service(tree: ast.Module) -> list[str]:
    """Classes at any depth defining two or more account-handling methods."""
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = {n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
            if len(methods & BEHAVIOUR) >= 2:
                found.append(node.name)
    return found


def _sweep() -> tuple[dict[str, list[str]], int]:
    """Offenders by file over the detector's population, and how many files were parsed."""
    offenders: dict[str, list[str]] = {}
    parsed = 0
    for path in detector.fork_scan_files():
        rel = path.as_posix()
        if not detector.in_population(path) or rel in CANONICAL:
            continue
        try:
            source = (repo_root() / rel).read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError, ValueError):
            continue
        parsed += 1
        copies = _copies_user_service(tree)
        if copies:
            offenders[rel] = copies
    return offenders, parsed


def test_no_second_user_service_implementation_by_behaviour() -> None:
    offenders, parsed = _sweep()
    assert parsed >= detector.MIN_FILES_PARSED, (
        f"the sweep parsed {parsed} files, under the detector's floor of {detector.MIN_FILES_PARSED} — "
        "an enumeration that collapsed must not read as a clean tree"
    )
    assert not offenders, (
        f"#15068: {offenders} carry UserService behaviour outside {SHARED_DIR}. Extend the shared "
        "class or override one of its hooks in the binding subclass instead."
    )


@functools.lru_cache(maxsize=1)
def _live_clusters() -> dict[str, detector.Cluster]:
    """One detector sweep for every parametrised case below."""
    return detector.find_clusters(detector.fork_scan_files())[0]


@pytest.mark.parametrize("name", SINGLE_DEFINITIONS)
def test_each_error_class_and_the_race_safe_insert_has_one_definition(name: str) -> None:
    clusters = _live_clusters()
    cluster = clusters.get(name)
    homes = sorted(d.path for d in cluster.definitions) if cluster else []
    assert not homes, f"#15068: {name} is defined in {homes}; its one home is {SHARED_DIR}"


@pytest.mark.parametrize("rel", sorted(BINDINGS))
def test_each_service_binds_the_shared_class_and_adds_only_its_hooks(rel: str) -> None:
    source = (repo_root() / rel).read_text(encoding="utf-8")
    assert len(source.splitlines()) <= MAX_BINDING_LINES, f"#15068: {rel} grew past a binding"
    classes = [n for n in ast.parse(source).body if isinstance(n, ast.ClassDef)]
    assert [c.name for c in classes] == ["UserService"], f"#15068: {rel} must define exactly one class"
    bases = [b.id for b in classes[0].bases if isinstance(b, ast.Name)]
    assert bases == ["SharedUserService"], f"#15068: {rel} must subclass the shared UserService, found {bases}"
    methods = {n.name for n in classes[0].body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert methods == BINDINGS[rel], f"#15068: {rel} defines {sorted(methods)}; allowed {sorted(BINDINGS[rel])}"


def test_the_canonical_modules_exist() -> None:
    missing = sorted(rel for rel in CANONICAL if not (repo_root() / rel).is_file())
    assert not missing, f"#15068: canonical modules missing: {missing}"


def test_the_behaviour_detector_has_a_contrast_pair() -> None:
    """A detector that never fires passes the sweep by finding nothing."""
    renamed_copy = (
        "class AccountManager:\n" "    async def create_user(self): ...\n" "    async def change_password(self): ...\n"
    )
    assert _copies_user_service(ast.parse(renamed_copy)) == ["AccountManager"], "a renamed copy is a copy"
    nested = "def factory():\n    class X:\n        def authenticate(self): ...\n        def delete_user(self): ...\n"
    assert _copies_user_service(ast.parse(nested)) == ["X"], "a nested copy is a copy"

    binding = (
        "class UserService(SharedUserService):\n"
        "    user_model = User\n"
        "    async def invalidate_other_sessions(self, user_id, token): ...\n"
    )
    assert _copies_user_service(ast.parse(binding)) == [], "a binding is not a copy"
    caller = "class Router:\n    async def create_user(self): ...\n    async def list_teams(self): ...\n"
    assert _copies_user_service(ast.parse(caller)) == [], "one shared method name is not a copy"


def test_the_definition_check_has_a_contrast_pair(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The single-definition check must fire on a second error class, and not on a re-export."""
    (tmp_path / "a.py").write_text("class DuplicateUserError(Exception):\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class DuplicateUserError(Exception):\n    pass\n", encoding="utf-8")
    (tmp_path / "c.py").write_text("from x import UserNotFoundError\n", encoding="utf-8")
    (tmp_path / "d.py").write_text("class UserNotFoundError(Exception):\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(detector, "_REPO_ROOT", tmp_path)
    clusters, parsed = detector.find_clusters([Path("a.py"), Path("b.py"), Path("c.py"), Path("d.py")])
    assert parsed == 4
    assert "DuplicateUserError" in clusters, "two definitions must form a cluster"
    assert "UserNotFoundError" not in clusters, "a re-export beside one definition is not a fork"
