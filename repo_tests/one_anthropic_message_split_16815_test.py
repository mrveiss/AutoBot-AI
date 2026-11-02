# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One Anthropic-family message split (#16815).

The Anthropic Messages API wants the system prompt lifted out of the message list. That split
was written three times in `llm_shared/providers` (`anthropic.py`, `vertexai.py`, `bedrock.py`).
It now lives once in `anthropic_format.py`.

The marker is a single function that BOTH compares a role to the literal `"system"` AND builds
a `{"role": ..., "content": ...}` dict: separating the system message while emitting Anthropic
messages. A prompt-string builder (Llama, Nova) compares the role but builds no such dict, so it
is not a copy, and neither is Nova's `content: [{"text": ...}]`, a different wire shape. The detector reads the syntax tree, so prose naming either is not a definition.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot-backend/llm_shared/providers/anthropic_format.py"
_ROOT = "autobot-backend/llm_shared/providers"
_CALLERS = tuple(f"{_ROOT}/{n}.py" for n in ("anthropic", "vertexai", "bedrock"))


def _is_system_literal(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute):  # CategoryDefaults.ROLE_SYSTEM
        return node.attr == "ROLE_SYSTEM"
    return isinstance(node, ast.Constant) and node.value == "system"


def _compares_to_system(fn: ast.AST) -> bool:
    return any(
        isinstance(n, ast.Compare) and any(_is_system_literal(c) for c in [n.left, *n.comparators])
        for n in ast.walk(fn)
    )


def _builds_role_content_dict(fn: ast.AST) -> bool:
    for n in ast.walk(fn):
        if isinstance(n, ast.Dict):
            by_key = {k.value: v for k, v in zip(n.keys, n.values) if isinstance(k, ast.Constant)}
            # A literal list as `content` is another API's shape (Nova's `[{"text": ...}]`), not a
            # pass-through of Anthropic content.
            if {"role", "content"} <= by_key.keys() and not isinstance(by_key["content"], ast.List):
                return True
    return False


def _split_functions(source: str) -> list[str]:
    """Names of functions in `source` that separate `system` and build Anthropic message dicts."""
    return [
        n.name
        for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and _compares_to_system(n)
        and _builds_role_content_dict(n)
    ]


def _is_source_python(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.endswith(".py") and not (name.endswith("_test.py") or name.startswith("test_") or "/tests/" in rel)


def _population(root: Path) -> list[str]:
    try:
        tracked = tracked_paths(root, _ROOT)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_source_python(rel)]


REACH = declare(
    "anthropic-message-split-scan",
    discover=_population,
    # Mid-window, from REACH.window(); the arithmetic is on the PR, not here.
    floor=20,
    what="non-test provider source",
    roots=(_ROOT,),
    growth=10,
)

_SPLIT = (
    "def split(messages):\n"
    "    system = ''\n"
    "    out = []\n"
    "    for m in messages:\n"
    "        if m.get('role') == 'system':\n"
    "            system = m.get('content', '')\n"
    "        else:\n"
    "            out.append({'role': m.get('role', 'user'), 'content': m.get('content', '')})\n"
    "    return system, out\n"
)
_PROMPT_STRING = (
    "def prompt(messages):\n"
    "    text = ''\n"
    "    for m in messages:\n"
    "        if m.get('role') == 'system':\n"
    "            text += '<s>' + m['content']\n"
    "    return text\n"
)
_NOVA = (
    "def nova(messages):\n"
    "    out = []\n"
    "    for m in messages:\n"
    "        if m.get('role') != 'system':\n"
    "            out.append({'role': m.get('role', 'user'), 'content': [{'text': m.get('content', '')}]})\n"
    "    return [m for m in messages if m.get('role') == 'system'], out\n"
)
_DICT_ONLY = "def wrap(m):\n    return {'role': 'user', 'content': m}\n"


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a split copy", _SPLIT, ["split"]),
        (
            "a split copy as a method",
            "class P:\n" + _SPLIT.replace("\n", "\n    ").replace("def", "    def", 1),
            ["split"],
        ),
        ("a split copy using the role constant", _SPLIT.replace("'system'", "CategoryDefaults.ROLE_SYSTEM"), ["split"]),
        ("a prompt-string builder (role check, no message dict)", _PROMPT_STRING, []),
        ("a Nova builder (list-literal content, another wire shape)", _NOVA, []),
        ("a message wrapper (dict, no system check)", _DICT_ONLY, []),
        ("a comment naming both", "# if role == 'system': {'role':'user','content':x}\nx = 1\n", []),
    ],
)
def test_the_matcher_tells_a_split_from_a_lookalike(label: str, source: str, expected: list[str]) -> None:
    assert _split_functions(source) == expected, label


@functools.lru_cache(maxsize=1)
def _splitters() -> tuple[tuple[str, ...], int]:
    found: list[str] = []
    parsed = 0
    for rel in REACH.examined(repo_root()):
        parsed += 1
        if _split_functions((repo_root() / rel).read_text(encoding="utf-8")):
            found.append(rel)
    return tuple(found), parsed


def test_the_scan_is_not_vacuous() -> None:
    _, parsed = _splitters()
    assert parsed >= 10, f"parsed {parsed} provider files"


def test_the_message_split_exists_once() -> None:
    found, _ = _splitters()
    assert found == (_CANONICAL,), (
        f"#16815: {list(found)} separate `system` and build Anthropic messages; the split lives once in "
        f"{_CANONICAL}. Call `split_system_and_chat(messages)` instead of copying its body."
    )


@pytest.mark.parametrize("rel", _CALLERS)
def test_each_anthropic_family_provider_calls_the_shared_split(rel: str) -> None:
    tree = ast.parse((repo_root() / rel).read_text(encoding="utf-8"))
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "split_system_and_chat"
    ]
    assert calls, f"#16815: {rel} no longer routes its message split through split_system_and_chat"
