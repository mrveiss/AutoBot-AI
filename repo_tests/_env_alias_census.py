# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A STATIC census of ``AUTOBOT_*`` names: SSOT settings aliases versus env-registry entries (#17419).

Stdlib ``ast`` only, over the tree a caller parsed, so the census needs no import of the settings
models and the baseline can be derived by reading files as text.

Seen: a string constant given as ``alias=`` / ``validation_alias=`` on any call, or as an argument of
``AliasChoices(...)``; a string constant given as ``name=`` (or the first argument) of ``EnvVarSpec(...)``.
NOT seen, and counted as ``dynamic`` with its ``line`` so the blind spot is a number, not silence:
an alias or registry name that is not a string constant (a variable, an f-string, a ``*args`` spread).
For the registry the blind spot is covered conservatively (see ``registered_in``); for aliases it is not.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

NAMESPACE = "AUTOBOT_"
_ALIAS_KEYWORDS = frozenset({"alias", "validation_alias"})
_WHOLE_NAME = re.compile(r"AUTOBOT_[A-Z0-9_]+")


@dataclass
class Census:
    names: set[str] = field(default_factory=set)
    #: ``(line, kind)`` of every name the census could not read as a string constant.
    dynamic: list[tuple[int, str]] = field(default_factory=list)


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)


def _take(census: Census, value: ast.expr, kind: str) -> None:
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        if value.value.startswith(NAMESPACE):
            census.names.add(value.value)
    else:
        census.dynamic.append((value.lineno, kind))


def aliases_in(tree: ast.AST) -> Census:
    """Every ``AUTOBOT_*`` alias the SSOT settings code writes as a string in *tree*."""
    census = Census()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node) == "AliasChoices":
            for arg in node.args:
                _take(census, arg.value if isinstance(arg, ast.Starred) else arg, "AliasChoices")
            continue
        for kw in node.keywords:
            if kw.arg in _ALIAS_KEYWORDS and not (
                isinstance(kw.value, ast.Call) and _call_name(kw.value) == "AliasChoices"
            ):
                _take(census, kw.value, kw.arg)
    return census


def registered_in(tree: ast.AST) -> Census:
    """Every ``AUTOBOT_*`` name an ``EnvVarSpec(...)`` in *tree* registers."""
    census = Census()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and _call_name(node) == "EnvVarSpec"):
            continue
        named = [kw.value for kw in node.keywords if kw.arg == "name"] or node.args[:1]
        for value in named:
            _take(census, value, "EnvVarSpec")
        if not named:  # ``EnvVarSpec(**spec)``: the name arrives inside a mapping the census cannot read
            census.dynamic.append((node.lineno, "EnvVarSpec"))
    if census.dynamic:
        # A helper or loop registers names it was handed (``_register("AUTOBOT_X", ...)``): in a file
        # with such a site, every whole-name string constant counts as registered, so the helper's
        # names are not reported as missing. This over-approximates; ``dynamic`` still names the sites.
        census.names |= {
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and _WHOLE_NAME.fullmatch(n.value)
        }
    return census
