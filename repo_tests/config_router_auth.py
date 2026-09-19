# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The config-listed router registries, for the router-auth sweep (#16368).

``router_auth_enumerator.REGISTRY`` reads only ``core_routers.py``, which
imports its routers. The other registries list routers as config tuples,
``(module, [router_attr,] prefix, tags, name)``, which ``loader.py`` imports at
runtime. No import statement names them, so the core sweep never saw one of
them. ``api.skills`` sat in ``feature_routers.py``, anonymous, for exactly that
reason.

This module reads those lists and classifies each router with the core sweep's
own ``classify``. It deliberately leaves ``REGISTRY`` and the core guard alone.
"""

import ast
from pathlib import Path

from repo_tests.router_auth_enumerator import BACKEND, Verdict, auth_vocabulary, classify

#: Every registry that lists routers as config tuples. ``mcp_routers.py`` is
#: absent because it lists none of its own: its routers are in ``core_routers.py``.
CONFIG_REGISTRIES: tuple[str, ...] = tuple(
    f"{BACKEND}/initialization/router_registry/{group}_routers.py"
    for group in ("feature", "analytics", "integration", "monitoring", "terminal")
)

_ENUMERATED: dict[str, list[Verdict]] = {}


def _config_lists(tree: ast.Module) -> list[ast.List]:
    """The ``*_ROUTER_CONFIGS = [...]`` literals in one registry module."""
    lists = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        else:
            continue
        if isinstance(target, ast.Name) and target.id.endswith("_ROUTER_CONFIGS") and isinstance(value, ast.List):
            lists.append(value)
    return lists


def config_registered_routers(root: Path) -> list[tuple[str, str]]:
    """``(name, module)`` for every router the config registries list.

    In every entry shape the module is the first string and the name the last.
    An absent or unreadable registry contributes nothing rather than raising, so
    an empty tree reads as "reached nothing" and the reach floor reports it.
    """
    found = []
    for relative in CONFIG_REGISTRIES:
        try:
            tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue
        for config in _config_lists(tree):
            for entry in config.elts:
                strings = [
                    item.value
                    for item in getattr(entry, "elts", [])
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                ]
                if strings:
                    found.append((strings[-1], strings[0]))
    return sorted(set(found))


def enumerate_config_routers(root: Path) -> list[Verdict]:
    """Every config-registered router, classified exactly as core routers are. Memoised per root."""
    key = str(root.resolve())
    if key not in _ENUMERATED:
        vocabulary = auth_vocabulary(root)
        _ENUMERATED[key] = [
            classify(root, name, module, vocabulary) for name, module in config_registered_routers(root)
        ]
    return _ENUMERATED[key]
