# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One converter per provider wire format (#16815).

The Anthropic / OpenAI tool-schema dicts were inlined in five provider modules and could drift
apart. They now live once in `autobot-backend/llm_shared/providers/message_formatting.py`. The
Anthropic system/chat split is guarded separately (`one_anthropic_message_split_16815_test.py`).

The markers are dict literals in the syntax tree, so prose naming them is not a definition:
  * Anthropic tool entry: keys `name`, `description` and `input_schema`;
  * OpenAI function tool: keys `type` (value "function") and `function`.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT_DIR = "autobot-backend/llm_shared/providers"
_CANONICAL = f"{_ROOT_DIR}/message_formatting.py"
_ANTHROPIC_KEYS = {"name", "description", "input_schema"}


def _dict_keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _is_function_tool(node: ast.Dict) -> bool:
    if not {"type", "function"} <= _dict_keys(node):
        return False
    pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    kind = pairs["type"]
    return isinstance(kind, ast.Constant) and kind.value == "function"


def _inlined_formatters(source: str) -> list[str]:
    """Names of the inlined formatter shapes `source` contains."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict) and _ANTHROPIC_KEYS <= _dict_keys(node):
            found.append("anthropic tool schema dict")
        elif isinstance(node, ast.Dict) and _is_function_tool(node):
            found.append("openai function tool dict")
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        (
            "anthropic tool dict",
            'x = {"name": n, "description": d, "input_schema": s}\n',
            ["anthropic tool schema dict"],
        ),
        ("openai tool dict", 'x = {"type": "function", "function": {"name": n}}\n', ["openai function tool dict"]),
        ("a call to the helper", "x = openai_function_tool_schemas(tools)\n", []),
        ("a non-function type dict", 'x = {"type": "text", "function": 1}\n', []),
        ("a comment naming it", '# {"type": "function", "function": 1}\nx = 1\n', []),
    ],
)
def test_the_matcher_tells_an_inlined_formatter_from_a_use(label: str, source: str, expected: list[str]) -> None:
    assert _inlined_formatters(source) == expected, label


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _provider_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, _ROOT_DIR)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "provider-tool-schema-scan",
    discover=_provider_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=22,
    what="non-test provider python source",
    roots=(_ROOT_DIR,),
    growth=5,
)


@functools.lru_cache(maxsize=1)
def _offenders() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for rel in REACH.examined(repo_root()):
        if rel == _CANONICAL:
            continue
        hits = _inlined_formatters((repo_root() / rel).read_text(encoding="utf-8"))
        if hits:
            out[rel] = hits
    return out


def test_the_scan_reaches_the_providers() -> None:
    assert _CANONICAL in REACH.examined(repo_root())


def test_the_canonical_module_defines_each_formatter() -> None:
    hits = set(_inlined_formatters((repo_root() / _CANONICAL).read_text(encoding="utf-8")))
    assert hits == {"anthropic tool schema dict", "openai function tool dict"}


def test_no_provider_inlines_a_formatter() -> None:
    assert _offenders() == {}, (
        f"#16815: {_offenders()} inline a provider wire-format conversion; call the converter in "
        f"{_CANONICAL} instead of copying it."
    )
