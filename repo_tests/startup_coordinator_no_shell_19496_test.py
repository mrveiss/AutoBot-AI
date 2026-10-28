# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The startup coordinator launches components from an argv list, never through a shell (#19496).

``subprocess.Popen(component.start_command, shell=True)`` was bandit B602 (High/High) and made every
PR touching the file red. The commands are fixed strings built in code, so no shell feature is
needed. ``autobot-infrastructure`` tests are not collected by CI (#14131), so this lives here.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_COORDINATOR = "autobot-infrastructure/shared/scripts/startup_coordinator.py"


def _tree() -> ast.Module:
    return ast.parse((repo_root() / _COORDINATOR).read_text(encoding="utf-8"))


def shell_true_calls(tree: ast.AST) -> list[int]:
    """Lines of each call passing ``shell=`` anything other than a literal False."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for k in node.keywords
        if k.arg == "shell" and not (isinstance(k.value, ast.Constant) and k.value.value is False)
    ]


def string_start_commands(tree: ast.AST) -> list[int]:
    """Lines where ``start_command=`` is given a string rather than an argv list."""
    return [
        k.value.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for k in node.keywords
        if k.arg == "start_command" and not isinstance(k.value, ast.List)
    ]


def test_the_coordinator_never_uses_a_shell() -> None:
    tree = _tree()
    assert shell_true_calls(tree) == []
    assert string_start_commands(tree) == []
    assert sum(1 for n in ast.walk(tree) if isinstance(n, ast.keyword) and n.arg == "start_command") >= 2


def test_each_component_starts_in_its_own_session() -> None:
    """Stop signals the process group, so ``npm run dev``'s vite grandchild is not orphaned."""
    popens = [n for n in ast.walk(_tree()) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "Popen"]
    assert popens, "the coordinator no longer calls Popen"
    for call in popens:
        kw = {k.arg: k.value for k in call.keywords}
        assert isinstance(kw.get("start_new_session"), ast.Constant) and kw["start_new_session"].value is True


def test_the_detectors_see_a_shell_and_a_string_command() -> None:
    bad = ast.parse('subprocess.Popen(cmd, shell=True)\nComponentInfo(name="x", start_command="npm run dev")\n')
    assert shell_true_calls(bad) == [1]
    assert string_start_commands(bad) == [2]
    good = ast.parse('subprocess.Popen(cmd, shell=False)\nComponentInfo(name="x", start_command=["npm", "run"])\n')
    assert shell_true_calls(good) == [] and string_start_commands(good) == []


def test_a_group_member_outliving_its_leader_is_stopped() -> None:
    """The leader exits at once, its backgrounded child survives: stop must still reach the child."""
    import subprocess

    from autobot_shared.process_group import process_group_is_dead, stop_process_group

    process = subprocess.Popen(["sh", "-c", "sleep 30 & exit 0"], start_new_session=True)
    process.wait(timeout=5)  # leader gone, the sleep lives on in the group
    assert not process_group_is_dead(process.pid)
    assert stop_process_group(process, grace_s=2) is True
    assert process_group_is_dead(process.pid)
    assert stop_process_group(process, grace_s=2) is False  # nothing left to stop


def test_the_coordinator_stops_through_the_shared_helper() -> None:
    """One implementation: the coordinator's stop calls autobot_shared.process_group, no local copy."""
    tree = _tree()
    imported = {
        alias.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "autobot_shared.process_group"
        for alias in n.names
    }
    local = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "stop_process_group" in imported
    assert not {"process_group_is_dead", "_group_alive", "_signal_group", "_wait_for_group"} & local
