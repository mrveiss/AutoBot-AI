# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One internal-API-key reader (#17856 row 13a, delivered on #18094).

`autobot_shared.node_proxy.internal_api_key()` is the only code that reads the shared
internal-service key. Before this, the backend read it through `ssot_config.misc`, the SLM
auth gate, the SLM vault client, the agent and a migration each read the environment
themselves, so a change to how the key is sourced had five places to be missed.

The marker is a read of the key's env var (`os.getenv` / `os.environ.get` / `os.environ[...]`
with the literal name or `INTERNAL_KEY_ENV`) or of the ssot field (`<x>.misc.internal_api_key`).
The detector reads the syntax tree, so a docstring or log message naming the variable is not a
read. Test files are out of scope: they build the key, they do not consume it.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_READER = "autobot_shared/node_proxy.py"
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
_ENV_NAME = "AUTOBOT_INTERNAL_API_KEY"
_ENV_GETTERS = {"getenv", "get"}


def _names_the_key(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == _ENV_NAME
    return isinstance(node, (ast.Attribute, ast.Name)) and getattr(node, "attr", getattr(node, "id", "")) == (
        "INTERNAL_KEY_ENV"
    )


def _is_environ(node: ast.AST) -> bool:
    return isinstance(node, (ast.Attribute, ast.Name)) and getattr(node, "attr", getattr(node, "id", "")) == "environ"


def _is_env_read(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and node.args and _names_the_key(node.args[0]):
        func = node.func
        if isinstance(func, ast.Name):
            return func.id == "getenv"
        if isinstance(func, ast.Attribute) and func.attr in _ENV_GETTERS:
            return func.attr == "getenv" or _is_environ(func.value)
    if isinstance(node, ast.Subscript):
        return _is_environ(node.value) and _names_the_key(node.slice)
    return False


def _is_ssot_read(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "internal_api_key"
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "misc"
    )


def _reads_the_key(source: str) -> bool:
    return any(_is_env_read(node) or _is_ssot_read(node) for node in ast.walk(ast.parse(source)))


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("getenv literal", "k = os.getenv('AUTOBOT_INTERNAL_API_KEY', '')\n", True),
        ("bare getenv", "k = getenv('AUTOBOT_INTERNAL_API_KEY')\n", True),
        ("environ.get via the constant", "k = os.environ.get(node_proxy.INTERNAL_KEY_ENV, '')\n", True),
        ("environ subscript", "k = os.environ['AUTOBOT_INTERNAL_API_KEY']\n", True),
        ("ssot field", "k = ssot_config.misc.internal_api_key\n", True),
        ("ssot via get_config", "k = get_config().misc.internal_api_key\n", True),
        ("the one reader", "k = node_proxy.internal_api_key()\n", False),
        ("another env var", "k = os.getenv('AUTOBOT_JWT_SECRET', '')\n", False),
        ("a dict get with the name", "k = headers.get('AUTOBOT_INTERNAL_API_KEY')\n", False),
        ("a log message", "logger.warning('AUTOBOT_INTERNAL_API_KEY not set')\n", False),
        ("a docstring", '"""os.getenv("AUTOBOT_INTERNAL_API_KEY")"""\nx = 1\n', False),
        ("an instance attribute", "k = self._internal_api_key\n", False),
    ],
)
def test_the_matcher_tells_a_key_read_from_a_mention(label: str, source: str, expected: bool) -> None:
    assert _reads_the_key(source) is expected, label


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _source_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "one-internal-api-key-reader-scan",
    discover=_source_population,
    floor=3253,  # mid-window: population 3403, window (3103, 3403)
    # Mid-window, from REACH.window(): 3032 measured, growth 300 -> 150 of headroom each way.
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _readers() -> tuple[str, ...]:
    found = []
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if ("INTERNAL" in source or "internal_api_key" in source) and _reads_the_key(source):
            found.append(rel)
    return tuple(found)


def test_only_node_proxy_reads_the_internal_api_key() -> None:
    assert _readers() == (_READER,), (
        f"#17856 row 13a: {sorted(set(_readers()) - {_READER})} read the internal API key themselves. "
        "Use `from autobot_shared import node_proxy` and call `node_proxy.internal_api_key()`."
    )
