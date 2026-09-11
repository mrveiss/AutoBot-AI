# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every scripted motion primitive consults the reduced-motion preference (#15749).

#14770 wired ``prefers-reduced-motion`` into the frontend's JS-driven motion,
and the completeness check offered was a grep for code that *reads* the
preference, finding none outside the composable. The defect is code that never
reads it -- a hardcoded ``animate: true`` never touched the preference in the
first place -- so that grep passes however many unwired animations exist. It
missed three in a row: a third inline reader, ``useVirtualScroll``'s smooth
default, and ``runClusterLayout``'s ``animate: true``.

This guard inverts the question. It finds the motion **primitives** and requires
each one to consult the preference or carry a reasoned waiver:

=====================  =====================================================
primitive              what it matches
=====================  =====================================================
``animate-option``     an ``animate:`` option (cytoscape and layout options)
``smooth-scroll``      ``behavior: 'smooth'`` / ``scrollBehavior: 'smooth'``
                       (``scrollTo``, ``scrollIntoView``, router scrolling)
``animate-call``       an ``.animate(`` call (``cy.animate()``, Web
                       Animations); a tween's ``duration:`` rides inside that
                       argument list, so it is judged there
``apex-animations``    an ApexCharts ``animations: {...}`` block setting
                       ``enabled: true`` at its top level
=====================  =====================================================

A candidate passes when its line -- or, for a call or a block, its bracketed
span -- reads ``isReducedMotion()``, ``prefersReducedMotion`` or
``preferredScrollBehavior()``; when its value is a literal that animates
nothing; or when it or the line above carries ``reduced-motion-exempt: <why>``.
A waiver with no reason is itself a finding.

What this cannot see, stated so a green run is not read as more than it is:

* **Motion caused by an absent option.** ApexCharts animates unless told
  otherwise, so a raw ``<apexchart>`` that never mentions ``animations`` has no
  primitive to find. ``main.ts`` sets a global ApexCharts default from the
  preference for exactly that reason, and a test below pins that it is there.
* **CSS motion.** ``assets/base.css`` switches motion off document-wide under
  the preference; a shadow root does not inherit it, so the embed widget
  carries its own rule -- also pinned below.

Reach is declared on the **candidates** read, per primitive, at the count this
commit holds -- the population the guard exists for -- through
``repo_tests._reach.declare``, so ``reach_declarations_test`` proves each floor
fires on an empty tree. File counts are asserted
non-zero per root but not pinned: the frontend-unification campaign moves files
between these roots routinely, and a pinned file count would fail every
consolidation PR while saying nothing about motion.

The detector is pure; ``frontend_reduced_motion_guard_contrast_test.py`` feeds
it fixtures that must trip it and fixtures that must not (#15671 shape).
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._reach import declare

__all__: list[str] = []

_REPO_ROOT = repo_root()

#: Every package whose scripts can start motion in a browser.
ROOTS = ("autobot-frontend/src", "libs/autobot-ui/src", "autobot-slm-frontend/src")
_SOURCE_SUFFIXES = (".ts", ".vue", ".js")
#: Tests and stories assert or demonstrate motion values; they start none.
_SKIPPED_SUFFIXES = (".test.ts", ".spec.ts", ".stories.ts", ".d.ts")
_SKIPPED_DIRS = frozenset({"__tests__", "node_modules", "_generated", "generated"})

READER = re.compile(r"isReducedMotion\(|prefersReducedMotion|preferredScrollBehavior\(")
_WAIVER = re.compile(r"reduced-motion-exempt:(?P<reason>.*)")
_COMMENT_LINE = re.compile(r"^\s*(?://|/\*|\*)")

_PRIMITIVES = {
    "animate-option": re.compile(r"(?<![\w$-])animate\s*:"),
    "smooth-scroll": re.compile(r"(?<![\w$-])(?:scrollBehavior|behavior)\s*:"),
    "animate-call": re.compile(r"\.animate\("),
    "apex-animations": re.compile(r"(?<![\w$-])animations\s*:\s*\{"),
}
#: ``animate: false`` animates nothing; ``animate: boolean`` is a type annotation.
_ANIMATE_INERT = re.compile(r"animate\s*:\s*(?:false|boolean)\b")
_SMOOTH_LITERAL = re.compile(r"(?:scrollBehavior|behavior)\s*:\s*['\"`]smooth['\"`]")
_ENABLED_KEY = re.compile(r"enabled\s*:")

#: A candidate fails when its verdict is one of these.
FAILING_VERDICTS = frozenset({"unwired", "waiver has no reason"})

#: Candidates per primitive on this commit, wired or not -- pinned AT the count
#: (see the module docstring). Lower one only in the diff that deliberately
#: removes a motion site; a drop nobody chose means the detector stopped reading.
_MIN_CANDIDATES = {"animate-option": 6, "smooth-scroll": 6, "animate-call": 1, "apex-animations": 5}


@dataclass(frozen=True)
class Hit:
    """One motion-primitive candidate and what the detector decided about it."""

    primitive: str
    line: int
    verdict: str


def _balanced_span(text: str, start: int) -> str:
    """``text`` from the bracket at ``start`` to the bracket that closes it.

    Raises on an unbalanced span: a detector that cannot read a call must fail
    loudly rather than report the call as clean.
    """
    opener = text[start]
    closer = {"(": ")", "{": "}", "[": "]"}[opener]
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opener:
            depth += 1
        elif text[index] == closer:
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise ValueError(f"unbalanced {opener!r} at offset {start}")


def _top_level_entries(span: str) -> list[str]:
    """The comma-separated entries of a bracketed span, nested brackets kept whole.

    Kept whole because a reader is a call: stripping nested brackets would turn
    ``enabled: !isReducedMotion()`` into ``enabled: !isReducedMotion`` and hide it.
    """
    depth, entries, current = 0, [], []
    for char in span:
        if char in "({[":
            depth += 1
            if depth == 1:
                continue
        elif char in ")}]":
            depth -= 1
            if depth == 0:
                break
        elif char == "," and depth == 1:
            entries.append("".join(current))
            current = []
            continue
        current.append(char)
    entries.append("".join(current))
    return [entry.strip() for entry in entries if entry.strip()]


def _apex_verdict(span: str) -> str:
    """Judge an ApexCharts ``animations`` block by its own top-level ``enabled``.

    A nested ``animateGradually.enabled`` only matters once that flag is on, and an
    absent flag leaves the decision to the global default ``main.ts`` sets.
    """
    flags = [entry.split(":", 1)[1] for entry in _top_level_entries(span) if _ENABLED_KEY.match(entry)]
    if not flags:
        return "inert"
    if READER.search(flags[0]):
        return "consults"
    return "unwired" if flags[0].strip() == "true" else "inert"


def _verdict(primitive: str, text: str, match: re.Match[str], line: str) -> str:
    """``consults`` / ``inert`` / ``unwired`` for one candidate, before any waiver."""
    if primitive == "apex-animations":
        return _apex_verdict(_balanced_span(text, match.end() - 1))
    if primitive == "animate-call":
        return "consults" if READER.search(_balanced_span(text, match.end() - 1)) else "unwired"
    if READER.search(line):
        return "consults"
    if primitive == "animate-option":
        return "inert" if _ANIMATE_INERT.search(line) else "unwired"
    return "unwired" if _SMOOTH_LITERAL.search(line) else "inert"


def _with_waiver(verdict: str, lines: list[str], index: int) -> str:
    """Apply a ``reduced-motion-exempt:`` waiver on the line or the one above."""
    if verdict != "unwired":
        return verdict
    for candidate in (lines[index], lines[index - 1] if index else ""):
        waiver = _WAIVER.search(candidate)
        if waiver:
            reason = waiver.group("reason").strip(" \t*/->")
            return "waived" if reason else "waiver has no reason"
    return verdict


def detect(text: str) -> list[Hit]:
    """Every motion-primitive candidate in one source text, with its verdict."""
    lines = text.splitlines()
    hits: list[Hit] = []
    for primitive, pattern in _PRIMITIVES.items():
        for match in pattern.finditer(text):
            index = text.count("\n", 0, match.start())
            if _COMMENT_LINE.match(lines[index]):
                continue
            verdict = _verdict(primitive, text, match, lines[index])
            hits.append(Hit(primitive, index + 1, _with_waiver(verdict, lines, index)))
    return sorted(hits, key=lambda hit: (hit.line, hit.primitive))


def findings(text: str) -> list[Hit]:
    """The candidates that fail: unwired, or waived without a reason."""
    return [hit for hit in detect(text) if hit.verdict in FAILING_VERDICTS]


def _sources(root: Path) -> list[Path]:
    """Script sources under one root; a missing root raises rather than reading as empty."""
    if not root.is_dir():
        raise FileNotFoundError(f"{root} does not exist -- repoint ROOTS instead of letting the sweep shrink")
    return sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in _SOURCE_SUFFIXES
        and not path.name.endswith(_SKIPPED_SUFFIXES)
        and not _SKIPPED_DIRS.intersection(path.relative_to(root).parts)
    )


def _present_sources(repo: Path) -> list[Path]:
    """Script sources under every root that exists in *repo*.

    The declared discovery, so an empty tree yields ``[]`` instead of raising:
    ``reach_declarations_test`` hands every declaration an empty repository and
    needs an empty *result*, and the floor then raises ``ReachFloorError``. The
    live sweep keeps the raising ``_sources``.
    """
    return [path for root in ROOTS if (repo / root).is_dir() for path in _sources(repo / root)]


@functools.cache
def _candidates_in(repo: Path) -> tuple[tuple[str, Hit], ...]:
    """Every motion candidate under *repo*, wired or not, as (repo-relative path, hit)."""
    return tuple(
        (path.relative_to(repo).as_posix(), hit)
        for path in _present_sources(repo)
        for hit in detect(path.read_text(encoding="utf-8"))
    )


def _discover(primitive: str) -> Callable[[Path], list[tuple[str, int]]]:
    """Discovery for one primitive's candidates -- what its floor is bound to."""

    def discover(repo: Path) -> list[tuple[str, int]]:
        return [(path, hit.line) for path, hit in _candidates_in(repo) if hit.primitive == primitive]

    return discover


#: One declaration per primitive, so a collapse in one cannot hide behind the
#: others' counts. ``growth=0``: ordinary work does not add motion sites, so each
#: floor sits at the live count and a new site is a deliberate edit to this map.
REACHES = tuple(
    declare(
        f"reduced-motion-{primitive}",
        discover=_discover(primitive),
        floor=floor,
        what=f"{primitive} motion candidates",
    )
    for primitive, floor in _MIN_CANDIDATES.items()
)


@functools.cache
def _sweep() -> tuple[dict[str, int], dict[str, tuple[Hit, ...]]]:
    """Files read per root, and every candidate per repo-relative file."""
    reached: dict[str, int] = {}
    candidates: dict[str, tuple[Hit, ...]] = {}
    for root in ROOTS:
        sources = _sources(_REPO_ROOT / root)
        reached[root] = len(sources)
        for path in sources:
            hits = detect(path.read_text(encoding="utf-8"))
            if hits:
                candidates[path.relative_to(_REPO_ROOT).as_posix()] = tuple(hits)
    return reached, candidates


def test_the_sweep_reads_every_root_and_every_known_motion_site() -> None:
    """State the reach before trusting a clean result -- see the module docstring."""
    reached, _ = _sweep()
    empty = [root for root, count in reached.items() if count == 0]
    assert not empty, f"these roots yielded no script sources -- the sweep has stopped reading them: {empty}"
    for reach in REACHES:
        reach.examined(_REPO_ROOT)


def test_every_motion_primitive_consults_the_preference_or_carries_a_reasoned_waiver() -> None:
    """An animation that never asks the user is a finding (#15749)."""
    _, candidates = _sweep()
    failing = [
        f"{path}:{hit.line}  {hit.primitive}  ({hit.verdict})"
        for path, hits in sorted(candidates.items())
        for hit in hits
        if hit.verdict in FAILING_VERDICTS
    ]
    assert not failing, (
        "These motion primitives ignore prefers-reduced-motion (#15749). Make each consult "
        "isReducedMotion() / useReducedMotion() / preferredScrollBehavior() from "
        "@/composables/useReducedMotion, or add `reduced-motion-exempt: <why>` on the line "
        "or the line above:\n  " + "\n  ".join(failing)
    )


def test_the_apexcharts_global_default_consults_the_preference() -> None:
    """Covers what no primitive can: a chart that never mentions ``animations``."""
    main = (_REPO_ROOT / "autobot-frontend" / "src" / "main.ts").read_text(encoding="utf-8")
    assert re.search(r"\.Apex\s*=", main), "main.ts no longer sets the global ApexCharts default (#15749)"
    blocks = [hit for hit in detect(main) if hit.primitive == "apex-animations"]
    assert [hit.verdict for hit in blocks] == [
        "consults"
    ], f"main.ts's ApexCharts default must read the preference: {blocks}"


def test_the_embed_widget_carries_its_own_reduced_motion_rule() -> None:
    """A shadow root does not inherit ``base.css``'s document-wide rule."""
    styles = (_REPO_ROOT / "autobot-frontend" / "src" / "embed" / "embed-styles.ts").read_text(encoding="utf-8")
    assert "@media (prefers-reduced-motion: reduce)" in styles, "the embed widget lost its reduced-motion rule (#15749)"
