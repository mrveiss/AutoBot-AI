# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The env registry must stay extensible (#15624).

`autobot_shared/env_registry.py` reached exactly its recorded size ceiling, and a
grandfathered file may not grow. Registering a variable means adding a block to
that file, so for a while **no new environment variable could be registered
anywhere in the repository** — in any component — by a ratchet that was never
aimed at this.

The ratchet is not wrong about growth. Its premise just does not fit a registry:
length here measures how much configuration the system has, not how tangled the
module is. The fix splits by the `component` field each spec already carries.

These tests pin the property that fix bought, because it is easy to lose by
accident: consolidating the modules back into one would restore the freeze
silently, and the next person to add a variable would meet the same wall with no
explanation.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED = REPO_ROOT / "autobot_shared"
PARENT = SHARED / "env_registry.py"

#: Every module that may hold `register_env_var` calls.
_MODULES = sorted(SHARED.glob("env_registry*.py"))


def _registrations(path: Path) -> list[str]:
    """Names registered by *path*, in file order."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = []
    for node in tree.body:
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        if getattr(node.value.func, "id", "") != "register_env_var":
            continue
        spec = node.value.args[0]
        for keyword in spec.keywords:
            if keyword.arg == "name" and isinstance(keyword.value, ast.Constant):
                names.append(keyword.value.value)
    return names


def test_the_scan_finds_the_registry_modules():
    """FIX THE SWEEP floor: a glob matching nothing would assert nothing below."""
    assert len(_MODULES) >= 2, (
        f"only {len(_MODULES)} env_registry module(s) found — FIX THE SWEEP, or the "
        "registry has been consolidated back into one file, which is the freeze "
        "this guard exists to prevent (#15624)"
    )


def test_registrations_live_outside_the_parent_module():
    """At least one component's entries must sit in a module of their own.

    This is the actual property. If every registration migrates back into
    `env_registry.py`, that file resumes growing toward its ceiling and the next
    variable is blocked again — with nothing on record saying why.
    """
    elsewhere = {
        module.name: _registrations(module) for module in _MODULES if module != PARENT
    }
    populated = {name: entries for name, entries in elsewhere.items() if entries}

    assert populated, (
        "every register_env_var call is back in env_registry.py. That file is "
        "grandfathered, so it will reach its ceiling again and block all further "
        "registration (#15624). Split a component out instead."
    )


def test_no_variable_is_registered_twice():
    """A move that copies rather than moves would register a name in two places."""
    seen: dict[str, str] = {}
    duplicates = []
    for module in _MODULES:
        for name in _registrations(module):
            if name in seen:
                duplicates.append(f"{name} in both {seen[name]} and {module.name}")
            seen[name] = module.name

    assert not duplicates, "a variable is registered in more than one module:\n  " + "\n  ".join(duplicates)


def test_every_split_module_is_imported_by_the_parent():
    """A module nobody imports registers nothing, and would fail silently.

    The registration happens as an import side effect, so an orphaned module is
    not a dormant file — it is a set of variables the registry does not have,
    while the source still looks as though it does.
    """
    parent_source = PARENT.read_text(encoding="utf-8")
    orphans = [
        module.name
        for module in _MODULES
        if module != PARENT and _registrations(module) and module.stem not in parent_source
    ]

    assert not orphans, (
        "these registry modules define variables but are never imported by "
        "env_registry.py, so nothing registers them:\n  " + "\n  ".join(orphans)
    )
