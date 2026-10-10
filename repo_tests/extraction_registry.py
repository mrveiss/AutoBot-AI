# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every concept that was extracted to one canonical site, and how that is held (#17995).

An extraction migrates N-1 call sites, nothing guards the Nth, and the survivor then
misses every later fix. This table is the "guard is part of the extraction" half: a PR
that extracts a concept adds ONE entry here, and ``extraction_registry_17995_test`` fails
when a module other than the canonical site defines or inlines it.

Not a replacement for ``symbol_fork_baseline.json`` (module-level NAME collisions, a
shrink-only debt list) or ``store_authority.py`` (which store owns a persisted datum);
neither names a canonical *code* site per concept or sees an inlined copy.

Each entry has a ``status``:

``GUARDED``           this registry's guard enforces it, via ``detector``.
``GUARDED_ELSEWHERE`` a dedicated guard enforces it; ``guard`` names that test file, which
                      the registry test requires to exist. Candidates to fold in here.
``DEFERRED``          not migrated yet; ``reason`` names the owner and why.
``WAITING``           blocked on another issue; ``reason`` names it.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Callable

GUARDED = "guarded"
GUARDED_ELSEWHERE = "guarded-elsewhere"
DEFERRED = "deferred"
WAITING = "waiting"

#: ``(tree) -> bool``: does this module define or inline the concept?
Detector = Callable[[ast.AST], bool]


def _calls(fn: ast.AST) -> set[str]:
    """Bare or attribute names of every call inside *fn*."""
    names: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            names.add(f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", ""))
    return names


def inlines_source_root(tree: ast.AST) -> bool:
    """A function that looks a source up and RETURNS ``Path(<x>.clone_path)`` (#2760, #17982).

    Keyed on the return, not on reading ``clone_path``: the indexing paths legitimately
    read it, and only a function that hands back the path is a second resolver.
    """
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or "get_source" not in _calls(fn):
            continue
        for ret in (n for n in ast.walk(fn) if isinstance(n, ast.Return)):
            v = ret.value
            if (
                isinstance(v, ast.Call)
                and getattr(v.func, "id", None) == "Path"
                and any(isinstance(a, ast.Attribute) and a.attr == "clone_path" for a in v.args)
            ):
                return True
    return False


def inlines_wav_duration(tree: ast.AST) -> bool:
    """``<wav>.getnframes() / <rate>``: the formula ``wav_duration_seconds`` owns (#13841)."""
    return any(
        isinstance(n, ast.BinOp)
        and isinstance(n.op, ast.Div)
        and isinstance(n.left, ast.Call)
        and getattr(n.left.func, "attr", None) == "getnframes"
        for n in ast.walk(tree)
    )


def inlines_egress_decision(tree: ast.AST) -> bool:
    """An ``egress_governor.evaluate(...)`` call or an ``egress_denied`` payload (#14901)."""
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "evaluate":
            if getattr(n.func.value, "id", None) == "egress_governor":
                return True
        if isinstance(n, ast.Constant) and n.value == "egress_denied":
            return True
    return False


@dataclass(frozen=True)
class Extraction:
    """One extracted concept: where it lives, who may spell it, how it is held."""

    concept: str
    issues: tuple[str, ...]
    canonical: str
    symbol: str
    status: str
    detector: Detector | None = None
    #: Files other than ``canonical`` allowed to match, each with a reason (shrink-only).
    allowed: tuple[tuple[str, str], ...] = ()
    guard: str = ""
    reason: str = ""


REGISTRY: tuple[Extraction, ...] = (
    Extraction(
        "source-root resolution",
        ("#2760", "#17982"),
        "autobot-backend/api/codebase_analytics/endpoints/shared.py",
        "resolve_source_root",
        GUARDED,
        inlines_source_root,
        reason=(
            "duplicates.py already routes through resolve_scan_root on main; "
            "its file is owned by issue-18067-duplicate-tooling"
        ),
    ),
    Extraction(
        "wav duration",
        ("#13841",),
        "autobot_shared/audio_wav.py",
        "wav_duration_seconds",
        GUARDED,
        inlines_wav_duration,
    ),
    Extraction(
        "egress decision (evaluate + audit log + denial payload)",
        ("#14901", "#14270"),
        "autobot-backend/services/gateway/egress_governor.py",
        "EgressGovernor.gate",
        GUARDED,
        inlines_egress_decision,
        allowed=(
            (
                "autobot-backend/services/gateway/gateway.py",
                "the gateway pipeline owns its own verdict handling, not a send seam",
            ),
        ),
    ),
    Extraction(
        "audio extension allowlist",
        ("#13512", "#13615"),
        "autobot_shared/ssot_constants.py",
        "SecurityConstants.ALLOWED_AUDIO_EXTENSIONS",
        GUARDED_ELSEWHERE,
        guard="repo_tests/audio_extension_allowlist_test.py",
        reason="a dedicated sweep catches exact and near copies; connector file owned by issue-17778-speech-forks",
    ),
    Extraction(
        "comment stripper",
        ("#17941",),
        "tools/lint/_comment_syntax.py",
        "strip_trailing_comment",
        GUARDED_ELSEWHERE,
        guard="repo_tests/one_comment_stripper_17941_test.py",
        reason="shrink-only pending list of private strippers lives in that guard",
    ),
    Extraction(
        "detached ansible spawn",
        ("#17994", "#11492"),
        "autobot-slm-backend/services/playbook_executor.py",
        "detached spawn",
        DEFERRED,
        reason=(
            "deferred: owned by issue-17336-one-redactor "
            "(autobot-slm-backend/api/code_sync.py, 13 undetached spawns)"
        ),
    ),
    Extraction(
        "semantic duplicate detection (the general detector, AC5)",
        ("#17982", "#17995"),
        "autobot-backend/api/codebase_analytics/endpoints/duplicates.py",
        "_run_semantic_analysis",
        WAITING,
        reason=(
            "waiting: #17982 lands on issue-18067-duplicate-tooling, which owns duplicates.py; "
            "until it merges the population of unregistered extractions cannot be measured"
        ),
    ),
)
