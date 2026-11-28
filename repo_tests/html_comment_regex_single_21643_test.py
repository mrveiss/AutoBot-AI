# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The HTML-comment pattern ``<!--.*?-->`` is defined once, in ``autobot_shared/html_comments.py`` (#21643, #22261).

Detected: the literal pattern text in a string constant (not a docstring) of a tracked ``.py`` under ``repo_tests``,
``tools``, ``autobot-backend``, ``autobot_shared``, ``scripts`` or ``pipeline-scripts``, outside the owner (and this
guard); a file that does not parse is read as text. Prose that names the pattern (a comment, a docstring) is data.
NOT detected: an equivalent pattern spelled differently.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

from tools.lint._parse_cache import parse
from tools.lint._scan_helpers import tracked_paths

PATTERN = "<!--" + ".*?" + "-->"
OWNER = "autobot_shared/html_comments.py"
SELF = "repo_tests/html_comment_regex_single_21643_test.py"
TREES = ("repo_tests", "tools", "autobot-backend", "autobot_shared", "scripts", "pipeline-scripts")


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """The ids of the string-constant nodes that are a module, class or function docstring."""
    found: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        first = body[0] if isinstance(body, list) and body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            found.add(id(first.value))
    return found


def _defines_pattern(text: str) -> bool:
    """Whether *text* (Python source) carries the pattern in a string constant that is not a docstring."""
    try:
        tree = parse(text)
    except SyntaxError:
        return PATTERN in text
    docs = _docstring_nodes(tree)
    return any(
        isinstance(n, ast.Constant) and isinstance(n.value, str) and PATTERN in n.value and id(n) not in docs
        for n in ast.walk(tree)
    )


def _flag(files: dict[str, str]) -> list[str]:
    """The paths of *files* (path -> text) that define the pattern outside the owner and this guard."""
    return [p for p, text in files.items() if p not in (OWNER, SELF) and _defines_pattern(text)]


def _offenders() -> list[str]:
    root = repo_root()
    paths = [p for p in tracked_paths(root, *TREES) if p.endswith(".py")]
    assert paths, "no tracked python under the scanned trees; the scan would pass vacuously"
    return _flag({p: (root / p).read_text(encoding="utf-8") for p in paths})


def test_no_second_html_comment_pattern():
    assert _offenders() == []


def test_the_scan_covers_the_four_trees_the_copies_were_found_in():
    assert {"autobot-backend", "autobot_shared", "scripts", "pipeline-scripts"} <= set(TREES)
    tracked = tracked_paths(repo_root(), *TREES)
    for rel in (
        "autobot-backend/services/tool_output_filter.py",
        "scripts/research/safe_clone.py",
        "pipeline-scripts/issue_structure.py",
        "pipeline-scripts/landing_notes.py",
    ):
        assert rel in tracked, rel


def test_a_second_definition_in_another_file_is_flagged():
    files = {"repo_tests/other_test.py": f"X = re.compile({PATTERN!r})\n"}
    assert _flag(files) == ["repo_tests/other_test.py"]


def test_a_second_definition_in_each_newly_covered_tree_is_flagged():
    source = f"X = re.compile({PATTERN!r}, re.S)\n"
    files = {f"{tree}/copy.py": source for tree in ("autobot-backend", "autobot_shared", "scripts", "pipeline-scripts")}
    assert _flag(files) == list(files)


def test_a_pattern_embedded_in_a_larger_alternation_is_flagged():
    assert _flag({"scripts/x.py": f'X = re.compile(r"{PATTERN}|```.*?```")\n'}) == ["scripts/x.py"]


def test_prose_naming_the_pattern_is_not_flagged():
    source = f'"""The old ({PATTERN}) sniff backtracked."""\n#: a ``({PATTERN})*`` regex is slow\nX = 1\n'
    assert _flag({"autobot-backend/prose.py": source}) == []


def test_a_clean_file_and_the_owner_and_self_paths_are_not_flagged():
    files = {"repo_tests/clean_test.py": "X = 1\n", OWNER: f"P = {PATTERN!r}\n", SELF: f"P = {PATTERN!r}\n"}
    assert _flag(files) == []


def test_the_owner_still_defines_it():
    assert _defines_pattern((repo_root() / OWNER).read_text(encoding="utf-8"))
