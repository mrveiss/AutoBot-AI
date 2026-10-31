# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chunk's identity is derived in `knowledge/chunk_identity.py` alone (#18142).

Eight modules once derived it eight ways, so a graph node and its vector chunk disagreed about
which chunk they were. Two inline shapes are flagged, by AST (a docstring or comment that names
`chunk_id` is not a read):

* a READ -- `x.get("chunk_id"...)` or `x["chunk_id"]` -- which is a private precedence rule;
* a DERIVATION -- `<hash>.hexdigest()[:N]` assigned to, or returned from, something named `*chunk*`.

Sites not yet moved are in a shrink-only baseline. Skipped directories are matched on the
REPO-RELATIVE parts (#18972), so a checkout under `.worktrees` is not read as clean.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare
from repo_tests.chunk_identity_baseline_18142 import BASELINE

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_HOME = "autobot-backend/knowledge/chunk_identity.py"
_SKIP_PARTS = frozenset({"__pycache__", "node_modules", ".worktrees", "venv", ".venv", "tests", "test"})


def _is_test(rel: str) -> bool:
    name = Path(rel).name
    return name.endswith("_test.py") or name.startswith("test_") or name == "conftest.py"


def _candidates(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, "autobot-backend/*.py", "autobot_shared/*.py")
    except EmptyEnumeration:
        return []
    return [p for p in paths if _kept(p)]


def _kept(rel: str) -> bool:
    """Decided on the repo-RELATIVE parts only, so the checkout's own location cannot skip a file (#18972)."""
    return not _SKIP_PARTS & set(Path(rel).parts) and not _is_test(rel)


REACH = declare(
    "chunk-identity-single-home-18142",
    discover=_candidates,
    floor=3012,  # mid-window: population 3112, window (2912, 3112)
    growth=200,
    what="tracked non-test .py files",
    roots=("autobot-backend/", "autobot_shared/"),
)


def _is_chunk_id_read(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
        return bool(node.args) and _is_chunk_key(node.args[0])
    return isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load) and _is_chunk_key(node.slice)


def _is_chunk_key(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "chunk_id"


def _is_hash_prefix(node: ast.AST) -> bool:
    """`<anything>.hexdigest()[:N]` -- a truncated digest used as an id."""
    if not (isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Slice) and node.slice.upper):
        return False
    call = node.value
    return isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "hexdigest"


def _names(node: ast.AST) -> list[str]:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return [node.name]
    targets = node.targets if isinstance(node, ast.Assign) else [getattr(node, "target", None)]
    return [t.id if isinstance(t, ast.Name) else t.attr for t in targets if isinstance(t, (ast.Name, ast.Attribute))]


def _chunk_named(node: ast.AST) -> bool:
    return any("chunk" in n.lower() for n in _names(node))


def _derivations(tree: ast.AST) -> int:
    """Hash-prefix expressions inside a `*chunk*` function or on the right of a `*chunk*` assignment."""
    found = 0
    for scope in ast.walk(tree):
        if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Assign, ast.AnnAssign)) and _chunk_named(
            scope
        ):
            found += sum(_is_hash_prefix(n) for n in ast.walk(scope))
    return found


def inline_sites(source: str) -> int:
    """How many inline chunk-identity reads or derivations *source* holds."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return 0
    return sum(_is_chunk_id_read(n) for n in ast.walk(tree)) + _derivations(tree)


def measure(files: dict[str, str]) -> dict[str, int]:
    """Inline-site count per repo-relative path, home module and clean files omitted."""
    counts = {rel: inline_sites(text) for rel, text in files.items() if rel != _HOME}
    return {rel: n for rel, n in counts.items() if n}


def _parses(source: str) -> bool:
    try:
        ast.parse(source)
    except (SyntaxError, ValueError):
        return False
    return True


def _read_all() -> dict[str, str]:
    """Files read AND parsed; the reach floor binds to these, not to the candidates listed (#19149)."""
    files = {}
    for rel in REACH.examined(_ROOT):
        try:
            text = (_ROOT / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if _parses(text):
            files[rel] = text
    REACH.completed(len(files), _ROOT)
    return files


def test_no_module_derives_chunk_identity_outside_the_helper() -> None:
    found = measure(_read_all())
    new = {rel: n for rel, n in found.items() if n > BASELINE.get(rel, 0)}
    assert new == {}, f"call knowledge.chunk_identity.resolve_chunk_id instead of deriving the id inline: {new}"


def test_the_baseline_only_shrinks() -> None:
    found = measure(_read_all())
    stale = {rel: (n, found.get(rel, 0)) for rel, n in BASELINE.items() if found.get(rel, 0) < n}
    assert stale == {}, f"lower these baseline entries to the current count (listed, now): {stale}"


def test_the_home_module_is_what_the_guard_exempts() -> None:
    assert (_ROOT / _HOME).is_file()
    assert "resolve_chunk_id" in (_ROOT / _HOME).read_text(encoding="utf-8")


# --- contrast fixtures: each pair differs only in the thing the detector keys on ---------------

_READ = 'def f(m):\n    return m.get("chunk_id") or m["chunk_id"]\n'
_MENTION = '"""Reads chunk_id."""\nKEY = "chunk_id"\ndef f(m):\n    m["chunk_id"] = 1\n    return m.get("other")\n'
_DERIVE = "import hashlib\ndef _chunk_id(k):\n    return hashlib.md5(k.encode()).hexdigest()[:12]\n"
_DERIVE_ASSIGN = "import hashlib\nchunk_key = hashlib.sha1(b'x').hexdigest()[:16]\n"
_OTHER_HASH = "import hashlib\ndef cache_key(k):\n    return hashlib.md5(k.encode()).hexdigest()[:12]\n"
_FULL_DIGEST = "import hashlib\ndef chunk_digest(k):\n    return hashlib.md5(k.encode()).hexdigest()\n"
_HELPER = "from knowledge.chunk_identity import resolve_chunk_id\ndef f(r):\n    return resolve_chunk_id(r)\n"


def test_an_inline_read_is_caught_and_a_mention_or_write_is_not() -> None:
    assert inline_sites(_READ) == 2
    assert inline_sites(_MENTION) == 0


def test_a_chunk_named_hash_prefix_is_caught_and_other_hashes_are_not() -> None:
    assert inline_sites(_DERIVE) == 1
    assert inline_sites(_DERIVE_ASSIGN) == 1
    assert inline_sites(_OTHER_HASH) == 0
    assert inline_sites(_FULL_DIGEST) == 0


def test_calling_the_helper_is_clean_and_the_home_module_is_exempt() -> None:
    assert inline_sites(_HELPER) == 0
    assert measure({_HOME: _READ, "autobot-backend/x.py": _READ}) == {"autobot-backend/x.py": 2}


def test_an_unparsable_file_is_not_a_crash_and_is_not_a_parse() -> None:
    assert inline_sites("def (:\n") == 0
    assert not _parses("def (:\n")
    assert _parses(_HELPER)


def test_skip_dirs_use_repo_relative_parts() -> None:
    """Only repo-relative parts decide; `.worktrees` in the checkout path is never an input (#18972)."""
    assert _kept("autobot-backend/services/x.py")
    assert not _kept("autobot-backend/tests/x.py")
    assert not _kept("autobot-backend/services/x_test.py")
    assert not _kept("autobot_shared/test_x.py")
