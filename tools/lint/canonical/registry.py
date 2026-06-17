# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Rule discovery and execution.

Rule modules are auto-discovered from a Python package via pkgutil. A valid
rule module exports module-level constants (RULE_ID, ISSUE, SEVERITY, TARGETS,
DESCRIPTION, FIX_HINT) and a `check(file_path, tree, ctx) -> list[Diagnostic]`
function. Anything else in the package is ignored.
"""

from __future__ import annotations

import ast
import importlib
import pkgutil
from collections.abc import Iterable
from pathlib import Path
from types import ModuleType

from tools.lint.canonical.context import Context, file_in_targets
from tools.lint.canonical.diagnostic import Diagnostic

_REQUIRED_ATTRS = ("RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT", "check")


def discover_rules(package: str) -> list[ModuleType]:
    pkg = importlib.import_module(package)
    rules: list[ModuleType] = []
    if not hasattr(pkg, "__path__"):
        return rules
    for _finder, modname, _ispkg in pkgutil.iter_modules(pkg.__path__):
        if modname.startswith("_"):
            continue
        mod = importlib.import_module(f"{package}.{modname}")
        if all(hasattr(mod, attr) for attr in _REQUIRED_ATTRS):
            rules.append(mod)
    return rules


def run_rules(
    rules: list[ModuleType],
    files: Iterable[Path],
    ctx: Context,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    for file_path in files:
        tree = ctx.parse(file_path)
        if tree is None:
            continue
        for rule in rules:
            if not file_in_targets(file_path, rule.TARGETS, repo_root=ctx.repo_root):
                continue
            diagnostics.extend(rule.check(file_path, tree, ctx))
    return diagnostics
