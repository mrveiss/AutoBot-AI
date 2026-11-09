# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``tools.lint._parse_cache`` is the one way a repository guard parses Python (#20814).

Two things are held here:

* The primitive returns what ``ast.parse`` returns, memoises repeated calls, and
  raises ``SyntaxError`` every time, not once.
* Guards under ``repo_tests/`` stop calling ``ast.parse`` directly. The files
  that still do are listed in ``_parse_cache_allowed.py``, and the list is
  shrink-only in both directions: a new direct caller fails, and so does an
  entry whose file no longer needs it. The three modules that
  rewrite the trees they parse are the exception: a shared tree must not be
  edited, so they keep their own parse, and this test refuses them the cache.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from repo_tests._parse_cache_allowed import ALLOWED_DIRECT
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: Modules that rewrite parsed trees (``ast.NodeTransformer`` or assigning node
#: attributes), so a shared tree would carry their edits to the next caller. The
#: last three hand their trees to ``collected_test_model.collectable_tests``,
#: which sets ``class_decorator_list`` on the nodes it returns.
TREE_REWRITERS = frozenset(
    {
        "repo_tests/_ratchet_base.py",
        "repo_tests/collected_test_model.py",
        "repo_tests/guard_reach_meta_test.py",
        "repo_tests/collected_test_model_test.py",
        "repo_tests/fixed_sleep_then_call_assertion_test.py",
        "repo_tests/tests_that_return_instead_of_asserting_test.py",
    }
)


def _population(root: Path) -> list[str]:
    try:
        return tracked_paths(root, "repo_tests/*.py")
    except EmptyEnumeration:
        return []


#: 836 tracked modules under repo_tests/ with this guard and its allowed list.
#: Window [796, 836]; 814 sits inside it. Re-measure with `git ls-files 'repo_tests/*.py'`.
REACH = declare(
    "parse-cache-direct-parse-scan",
    discover=_population,
    what="python modules",
    roots=("repo_tests",),
    floor=850,  # mid-window: population 870, window (830, 870)
    growth=40,
)


def _ast_names(tree: ast.AST) -> tuple[set[str], set[str]]:
    """``(names bound to the ast module, names bound to ast.parse itself)``.

    Covers ``import ast``, ``import ast as _ast`` and ``from ast import parse [as p]``,
    wherever in the module the import sits.
    """
    modules, functions = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(a.asname or a.name for a in node.names if a.name == "ast")
        elif isinstance(node, ast.ImportFrom) and node.module == "ast":
            functions.update(a.asname or a.name for a in node.names if a.name == "parse")
    return modules, functions


def calls_ast_parse(source: str) -> bool:
    """Whether *source* calls ``ast.parse`` in code, under any alias. Strings and comments don't count."""
    try:
        tree = parse_cache.parse(source)
    except SyntaxError:
        return False
    modules, functions = _ast_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "parse" and isinstance(func.value, ast.Name):
            if func.value.id in modules:
                return True
        elif isinstance(func, ast.Name) and func.id in functions:
            return True
    return False


def imports_parse_cache(source: str) -> bool:
    """Whether *source* imports ``tools.lint._parse_cache`` in code, not merely mentions it."""
    try:
        tree = parse_cache.parse(source)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "tools.lint":
            if any(a.name == "_parse_cache" for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module == "tools.lint._parse_cache":
            return True
        elif isinstance(node, ast.Import) and any(a.name == "tools.lint._parse_cache" for a in node.names):
            return True
    return False


def _scan() -> tuple[list[str], list[str]]:
    """``(direct callers outside the rewriters, rewriters that import the cache)``."""
    root = repo_root()
    direct, cached_rewriters = [], []
    for rel in REACH.examined(root):
        source = (root / rel).read_text(encoding="utf-8")
        if rel in TREE_REWRITERS:
            if imports_parse_cache(source):
                cached_rewriters.append(rel)
        elif rel != "repo_tests/parse_cache_test.py" and calls_ast_parse(source):
            direct.append(rel)
    return direct, cached_rewriters


def test_parse_returns_what_ast_parse_returns() -> None:
    source = "def f(x):\n    return x + 1\n"
    assert ast.dump(parse_cache.parse(source)) == ast.dump(ast.parse(source))
    assert ast.dump(parse_cache.parse("x", mode="eval")) == ast.dump(ast.parse("x", mode="eval"))


def test_a_repeated_parse_is_served_from_the_memo() -> None:
    source = "value = 1  # parse_cache_test memo probe\n"
    first = parse_cache.parse(source)
    hits = parse_cache.cache_info().hits
    assert parse_cache.parse(source) is first
    assert parse_cache.cache_info().hits == hits + 1


def test_a_syntax_error_is_raised_on_every_call() -> None:
    for _ in range(2):
        with pytest.raises(SyntaxError):
            parse_cache.parse("def broken(:\n")


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import ast\ntree = ast.parse(text)\n", True),
        ("import ast as _ast\ntree = _ast.parse(text)\n", True),
        ("from ast import parse\ntree = parse(text)\n", True),
        ("from ast import parse as p\ntree = p(text)\n", True),
        ("x = 'ast.parse(text)'\n", False),
        ("# ast.parse(text)\n", False),
        ("tree = parse_cache.parse(text)\n", False),
        ("import ast\ntree = my.ast.parse(text)\n", False),
    ],
)
def test_the_detector_tells_a_call_from_text(source: str, expected: bool) -> None:
    assert calls_ast_parse(source) is expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("from tools.lint import _parse_cache as parse_cache\n", True),
        ("from tools.lint._parse_cache import parse\n", True),
        ("# tools.lint._parse_cache is not used here\n", False),
        ('"""Unlike _parse_cache, this module parses its own trees."""\n', False),
    ],
)
def test_the_import_check_tells_an_import_from_a_mention(source: str, expected: bool) -> None:
    assert imports_parse_cache(source) is expected


def test_no_new_direct_parse() -> None:
    direct, _ = _scan()
    unexpected = sorted(set(direct) - ALLOWED_DIRECT)
    assert not unexpected, (
        f"#20814: {unexpected} call ast.parse directly. Use `parse_cache.parse` from "
        "tools.lint._parse_cache instead."
    )


def test_every_allowed_direct_caller_still_needs_its_entry() -> None:
    direct, _ = _scan()
    stale = sorted(ALLOWED_DIRECT - set(direct))
    assert not stale, (
        f"#20814: {stale} no longer call ast.parse directly; remove them from " "repo_tests/_parse_cache_allowed.py."
    )


def test_tree_rewriters_keep_their_own_parse() -> None:
    _, cached_rewriters = _scan()
    assert not cached_rewriters, (
        f"#20814: {cached_rewriters} rewrite the trees they parse and must not share cached "
        "trees. Keep ast.parse there."
    )
