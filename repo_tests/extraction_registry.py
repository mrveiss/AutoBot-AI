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

DEFAULT_ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")
TOOLING_ROOTS = ("tools/lint", "pipeline-scripts", "scripts")

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


def _is_path_of_clone_path(v: ast.AST | None) -> bool:
    """``Path(<x>.clone_path)``."""
    return (
        isinstance(v, ast.Call)
        and getattr(v.func, "id", None) == "Path"
        and any(isinstance(a, ast.Attribute) and a.attr == "clone_path" for a in v.args)
    )


def _names_bound_once_to_clone_path(fn: ast.AST) -> set[str]:
    """Names whose ONLY assignment in *fn* is ``Path(<x>.clone_path)`` (a single-assignment flow)."""
    count: dict[str, int] = {}
    hits: set[str] = set()
    for n in ast.walk(fn):
        if isinstance(n, (ast.Assign, ast.AnnAssign)):
            targets = n.targets if isinstance(n, ast.Assign) else [n.target]
            for t in (t for t in targets if isinstance(t, ast.Name)):
                count[t.id] = count.get(t.id, 0) + 1
                if _is_path_of_clone_path(n.value):
                    hits.add(t.id)
        elif isinstance(n, (ast.AugAssign, ast.NamedExpr)) and isinstance(n.target, ast.Name):
            count[n.target.id] = count.get(n.target.id, 0) + 2
    return {name for name in hits if count[name] == 1}


def inlines_source_root(tree: ast.AST) -> bool:
    """A function that looks a source up and RETURNS ``Path(<x>.clone_path)`` (#2760, #17982).

    Keyed on the return, not on reading ``clone_path``: the indexing paths legitimately
    read it, and only a function that hands back the path is a second resolver. Follows
    one hop: ``root = Path(x.clone_path); return root`` (the name assigned exactly once in
    the same function). Limit, by design: reassignment, tuple unpacking, attribute targets
    and flows across functions are not followed, because chasing them needs real dataflow
    and a wrong guess would flag the legitimate indexing paths.
    """
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or "get_source" not in _calls(fn):
            continue
        via_name = _names_bound_once_to_clone_path(fn)
        for ret in (n for n in ast.walk(fn) if isinstance(n, ast.Return)):
            v = ret.value
            if _is_path_of_clone_path(v) or (isinstance(v, ast.Name) and v.id in via_name):
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


_GOVERNOR = "egress_governor"
_DENIAL = "egress_denied"


def _governor_names(tree: ast.AST) -> set[str]:
    """``egress_governor`` plus every alias it is imported under (``... import egress_governor as eg``)."""
    names = {_GOVERNOR}
    for n in ast.walk(tree):
        if isinstance(n, (ast.Import, ast.ImportFrom)):
            names.update(a.asname for a in n.names if a.asname and a.name.rsplit(".", 1)[-1] == _GOVERNOR)
    return names


def _is_governor_receiver(v: ast.AST, names: set[str]) -> bool:
    """A bare governor name, or an attribute holding one (``self._egress_governor``, ``self.governor``)."""
    if isinstance(v, ast.Name):
        return v.id in names
    return isinstance(v, ast.Attribute) and (v.attr in names or ("egress" in v.attr and "governor" in v.attr))


def _denial_constants_outside_comparisons(tree: ast.AST) -> bool:
    """An ``"egress_denied"`` literal that is not an operand of a comparison.

    ``x["error"] == "egress_denied"`` or ``code in ("egress_denied", ...)`` CONSUMES the
    payload; a dict value, keyword, return or assignment BUILDS it. Only builders are copies.
    """
    consumed = {id(c) for cmp in ast.walk(tree) if isinstance(cmp, ast.Compare) for c in ast.walk(cmp)}
    return any(isinstance(n, ast.Constant) and n.value == _DENIAL and id(n) not in consumed for n in ast.walk(tree))


def inlines_egress_decision(tree: ast.AST) -> bool:
    """A governor ``.evaluate(...)`` call or a built ``egress_denied`` payload (#14901).

    Follows ``from ... import egress_governor as eg`` and ``self.<...governor>.evaluate``.
    Limits, by design: a governor reached through an arbitrary local (``g = get_gov();
    g.evaluate()``) is not followed, and a literal compared via a variable
    (``tag = "egress_denied"; if x == tag``) reads as a producer; both would need real
    dataflow and are rare enough that a false flag is cheaper than a silent miss.
    """
    names = _governor_names(tree)
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "evaluate":
            if _is_governor_receiver(n.func.value, names):
                return True
    return _denial_constants_outside_comparisons(tree)


_POST_COMMIT_KEY = "_post_commit_cbs"
_POST_COMMIT_CONSTANT = "POST_COMMIT_CALLBACKS"


def _is_post_commit_key(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return node.value == _POST_COMMIT_KEY
    return isinstance(node, ast.Name) and node.id == _POST_COMMIT_CONSTANT


def seeds_post_commit_list(tree: ast.AST) -> bool:
    """Assigns to ``<x>.info[<post-commit key>]``: only a transaction scope does (#15068).

    A reader that appends a callback does not seed the list and is not a copy.
    """
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for tgt in targets:
            if isinstance(tgt, ast.Subscript) and isinstance(tgt.value, ast.Attribute) and tgt.value.attr == "info":
                if _is_post_commit_key(tgt.slice):
                    return True
    return False


def _delegates_to(fn: ast.AST, name: str) -> bool:
    """A thin ``return name(...)`` wrapper has one implementation behind it: not a fork."""
    body = [st for st in fn.body if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant))]
    if len(body) != 1 or not isinstance(body[0], ast.Return) or not isinstance(body[0].value, ast.Call):
        return False
    callee = body[0].value.func
    return (callee.attr if isinstance(callee, ast.Attribute) else getattr(callee, "id", None)) == name


def defines_top_level(name: str) -> Detector:
    """Detector: a module-level ``def name`` / ``def _name`` that is not a delegating wrapper.

    Keyed on NAME, not body (a body comparison was vacuous: private copies took the logger
    from a global where the canonical one takes a parameter). Nested functions are local
    scope and ignored; the leading underscore is stripped because the thirteenth copy of
    ``configure_logging`` was ``_configure_logging``.
    """

    def detect(tree: ast.AST) -> bool:
        return any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.lstrip("_") == name
            and not _delegates_to(n, name)
            for n in getattr(tree, "body", [])
        )

    return detect


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
    #: Path prefixes swept for this concept; the default is the three packages.
    roots: tuple[str, ...] = DEFAULT_ROOTS
    #: Sweep test modules too. The lint-helper entries need it: a test file under ``tools/lint``
    #: that re-declares a helper is as much a fork as a checker that does.
    include_tests: bool = False


REGISTRY: tuple[Extraction, ...] = (
    Extraction(
        "post-commit transaction scope",
        ("#15068",),
        "autobot_shared/db_session.py",
        "async_session_scope",
        GUARDED,
        seeds_post_commit_list,
        reason="folded in from one_session_scope_15068_test; the per-provider check stays in the registry test",
    ),
    Extraction(
        "lint helper configure_logging",
        ("#13916",),
        "tools/lint/_scan_helpers.py",
        "configure_logging",
        GUARDED,
        defines_top_level("configure_logging"),
        roots=TOOLING_ROOTS,
        include_tests=True,
        reason="folded in from no_private_copy_of_a_shared_helper_test; canonical owned by issue-14896-lint-harness",
    ),
    Extraction(
        "lint helper tracked_paths",
        ("#13916",),
        "tools/lint/_scan_helpers.py",
        "tracked_paths",
        GUARDED,
        defines_top_level("tracked_paths"),
        roots=TOOLING_ROOTS,
        include_tests=True,
        reason="folded in from no_private_copy_of_a_shared_helper_test; canonical owned by issue-14896-lint-harness",
    ),
    Extraction(
        "lint helper logical_lines",
        ("#13916",),
        "tools/lint/_scan_helpers.py",
        "logical_lines",
        GUARDED,
        defines_top_level("logical_lines"),
        roots=TOOLING_ROOTS,
        include_tests=True,
        reason="folded in from no_private_copy_of_a_shared_helper_test; canonical owned by issue-14896-lint-harness",
    ),
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
