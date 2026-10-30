# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One dtype table and one compression set in `llm_shared/optimization` (#13049 C2, C3).

`taxonomy.py` owns both. The markers are syntactic: a dict literal that spells two or more of
the dtype names as keys is a second byte-width table; a set/frozenset literal holding the
`4bit`/`8bit` compression modes is a second validity set. The detector reads the syntax tree,
so prose naming the strings is not a definition.

Third marker: a set holding the GPT-2-style `model_type` names is a second layer-layout table.
"""

from __future__ import annotations

import ast
import functools

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_PKG = "autobot-backend/llm_shared/optimization/"
_CANONICAL = _PKG + "taxonomy.py"
_DTYPE_NAMES = frozenset({"fp16", "bf16", "fp32", "float16", "bfloat16", "float32"})
_COMPRESSION_MODES = frozenset({"4bit", "8bit"})
_GPT2_STYLE = frozenset({"gpt2", "gptj"})


def _str_consts(nodes: list[ast.expr | None]) -> set[str]:
    return {n.value for n in nodes if isinstance(n, ast.Constant) and isinstance(n.value, str)}


def _forks(source: str) -> tuple[bool, bool, bool]:
    """(second dtype table, second compression set, second layout set) in `source`."""
    dtype = comp = layout = False
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Dict) and len(_str_consts(node.keys) & _DTYPE_NAMES) >= 2:
            dtype = True
        elements = node.elts if isinstance(node, (ast.Set, ast.List, ast.Tuple)) else None
        if elements is not None and _COMPRESSION_MODES <= _str_consts(elements):
            comp = True
        if elements is not None and _GPT2_STYLE <= _str_consts(elements):
            layout = True
    return dtype, comp, layout


def _is_package_source(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.startswith(_PKG) and rel.endswith(".py") and not name.endswith("_test.py")


def _population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-backend/llm_shared/optimization")
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if _is_package_source(rel)]


REACH = declare(
    "optimization-taxonomy-scan",
    discover=_population,
    # Mid-window, from REACH.window().
    floor=18,
    what="non-test python source",
    roots=("autobot-backend/llm_shared/optimization",),
    growth=4,
)


@functools.lru_cache(maxsize=1)
def _forked_files() -> dict[str, tuple[bool, bool, bool]]:
    found = {}
    for rel in REACH.examined(repo_root()):
        flags = _forks((repo_root() / rel).read_text(encoding="utf-8"))
        if any(flags):
            found[rel] = flags
    return found


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a second byte table", 'T = {"fp16": 2, "float16": 2}\n', (True, False, False)),
        ("a second validity set", 'V = frozenset({"4bit", "8bit", "none"})\n', (False, True, False)),
        ("a second layout set", 'G = frozenset({"gpt2", "gptj", "gpt_neo"})\n', (False, False, True)),
        ("a lookup of one spelling", 'x = {"fp16": 2}\n', (False, False, False)),
        ("a comment naming them", '# {"fp16", "4bit", "8bit"}\nx = 1\n', (False, False, False)),
    ],
)
def test_the_matcher_tells_a_fork_from_a_use(label: str, source: str, expected: tuple[bool, bool, bool]) -> None:
    assert _forks(source) == expected, label


def test_only_the_taxonomy_module_defines_them() -> None:
    offenders = sorted(set(_forked_files()) - {_CANONICAL})
    assert not offenders, f"second dtype table or compression set outside taxonomy.py: {offenders}"


def test_the_canonical_module_defines_both_enums() -> None:
    tree = ast.parse((repo_root() / _CANONICAL).read_text(encoding="utf-8"))
    classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    assert {"Dtype", "Compression"} <= classes


def test_the_canonical_module_is_seen_defining_the_layout_set() -> None:
    assert _forked_files().get(_CANONICAL) == (False, False, True)


_FAMILY_HOME = "autobot_shared/model_taxonomy.py"


def _defines_architecture_family(source: str) -> bool:
    """True when `source` has a class statement named ArchitectureFamily."""
    return any(isinstance(n, ast.ClassDef) and n.name == "ArchitectureFamily" for n in ast.walk(ast.parse(source)))


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("a local enum", "class ArchitectureFamily(str, Enum):\n    SSM = 'ssm'\n", True),
        ("an import", "from autobot_shared.model_taxonomy import ArchitectureFamily\n", False),
        ("a re-export alias", "ArchitectureFamily = _Shared\n", False),
    ],
)
def test_the_matcher_tells_a_definition_from_an_import(label: str, source: str, expected: bool) -> None:
    assert _defines_architecture_family(source) is expected, label


_FAMILY_ROOTS = ("autobot-backend", "autobot-npu-worker", "autobot-slm-backend", "autobot_shared")


def _family_population(root) -> list[str]:
    try:
        tracked = tracked_paths(root, *_FAMILY_ROOTS)
    except EmptyEnumeration:
        return []
    return [rel for rel in tracked if rel.endswith(".py") and not rel.endswith("_test.py") and "/tests/" not in rel]


FAMILY_REACH = declare(
    "architecture-family-definition-scan",
    discover=_family_population,
    floor=3335,  # re-pinned mid-window (train 71) (#17844)
    what="non-test python source",
    roots=_FAMILY_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _family_definitions() -> tuple[str, ...]:
    found = []
    for rel in FAMILY_REACH.examined(repo_root()):
        text = (repo_root() / rel).read_text(encoding="utf-8")
        if "ArchitectureFamily" in text and _defines_architecture_family(text):
            found.append(rel)
    return tuple(found)


def test_architecture_family_is_defined_only_in_autobot_shared() -> None:
    assert _family_definitions() == (_FAMILY_HOME,)
