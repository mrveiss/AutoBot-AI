# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``tools.lint._parse_cache`` is the one way a repository guard parses Python (#20814).

Two things are held here:

* The primitive returns what ``ast.parse`` returns, memoises repeated calls, and
  raises ``SyntaxError`` every time, not once.
* Guards under ``repo_tests/`` don't call ``ast.parse`` directly. Four files at
  their size ceiling are listed until they are split (#20820). The three modules that
  rewrite the trees they parse are the exception: a shared tree must not be
  edited, so they keep their own parse, and this test refuses them the cache.
"""

from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

#: Modules that rewrite parsed trees (``ast.NodeTransformer`` or assigning node
#: attributes), so a shared tree would carry their edits to the next caller.
TREE_REWRITERS = frozenset(
    {
        "repo_tests/_ratchet_base.py",
        "repo_tests/collected_test_model.py",
        "repo_tests/guard_reach_meta_test.py",
    }
)

#: Guards that still call ``ast.parse`` directly, rewriters aside. Each sits at
#: its file-size ceiling and cannot take the import line until it is split
#: (#20820). Shrink only: remove an entry when its file moves to the cache.
ALLOWED_DIRECT = frozenset(
    {
        "repo_tests/enum_union_guard_test.py",
        "repo_tests/phase_validation_paths_and_skips_17089_test.py",
        "repo_tests/router_auth_enumerator.py",
        "repo_tests/sync_deletions_ansible_wiring_16310_test.py",
    }
)


def _population(root: Path) -> list[str]:
    try:
        return tracked_paths(root, "repo_tests/*.py")
    except EmptyEnumeration:
        return []


#: 834 tracked modules under repo_tests/ when this guard landed. Window
#: [794, 834]; pinned mid-window. Re-measure with `git ls-files 'repo_tests/*.py'`.
REACH = declare(
    "parse-cache-direct-parse-scan",
    discover=_population,
    what="python modules",
    roots=("repo_tests",),
    floor=814,
    growth=40,
)


def calls_ast_parse(source: str) -> bool:
    """Whether *source* calls ``ast.parse(`` in code. Text inside strings and comments is ignored."""
    try:
        toks = [t for t in tokenize.generate_tokens(io.StringIO(source).readline) if t.type != tokenize.NL]
    except (tokenize.TokenError, SyntaxError):
        return False
    return any(
        a.string == "ast"
        and d.string == "."
        and p.string == "parse"
        and o.string == "("
        and a.type == tokenize.NAME
        and (i == 0 or toks[i - 1].string != ".")
        for i, (a, d, p, o) in enumerate(zip(toks, toks[1:], toks[2:], toks[3:]))
    )


def _scan() -> tuple[list[str], list[str]]:
    """``(direct callers outside the rewriters, rewriters that import the cache)``."""
    root = repo_root()
    direct, cached_rewriters = [], []
    for rel in REACH.examined(root):
        source = (root / rel).read_text(encoding="utf-8")
        if rel in TREE_REWRITERS:
            if "_parse_cache" in source:
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
        ("tree = ast.parse(text)\n", True),
        ("x = 'ast.parse(text)'\n", False),
        ("# ast.parse(text)\n", False),
        ("tree = parse_cache.parse(text)\n", False),
        ("tree = my.ast.parse(text)\n", False),
    ],
)
def test_the_detector_tells_a_call_from_text(source: str, expected: bool) -> None:
    assert calls_ast_parse(source) is expected


def test_no_guard_calls_ast_parse_directly() -> None:
    direct, _ = _scan()
    unexpected = sorted(set(direct) - ALLOWED_DIRECT)
    assert not unexpected, (
        f"#20814: {unexpected} call ast.parse directly. Use `parse_cache.parse` from "
        "tools.lint._parse_cache instead."
    )


def test_every_allowed_direct_caller_still_needs_its_entry() -> None:
    direct, _ = _scan()
    stale = sorted(ALLOWED_DIRECT - set(direct))
    assert not stale, f"#20820: {stale} no longer call ast.parse directly; remove them from ALLOWED_DIRECT."


def test_tree_rewriters_keep_their_own_parse() -> None:
    _, cached_rewriters = _scan()
    assert not cached_rewriters, (
        f"#20814: {cached_rewriters} rewrite the trees they parse and must not share cached "
        "trees. Keep ast.parse there."
    )
