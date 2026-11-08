# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
""" "Is this file name a test file?" is answered by `autobot_shared.testfile_names` alone (#21078).

Forty-odd hand-written copies had drifted: some omitted `conftest.py`, some omitted the JS `.test.`/`.spec.`
names, some matched `test_` differently. A rule change had to be made in every copy and any copy missed
kept the old answer.

The detector flags the literals a hand-written file-name rule is made of, by AST (a docstring or comment
naming them is not a rule):

* ``x.endswith("_test.py")`` / ``x.endswith("_test")`` (also as a tuple member);
* ``x == "conftest.py"`` / ``"conftest"`` (``==``, ``!=``, ``in``, ``not in``, either side);
* ``".test." in x`` / ``".spec." in x``.

Directory rules (``"tests" in parts``) are not flagged: they stay with the caller and combine with the
predicate. Sites not yet moved are in a shrink-only baseline, each group with its reason.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.test_name_predicate_baseline_21078 import BASELINE

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_CANONICAL = "autobot_shared/testfile_names.py"
_SUFFIX_LITERALS = frozenset({"_test.py", "_test"})
_CONFTEST_LITERALS = frozenset({"conftest.py", "conftest"})
_JS_INFIXES = frozenset({".test.", ".spec."})
#: The source trees swept. ``.claude/``, ``docs/``, ``debug/``, the worker stubs and the ``.github``/``site``/``data``
#: leftovers hold a few dozen tracked .py files and are NOT read (RATCHET_BASELINES rule 1: the boundary is declared here).
_ROOTS = (
    "autobot-backend/",
    "autobot-slm-backend/",
    "autobot_shared/",
    "autobot-infrastructure/",
    "autobot-npu-worker/",
    "repo_tests/",
    "tools/",
    "scripts/",
    "pipeline-scripts/",
    "plugins/",
    "libs/",
)


def _discover(root: Path) -> list[str]:
    try:
        return tracked_paths(root, *(f"{prefix}*.py" for prefix in _ROOTS))
    except EmptyEnumeration:
        return []


#: About 8,200 of the tracked tree's ~13,700 files; 0.5 fires once a fifth of the sweep goes unread.
REACH = declare(
    "test-name-predicate-single-home-21078",
    discover=_discover,
    min_fraction=0.5,
    what="tracked .py files",
    roots=_ROOTS,
)


def _const(node: ast.AST) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _is_suffix_check(node: ast.AST) -> bool:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "endswith"):
        return False
    if not node.args:
        return False
    arg = node.args[0]
    values = arg.elts if isinstance(arg, (ast.Tuple, ast.List, ast.Set)) else [arg]
    return any(_const(v) in _SUFFIX_LITERALS for v in values)


def _is_name_comparison(node: ast.AST) -> bool:
    if not isinstance(node, ast.Compare):
        return False
    operands = [node.left, *node.comparators]
    if any(_const(o) in _CONFTEST_LITERALS for o in operands):
        return True
    return _const(node.left) in _JS_INFIXES and isinstance(node.ops[0], (ast.In, ast.NotIn))


def handwritten_sites(source: str) -> int:
    """How many hand-written test-file-name rule literals *source* holds."""
    try:
        tree = parse_cache.parse(source)
    except (SyntaxError, ValueError):
        return 0
    return sum(_is_suffix_check(n) or _is_name_comparison(n) for n in ast.walk(tree))


def measure(files: dict[str, str]) -> dict[str, int]:
    """Site count per repo-relative path, the canonical module and clean files omitted."""
    counts = {rel: handwritten_sites(text) for rel, text in files.items() if rel != _CANONICAL}
    return {rel: n for rel, n in counts.items() if n}


@functools.lru_cache(maxsize=1)
def _read_all() -> dict[str, str]:
    """Files read; the reach floor binds to these, not to the candidates listed (#19149)."""
    files = {}
    for rel in REACH.examined(_ROOT):
        try:
            files[rel] = (_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    REACH.completed(len(files), _ROOT)
    return files


def test_no_file_hand_writes_a_test_name_rule_beyond_the_baseline() -> None:
    found = measure(_read_all())
    new = {rel: n for rel, n in found.items() if n > BASELINE.get(rel, 0)}
    assert new == {}, f"call autobot_shared.testfile_names.is_test_filename instead of a hand-written rule: {new}"


def test_the_baseline_only_shrinks() -> None:
    found = measure(_read_all())
    stale = {rel: (n, found.get(rel, 0)) for rel, n in BASELINE.items() if found.get(rel, 0) < n}
    assert stale == {}, f"lower these baseline entries to the current count (listed, now): {stale}"


def test_the_canonical_module_is_what_the_guard_exempts() -> None:
    source = (_ROOT / _CANONICAL).read_text(encoding="utf-8")
    assert "def is_test_filename" in source
    assert handwritten_sites(source) == 0, "the canonical module is exempt by path; it must also need no exemption"


# --- planted controls: each pair differs only in the thing the detector keys on -----------------

_SUFFIX = 'def is_test(p):\n    return p.name.endswith("_test.py")\n'
_SUFFIX_TUPLE = 'def is_test(n):\n    return n.endswith(("_spec.py", "_test"))\n'
_CONFTEST = 'def skip(p):\n    return p.name == "conftest.py"\n'
_JS = 'def skip(n):\n    return ".test." in n or ".spec." in n\n'
_FULL_HAND_COPY = (
    "def _is_test(path):\n"
    "    name = path.name\n"
    '    return name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py"\n'
)
_CANONICAL_CALL = (
    "from autobot_shared.testfile_names import is_test_filename\n"
    "def _is_test(path):\n    return is_test_filename(path.name, include_js=False)\n"
)
_MENTION = '"""A test lives in x_test.py or conftest.py."""\nNAME = "_test.py"\nDIRS = ("tests",)\n'
_DIRECTORY_RULE = 'def skip(parts):\n    return "tests" in parts\n'


def test_a_planted_hand_written_predicate_is_flagged() -> None:
    assert handwritten_sites(_SUFFIX) == 1
    assert handwritten_sites(_SUFFIX_TUPLE) == 1
    assert handwritten_sites(_CONFTEST) == 1
    assert handwritten_sites(_JS) == 2
    assert handwritten_sites(_FULL_HAND_COPY) == 2
    assert measure({"autobot-backend/planted.py": _FULL_HAND_COPY}) == {"autobot-backend/planted.py": 2}


def test_the_canonical_call_a_mention_and_a_directory_rule_are_not_flagged() -> None:
    assert handwritten_sites(_CANONICAL_CALL) == 0
    assert handwritten_sites(_MENTION) == 0
    assert handwritten_sites(_DIRECTORY_RULE) == 0


def test_the_canonical_path_is_exempt_whatever_it_holds() -> None:
    assert measure({_CANONICAL: _FULL_HAND_COPY}) == {}


def test_an_unparsable_file_is_not_a_crash() -> None:
    assert handwritten_sites("def (:\n") == 0
