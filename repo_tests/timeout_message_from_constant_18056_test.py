# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A timeout message states the duration the code waits on, not a literal (#18056).

A timeout enforced from one value and reported from a literal drifts silently:
the message then states a duration the code no longer uses. Two had already
drifted when this guard landed. The environment analysis waited 240 s with the
LLM filter but reported 120 s. The pip install timeout is configurable by env
var but was reported as a fixed 300 s.

**What this detects:** a string literal (not a docstring) containing
"timed out after <digits>". A message built from the constant (an f-string or a
``%`` argument) carries no digits in the literal, so it passes.

**What it does not detect:** a message that spells the number in words, or a
literal reported far from the call that waits. Those are out of reach of a
syntactic check, and nothing here claims them.

The population is derived twice, from the syntax tree and from the raw text,
and the two are compared as sets, so a detector that silently stops seeing a
site fails instead of reporting clean (RATCHET_BASELINES.md).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint import _parse_cache as parse_cache
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_ROOT = repo_root()
_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared", "autobot-infrastructure")
_TEST_FILE = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$|conftest\.py$)")
#: "timed out after 30s", "Timeout after 120 seconds", "Analysis timeout (5 minutes)",
#: "Redis set timeout after 2s", "after 10s timeout". Case-insensitive.
_LITERAL = re.compile(r"(?i)\btime(d\s*)?\s*out\s*(after|\()\s*\d|\bafter\s+\d+\s*(s|sec|seconds?)\s+timeout")

#: Sites still stating a literal, with how many. **Only shrinks.** Each is a follow-up of #18056.
_PENDING = {
    # Five open PRs touch this file; the sites follow once they land.
    "autobot-slm-backend/api/code_sync.py": 2,
    # Says "5 minutes" but nothing in this file sets a timeout, so the stated
    # duration is not enforced here at all. That needs tracing to its caller, not a constant swap.
    "autobot-backend/secure_command_executor.py": 1,
    # Found once the detector covered "timeout after N", "timeout (N minutes)" and
    # "after Ns timeout" (case-insensitive). Each is checked against its wait in the follow-up.
    "autobot-backend/api/analytics_controller.py": 2,
    "autobot-backend/benchmarks/benchmark_belief_state.py": 2,
    "autobot-backend/chat_workflow/conversation.py": 1,
    "autobot-backend/security/enterprise/security_policy_manager.py": 1,
    "autobot-infrastructure/shared/scripts/ai-ml/optimize_llm_models.py": 1,
    "autobot-infrastructure/shared/scripts/diagnose_backend.py": 1,
    "autobot-slm-backend/api/roles.py": 1,
    "autobot-slm-backend/migrations/runner.py": 1,
}

#: Files whose only text hit is a comment, not a message. The text derivation sees them and the
#: tree does not, by design; naming them keeps the comparison exact rather than a subset check.
_PROSE_ONLY = frozenset(
    {
        "autobot-backend/api/codebase_analytics/endpoints/pattern_analysis.py",
        "autobot-backend/services/pty_command.py",
        "autobot-backend/utils/celery_reliability.py",
    }
)


def _source_files(root: Path) -> list[str]:
    try:
        paths = tracked_paths(root, *_ROOTS)
    except EmptyEnumeration:
        return []
    return [p for p in paths if p.endswith(".py") and not _TEST_FILE.search(p)]


def _all_python(root: Path) -> int:
    try:
        return sum(1 for p in tracked_paths(root, *_ROOTS) if p.endswith(".py"))
    except EmptyEnumeration:
        return 0


#: Measured 2026-11-03: non-test source is about 54% of tracked .py under these roots.
REACH = declare(
    "timeout-message-from-constant",
    discover=_source_files,
    reference=_all_python,
    min_fraction=0.4,
    what="non-test python source",
    roots=_ROOTS,
)


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                ids.add(id(first.value))
    return ids


def literal_sites(source: str) -> int:
    """Non-docstring string literals stating a timeout duration in digits."""
    try:
        tree = parse_cache.parse(source)
    except SyntaxError:
        return 0
    skip = _docstring_nodes(tree)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in skip
        and _LITERAL.search(node.value)
    )


def _populations() -> tuple[dict[str, int], set[str]]:
    by_ast: dict[str, int] = {}
    by_text: set[str] = set()
    examined = REACH.examined(_ROOT)
    for rel in examined:
        text = (_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if _LITERAL.search(text):
            by_text.add(rel)
            if count := literal_sites(text):
                by_ast[rel] = count
    REACH.completed(len(examined), _ROOT)
    return by_ast, by_text


def test_no_new_timeout_message_states_a_literal():
    by_ast, _ = _populations()
    grown = {rel: n for rel, n in by_ast.items() if n > _PENDING.get(rel, 0)}
    assert not grown, (
        f"timeout messages stating a literal duration: {grown}. Build the message from the value the "
        "wait uses (f'... {TIMEOUT_S:.0f}s'), so the two cannot drift (#18056)."
    )


def test_the_pending_list_only_shrinks():
    by_ast, _ = _populations()
    stale = {rel: (n, by_ast.get(rel, 0)) for rel, n in _PENDING.items() if by_ast.get(rel, 0) < n}
    assert not stale, f"fixed sites still listed (listed, found): {stale}. Lower or delete their _PENDING entries."


def test_the_two_derivations_agree():
    """The text search and the syntax tree must name the same files, or the detector has gone blind."""
    by_ast, by_text = _populations()
    assert not set(by_ast) - by_text, f"tree-only: {sorted(set(by_ast) - by_text)}: the text derivation has gone blind"
    assert by_text - set(by_ast) == _PROSE_ONLY, (
        f"text-only now {sorted(by_text - set(by_ast))}, recorded {sorted(_PROSE_ONLY)}. A new comment or docstring "
        "hit belongs in _PROSE_ONLY; a recorded one that left means a literal was missed or the comment changed."
    )


def test_the_detector_reads_literals_not_prose():
    assert literal_sites('x = "timed out after 30 seconds"') == 1
    assert literal_sites('x = "Timeout after 120 seconds"') == 1
    assert literal_sites('x = "Analysis timeout (5 minutes)"') == 1
    assert literal_sites('x = "failed after 10s timeout"') == 1
    assert literal_sites('x = f"timed out after {T:.0f} seconds"') == 0
    assert literal_sites('def f():\n    """It timed out after 30 seconds once."""\n') == 0
    assert literal_sites('log("timed out after %.0fs", T)') == 0
