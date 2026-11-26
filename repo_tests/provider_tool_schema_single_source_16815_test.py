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
  * OpenAI function tool: keys `type` (value "function") and `function`;
  * a `dict(...)` call or dict literal pairing `name` with `input_schema` or `parameters`.

The scan covers every non-test python file under `autobot-backend/llm_shared` (providers and
adapters) plus exactly three request builders outside it, listed in `_EXTRA_FILES`:
`api/llm.py`, `chat_workflow/manager.py` and `modern_ai_integration.py`. Nothing else is scanned.
Out of scope: MCP tool registries and tool-definition modules (they define tools, they do not build
provider requests) including `api/browser_mcp.py`, and any other module not named above. See
`_inlined_formatters` for the shapes the matcher cannot see.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.testfile_names import is_test_filename
from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT_DIR = "autobot-backend/llm_shared"
_EXTRA_FILES = (
    "autobot-backend/api/llm.py",
    "autobot-backend/chat_workflow/manager.py",
    "autobot-backend/modern_ai_integration.py",
)
_CANONICAL = f"{_ROOT_DIR}/providers/message_formatting.py"
_ANTHROPIC_KEYS = {"name", "description", "input_schema"}
_SCHEMA_KEYS = {"input_schema", "parameters"}


def _dict_keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)}


def _is_function_tool(node: ast.Dict) -> bool:
    if not {"type", "function"} <= _dict_keys(node):
        return False
    pairs = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
    kind = pairs["type"]
    return isinstance(kind, ast.Constant) and kind.value == "function"


def _is_dict_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict"


def _pairs_name_with_schema(keys: set[str]) -> bool:
    return "name" in keys and bool(keys & _SCHEMA_KEYS)


def _inlined_formatters(source: str) -> list[str]:
    """Names of the inlined formatter shapes `source` contains.

    Flagged: a dict literal with `name`+`description`+`input_schema`; an OpenAI function tool
    (`type`="function" + `function`); a `dict(...)` call, or any other dict literal, pairing `name` with
    `input_schema` or `parameters`.

    Known limits (not detected): a schema assembled key by key (`d["name"] = ...; d["input_schema"] = ...`),
    keys built from non-literal expressions or `**` unpacking, a dict built from `dict(zip(...))` or a
    comprehension, and a tool dict whose `name` is added after the schema in a separate statement.
    """
    found: list[str] = []
    for node in ast.walk(parse_cache.parse(source)):
        if isinstance(node, ast.Dict) and _ANTHROPIC_KEYS <= _dict_keys(node):
            found.append("anthropic tool schema dict")
        elif isinstance(node, ast.Dict) and _is_function_tool(node):
            found.append("openai function tool dict")
        elif isinstance(node, ast.Dict) and _pairs_name_with_schema(_dict_keys(node)):
            found.append("partial tool schema dict")
        elif _is_dict_call(node) and _pairs_name_with_schema({k.arg for k in node.keywords if k.arg}):
            found.append("tool schema dict() call")
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
        ("dict() call with input_schema", "x = dict(name=n, input_schema=s)\n", ["tool schema dict() call"]),
        ("dict() call with parameters", "x = dict(name=n, parameters=s)\n", ["tool schema dict() call"]),
        ("dict() call without a schema key", "x = dict(name=n, description=d)\n", []),
        ("partial dict with input_schema", 'x = {"name": n, "input_schema": s}\n', ["partial tool schema dict"]),
        ("partial dict with parameters", 'x = {"name": n, "parameters": s}\n', ["partial tool schema dict"]),
        ("a dict with only a schema key", 'x = {"parameters": s}\n', []),
        ("a call to the helper", "x = openai_function_tool_schemas(tools)\n", []),
        ("a non-function type dict", 'x = {"type": "text", "function": 1}\n', []),
        ("a comment naming it", '# {"type": "function", "function": 1}\nx = 1\n', []),
    ],
)
def test_the_matcher_tells_an_inlined_formatter_from_a_use(label: str, source: str, expected: list[str]) -> None:
    assert _inlined_formatters(source) == expected, label


def _is_source_python(rel: str) -> bool:
    return rel.endswith(".py") and not (
        is_test_filename(rel, include_js=False, include_conftest=False) or "/tests/" in rel
    )


def _provider_population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, _ROOT_DIR)
    except EmptyEnumeration:
        return []
    scanned = [rel for rel in tracked if _is_source_python(rel)]
    return scanned + [rel for rel in _EXTRA_FILES if (root / rel).is_file()]


REACH = declare(
    "provider-tool-schema-scan",
    discover=_provider_population,
    # Mid-window, from REACH.window(): population 129 (126 under llm_shared + 3 named builders), growth 5 -> [124, 129], pin 127. A new guard has no
    # base declaration, so the computed floor (repo_tests/_reach_base.py) cannot apply until it lands.
    floor=127,
    what="non-test provider python source",
    roots=(_ROOT_DIR, *_EXTRA_FILES),
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
    assert {"anthropic tool schema dict", "openai function tool dict"} <= hits


def test_no_provider_inlines_a_formatter() -> None:
    assert _offenders() == {}, (
        f"#16815: {_offenders()} inline a provider wire-format conversion; call the converter in "
        f"{_CANONICAL} instead of copying it."
    )
