# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One content digest (#15722, umbrella #13916).

`autobot_shared/content_digest.py` is the only place that turns content into a SHA-256 digest:
`content_digest(content, width=None)` for the full form, `width=n` for a stored short form, and
`fact_dedup_key` for the fact deduplication key. Two functions named `content_hash` used to
return different widths of the same digest, and the 16-char truncation was written inline in
five more places, so the Redis write path and the cleanup path derived the same key apart.

The marker is a `sha256(<x>.encode(...))` call whose input is named like content. The detector
reads the syntax tree, so a docstring or comment is not a copy. Identifier hashes (a URL, a
path, an API key) are not content digests and their names do not match.

Sites that still hash content inline are listed in `_UNCONVERTED` with the reason. The list may
only shrink: an entry whose file no longer carries the pattern fails, so converting a site forces
its removal.
"""

from __future__ import annotations

import ast
import functools
import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_CANONICAL = "autobot_shared/content_digest.py"
_ROOTS = ("autobot-backend", "autobot_shared")
_CONTENT_NAME = re.compile(r"content|text|^code$|element_code|body|hash_source|source", re.IGNORECASE)

_QUEUED = "queued on another branch; convert when it merges"
_CEILING = "grandfathered over its size ceiling; the import line would grow it"
_TOOL = "standalone code-analysis tool script, not a stored key"
_UNCONVERTED = {
    "autobot-backend/agents/npu_code_search_agent.py": _CEILING,
    "autobot-backend/agents/scope_enforcement.py": "x- prefixed id, unconverted",
    "autobot-backend/api/analytics_continuous_learning.py": _CEILING,
    "autobot-backend/code_analysis/auto-tools/playwright_sanitizer.py": _TOOL,
    "autobot-backend/code_analysis/auto-tools/security_deep_sanitizer.py": _TOOL,
    "autobot-backend/code_analysis/auto-tools/security_sanitizer.py": _TOOL,
    "autobot-backend/services/claim_verifier.py": "claim-text digest, unconverted",
    "autobot-backend/services/npu_client.py": "encodes with errors=replace, a different input form",
}


def _terminal_name(node: ast.AST) -> str:
    if isinstance(node, (ast.Name, ast.Attribute)):
        return node.id if isinstance(node, ast.Name) else node.attr
    if isinstance(node, ast.Subscript):
        return _terminal_name(node.value)
    return ""


def _hashes_content(source: str) -> bool:
    """True when `source` calls sha256 on `<content-named expr>.encode(...)`."""
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and node.args):
            continue
        func = node.func
        if not (
            isinstance(func, ast.Attribute)
            and func.attr == "sha256"
            or isinstance(func, ast.Name)
            and func.id == "sha256"
        ):
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and arg.func.attr == "encode":
            if _CONTENT_NAME.search(_terminal_name(arg.func.value)):
                return True
    return False


@pytest.mark.parametrize(
    ("label", "source", "expected"),
    [
        ("inline content digest", "h = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]\n", True),
        ("attribute content", "h = hashlib.sha256(request.content.encode()).hexdigest()\n", True),
        ("bare imported sha256", "h = sha256(text.encode()).hexdigest()\n", True),
        ("an identifier hash", "h = hashlib.sha256(url.encode()).hexdigest()\n", False),
        ("a bytes digest", "h = hashlib.sha256(payload_bytes).hexdigest()\n", False),
        ("a docstring naming it", '"""hashlib.sha256(content.encode())"""\nx = 1\n', False),
        ("the canonical call", "h = content_digest(content, width=16)\n", False),
    ],
)
def test_the_matcher_tells_a_content_digest_from_an_identifier_hash(label: str, source: str, expected: bool) -> None:
    assert _hashes_content(source) is expected, label


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
    "one-content-digest-scan",
    discover=_source_population,
    floor=2825,  # re-pinned mid-window (train 81 on main)
    # Mid-window, from REACH.window(): 2730 measured, growth 300 -> 150 of headroom each way.,
    what="non-test python source",
    roots=_ROOTS,
    growth=300,
)


@functools.lru_cache(maxsize=1)
def _hashers() -> tuple[str, ...]:
    found = []
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "sha256" in source and _hashes_content(source):
            found.append(rel)
    return tuple(found)


def test_no_local_content_digest_outside_the_canonical_module() -> None:
    new = sorted(set(_hashers()) - set(_UNCONVERTED) - {_CANONICAL})
    assert not new, (
        f"#15722: {new} hash content with an inline sha256(...). Use "
        f"`from autobot_shared.content_digest import content_digest` (width=n for a stored short form) "
        f"or `fact_dedup_key` for the fact dedup key."
    )


def test_every_unconverted_entry_still_carries_the_pattern() -> None:
    stale = sorted(set(_UNCONVERTED) - set(_hashers()))
    assert not stale, f"#15722: {stale} no longer hash content inline; remove them from _UNCONVERTED."


def test_the_canonical_module_does_the_hashing() -> None:
    text = (repo_root() / _CANONICAL).read_text(encoding="utf-8")
    assert "hashlib.sha256" in text and "FACT_DEDUP_WIDTH = 16" in text


def test_the_dedup_width_and_content_hash_name_exist_once() -> None:
    """AC1/AC2: one width constant, and `content_hash` is defined as a function only in fact_store."""
    widths, defs = [], []
    for rel in REACH.examined(repo_root()):
        source = (repo_root() / rel).read_text(encoding="utf-8")
        if "_CONTENT_HASH_WIDTH" in source:
            widths.append(rel)
        if "def content_hash(" in source and "/knowledge/" in rel:
            defs.append(rel)
    assert widths == [], f"#15722: {widths} define their own dedup width"
    assert defs == ["autobot-backend/knowledge/fact_store.py"], defs
