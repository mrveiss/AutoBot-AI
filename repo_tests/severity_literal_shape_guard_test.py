# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14988 — the severity forks and literal shapes the #13597 ratchet misses.

``repo_tests/enum_union_guard_test.py`` ratchets exactly one shape, the dict
entry::

    _SEVERITY_LITERAL = re.compile(r'''["']severity["']\\s*:\\s*["'][A-Za-z_]+["']''')

That matcher requires a **quoted key followed by a colon**, so every literal
written as a keyword argument, an attribute assignment or a comparison is
invisible to it. Measured on this tree, those two shapes carry 194 more
literals across 53 files than the guarded shape's 25 across 6.

This file ratchets the other two shapes so the unguarded population can only
fall, and pins the finding that stops the lazy fix: the values outside the
canonical vocabulary are **not missing rungs**. Every one of them is a
different enum's vocabulary sitting in a field named ``severity``:

* ``forbidden`` — ``autobot-backend/security/command_patterns.py:78`` grades a
  dangerous-command pattern; that ladder is ``CommandRisk``, which already has
  ``FORBIDDEN``. Wrong enum, not a missing rung.
* ``none`` / ``moderate`` — ``autobot_shared/delta_engine.py:120`` classifies a
  metric delta as ``none`` / ``moderate`` / ``critical``. ``none`` is the
  *absence* of a finding, which no severity ladder can express.
* ``missing`` — ``autobot_shared/env_drift_detector.py:55`` records a drift
  *kind* (``missing`` / ``type_mismatch`` / ``unknown``), not how bad it is.

So the fix for those four is a correctly typed field, filed per-value on
#14988 — never widening ``Severity``. ``test_the_canonical_vocabulary_does_not
_absorb_another_enums_words`` fails if anyone takes the shortcut.

Traps this file is built against, both seen in this repo:

* *A sweep matching zero files still passes.* Every count assertion is preceded
  by a floor on the population it counted over, and the file enumeration has
  its own floor.
* *A guard counting a token the producer never emits.* Each matcher is asserted
  against a real tracked file as well as against synthetic strings, so a
  matcher that has stopped matching the tree fails rather than reading clean.

This module lives in ``repo_tests/``, which is outside the two scanned roots,
so the example strings below cannot inflate the counts they are checking —
``test_this_guard_is_outside_the_scanned_roots`` pins that.
"""

from __future__ import annotations

import ast
import collections
import functools
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env
from autobot_shared.status_enums import Severity

REPO_ROOT = Path(__file__).resolve().parents[1]

# The same two roots the dict-entry ratchet scans, so the three populations are
# comparable and a literal cannot escape by moving between guards.
SCANNED_ROOTS = ("autobot-backend/", "autobot_shared/")

# Matchers quoted verbatim from #14988 so the numbers here are the numbers the
# issue reports. `severity\s*=` also matches a suffixed name such as
# `min_severity="high"`; that is deliberate — it is the same bare literal.
_SEVERITY_KWARG = re.compile(r"""severity\s*=\s*["'][A-Za-z_]+["']""")
_SEVERITY_COMPARISON = re.compile(r"""severity["']?\]?\s*==\s*["'][A-Za-z_]+["']""")

# Trailing quoted word of a match — the literal value itself.
_MATCHED_VALUE = re.compile(r"""["']([A-Za-z_]+)["']\s*$""")

# Measured on Dev_new_gui at 2363ad3aa9. Ceilings may only fall.
KWARG_LITERAL_CEILING = 73
COMPARISON_LITERAL_CEILING = 121
LITERAL_FILE_CEILING = 53

# Floors sit just under each ceiling for the same reason the dict-entry ratchet
# floors its own count: zero must FAIL rather than read as a spotless tree. A
# conversion run that drops more than five at once is a deliberate edit here.
KWARG_LITERAL_FLOOR = 68
COMPARISON_LITERAL_FLOOR = 116
LITERAL_FILE_FLOOR = 48

# Literals whose value is not a canonical Severity value. 20 today; see the
# module docstring for why each is a mis-typed field rather than a missing rung.
OUT_OF_VOCABULARY_CEILING = 20
OUT_OF_VOCABULARY_FLOOR = 15

# Pinned by name as well as by count: a NEW word outside the vocabulary fails
# here even while the total stays under the ceiling.
KNOWN_OUT_OF_VOCABULARY = frozenset({"none", "moderate", "missing", "forbidden"})

# Floor for the file enumeration itself. An empty walk agrees with everything.
_TRACKED_PY_FLOOR = 3000

# A file that certainly carries each shape, so a matcher that has silently
# stopped matching the tree fails by name instead of reporting a clean sweep.
_KWARG_WITNESS = "autobot_shared/delta_engine.py"
_COMPARISON_WITNESS = "autobot_shared/delta_engine.py"


@functools.lru_cache(maxsize=1)
def _tracked_python_files() -> tuple[str, ...]:
    """Tracked ``*.py`` paths, relative to the repo root, worktrees excluded.

    The environment is scrubbed because an inherited ``GIT_DIR`` makes
    ``ls-files`` answer for a different checkout entirely (#15490).
    """
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    )
    return tuple(line for line in out.stdout.splitlines() if line and not line.startswith(".worktrees/"))


@functools.lru_cache(maxsize=1)
def _scanned_files() -> tuple[str, ...]:
    """The tracked files under the two roots the ratchets count over."""
    return tuple(rel for rel in _tracked_python_files() if rel.startswith(SCANNED_ROOTS))


def _read(rel: str) -> str:
    try:
        return (REPO_ROOT / rel).read_text(encoding="utf-8")
    except OSError:
        return ""


def _hits(matcher: re.Pattern[str]) -> list[tuple[str, str]]:
    """(file, matched text) for every hit of *matcher* under the scanned roots."""
    return [(rel, match.group(0)) for rel in _scanned_files() for match in matcher.finditer(_read(rel))]


@functools.lru_cache(maxsize=1)
def _unguarded_hits() -> tuple[tuple[str, str], ...]:
    """Both unguarded shapes together, deduplicated by file and span."""
    seen: dict[str, set[tuple[int, int]]] = collections.defaultdict(set)
    out: list[tuple[str, str]] = []
    for rel in _scanned_files():
        text = _read(rel)
        for matcher in (_SEVERITY_KWARG, _SEVERITY_COMPARISON):
            for match in matcher.finditer(text):
                if match.span() not in seen[rel]:
                    seen[rel].add(match.span())
                    out.append((rel, match.group(0)))
    return tuple(out)


def _matched_value(text: str) -> str | None:
    found = _MATCHED_VALUE.search(text)
    return found.group(1) if found else None


def _out_of_vocabulary() -> collections.Counter:
    """Counts of matched literals whose value no ``Severity`` member carries."""
    vocabulary = {member.value for member in Severity}
    values = (_matched_value(text) for _, text in _unguarded_hits())
    return collections.Counter(v for v in values if v is not None and v not in vocabulary)


# --------------------------------------------------------------------------
# Population floors — evaluated before every substantive assertion below
# --------------------------------------------------------------------------


def test_the_enumeration_reaches_the_repo():
    """An empty file list would agree with every count assertion in this file."""
    assert len(_tracked_python_files()) >= _TRACKED_PY_FLOOR, (
        f"git ls-files returned {len(_tracked_python_files())} python files, "
        f"under the floor of {_TRACKED_PY_FLOOR} — the enumeration is broken, "
        "not the tree"
    )


def test_the_scanned_roots_still_hold_files():
    """The roots are named as string prefixes; a rename would silently empty them."""
    assert len(_scanned_files()) >= 1000, (
        f"only {len(_scanned_files())} tracked files under {SCANNED_ROOTS} — "
        "the roots moved and every ratchet below is counting nothing"
    )


def test_this_guard_is_outside_the_scanned_roots():
    """The example strings in this module must not inflate the counts it pins."""
    rel = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
    assert not rel.startswith(SCANNED_ROOTS), (
        f"{rel} moved under a scanned root — its own examples are now part of " "the population it ratchets"
    )


# --------------------------------------------------------------------------
# Matcher self-checks — the literal matched is the literal the tree emits
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("shape", "matches"),
    [
        ("severity=" + '"high"', True),
        ("severity = " + "'critical'", True),
        ("min_severity=" + '"low"', True),
        ("severity=" + "Severity.HIGH", False),
        ("severity=" + "level", False),
    ],
)
def test_the_kwarg_matcher_matches_the_shape_it_claims(shape, matches):
    assert bool(_SEVERITY_KWARG.search(shape)) is matches, shape


@pytest.mark.parametrize(
    ("shape", "matches"),
    [
        ("severity == " + '"high"', True),
        ('item["severity"] == ' + "'critical'", True),
        ("severity == " + "Severity.HIGH.value", False),
        ("severity == " + "other", False),
    ],
)
def test_the_comparison_matcher_matches_the_shape_it_claims(shape, matches):
    assert bool(_SEVERITY_COMPARISON.search(shape)) is matches, shape


def test_each_matcher_still_matches_a_real_tracked_file():
    """Synthetic strings prove the regex; only the tree proves the sweep.

    A matcher tuned against examples alone can drift away from what the
    producers actually write and report a clean tree forever.
    """
    assert _SEVERITY_KWARG.search(_read(_KWARG_WITNESS)), (
        f"#14988: no keyword-shaped severity literal left in {_KWARG_WITNESS} — "
        "if it was genuinely converted, repoint the witness; do not delete it"
    )
    assert _SEVERITY_COMPARISON.search(_read(_COMPARISON_WITNESS)), (
        f"#14988: no comparison-shaped severity literal left in "
        f"{_COMPARISON_WITNESS} — repoint the witness rather than dropping it"
    )


def test_the_two_shapes_do_not_double_count():
    """The union is the sum, so each ceiling can be reasoned about alone."""
    separate = len(_hits(_SEVERITY_KWARG)) + len(_hits(_SEVERITY_COMPARISON))
    assert len(_unguarded_hits()) == separate, (
        f"the two shapes now overlap ({separate} separate vs "
        f"{len(_unguarded_hits())} deduplicated) — the ceilings below "
        "double-count and must be re-measured together"
    )


# --------------------------------------------------------------------------
# The ratchets — down only
# --------------------------------------------------------------------------


def test_keyword_shaped_severity_literals_do_not_grow():
    hits = _hits(_SEVERITY_KWARG)
    assert len(hits) >= KWARG_LITERAL_FLOOR, (
        f"#14988: only {len(hits)} keyword-shaped severity literals found "
        f"(floor {KWARG_LITERAL_FLOOR}). A sweep that suddenly finds far fewer "
        "is a broken matcher until proven otherwise; if they were genuinely "
        "converted, lower both bounds in the same commit."
    )
    assert len(hits) <= KWARG_LITERAL_CEILING, (
        f"#14988: {len(hits)} keyword-shaped severity literals, over the "
        f"ceiling of {KWARG_LITERAL_CEILING}. Use "
        "autobot_shared.status_enums.Severity instead of a bare string."
    )


def test_comparison_shaped_severity_literals_do_not_grow():
    hits = _hits(_SEVERITY_COMPARISON)
    assert len(hits) >= COMPARISON_LITERAL_FLOOR, (
        f"#14988: only {len(hits)} comparison-shaped severity literals found "
        f"(floor {COMPARISON_LITERAL_FLOOR}). Lower both bounds together when "
        "they are genuinely converted."
    )
    assert len(hits) <= COMPARISON_LITERAL_CEILING, (
        f"#14988: {len(hits)} comparison-shaped severity literals, over the "
        f"ceiling of {COMPARISON_LITERAL_CEILING}. Compare against a "
        "Severity member, not a string."
    )


def test_the_spread_of_files_carrying_a_literal_does_not_grow():
    """A per-file allowlist would be 53 entries of noise; the count is the ratchet."""
    files = {rel for rel, _ in _unguarded_hits()}
    assert len(files) >= LITERAL_FILE_FLOOR, (
        f"#14988: only {len(files)} files carry an unguarded severity literal "
        f"(floor {LITERAL_FILE_FLOOR}) — the sweep stopped reaching the tree."
    )
    assert len(files) <= LITERAL_FILE_CEILING, (
        f"#14988: {len(files)} files now carry an unguarded severity literal, "
        f"over the ceiling of {LITERAL_FILE_CEILING}. The defect spread to a "
        "new module."
    )


# --------------------------------------------------------------------------
# The values outside the vocabulary — and the shortcut that must stay shut
# --------------------------------------------------------------------------


def test_out_of_vocabulary_severity_literals_do_not_grow():
    counts = _out_of_vocabulary()
    total = sum(counts.values())
    assert total >= OUT_OF_VOCABULARY_FLOOR, (
        f"#14988: only {total} out-of-vocabulary severity literals "
        f"(floor {OUT_OF_VOCABULARY_FLOOR}). Either they were converted — lower "
        "both bounds — or Severity absorbed a word it should not have; see "
        "test_the_canonical_vocabulary_does_not_absorb_another_enums_words."
    )
    assert total <= OUT_OF_VOCABULARY_CEILING, (
        f"#14988: {total} severity literals carry a value no Severity member "
        f"has, over the ceiling of {OUT_OF_VOCABULARY_CEILING}: "
        f"{dict(counts.most_common())}"
    )


def test_no_new_word_appears_outside_the_vocabulary():
    """Pinned by name, so a new bad word fails even under the total ceiling."""
    found = set(_out_of_vocabulary())
    assert found, "#14988: the out-of-vocabulary scan found nothing — it is broken"
    assert found <= KNOWN_OUT_OF_VOCABULARY, (
        f"#14988: new severity values outside the canonical vocabulary: "
        f"{sorted(found - KNOWN_OUT_OF_VOCABULARY)}. Decide each one — synonym, "
        "new rung, or (as with all four already known) a different enum's "
        "vocabulary in a field named severity."
    )


def test_the_canonical_vocabulary_does_not_absorb_another_enums_words():
    """The lazy fix for the count above is widening Severity. It is wrong.

    Each of these four is a different vocabulary — a command-risk ladder, a
    delta classification whose ``none`` means *no finding*, and a drift kind.
    Adding them to ``Severity`` would make the ratchet read clean while making
    the canonical enum less meaningful, which is the opposite of #13597.
    """
    vocabulary = {member.value for member in Severity}
    absorbed = vocabulary & KNOWN_OUT_OF_VOCABULARY
    assert not absorbed, (
        f"#14988: Severity gained {sorted(absorbed)} — those are "
        "CommandRisk / delta-classification / drift-kind vocabularies, not "
        "severity rungs. Type the field correctly instead."
    )


def test_the_scanned_population_still_dwarfs_the_guarded_shape():
    """The premise of this file: the unguarded shapes are the larger population.

    If this ever inverts, the dict-entry ratchet has grown or these shapes have
    drained, and the two guards should be reconciled rather than left apart.
    """
    dict_shape = re.compile(r"""["']severity["']\s*:\s*["'][A-Za-z_]+["']""")
    assert len(_unguarded_hits()) > len(_hits(dict_shape)), (
        "#14988: the unguarded shapes no longer outnumber the guarded one — "
        "fold this ratchet into repo_tests/enum_union_guard_test.py"
    )


# --------------------------------------------------------------------------
# #14988 item 1/2 — the fourth fork is already collapsed; keep it collapsed
# --------------------------------------------------------------------------

# #14988 reports `CausalSeverity` as a fourth severity fork declaring its own
# `(str, Enum)`. Measured on this tree it is already an alias of the canonical
# `Severity` — but nothing asserted that, so a re-declaration would have been
# invisible. These two tests pin the collapse and the reason it was safe.
_CAUSAL_ENGINE = "autobot-backend/services/causal_inference_engine.py"
_DIAGNOSTICS = "autobot-backend/api/diagnostics.py"


def _module_ast(rel: str) -> ast.Module:
    path = REPO_ROOT / rel
    assert path.exists(), f"#14988: {rel} is gone — the guard has no target"
    return ast.parse(path.read_text(encoding="utf-8"))


def test_causal_severity_is_still_an_alias_of_the_canonical_enum():
    """Read by AST: importing the engine pulls the whole backend app in."""
    tree = _module_ast(_CAUSAL_ENGINE)
    redeclared = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "CausalSeverity"]
    assert not redeclared, f"#14988: CausalSeverity was re-declared as its own enum in {_CAUSAL_ENGINE}"
    aliased = [
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for name in node.names
        if name.asname == "CausalSeverity" and name.name == "Severity"
    ]
    assert aliased == ["autobot_shared.status_enums"], (
        f"#14988: CausalSeverity in {_CAUSAL_ENGINE} is bound to " f"{aliased or 'nothing'}, not the canonical Severity"
    )


def test_the_canonical_severity_carries_every_causal_rung():
    """The alias is only safe while Severity is a superset of the old fork."""
    for name in ("CRITICAL", "DEGRADED", "WARNING"):
        assert hasattr(Severity, name), f"#14988: Severity lost {name}, which CausalSeverity needs"


def test_the_causal_report_still_crosses_the_wire_as_a_value():
    """Why dropping the `(str, Enum)` base was safe — and must stay safe.

    The fork was a str subclass; the canonical enum is not. That is only inert
    while the serialisation goes through an explicit `.value` read, so both
    halves of that path are pinned: the report emits `.value`, and the endpoint
    returns `to_dict()` rather than the dataclass.
    """
    engine = (REPO_ROOT / _CAUSAL_ENGINE).read_text(encoding="utf-8")
    assert '"severity": self.severity.value' in engine, (
        f"#14988: {_CAUSAL_ENGINE} no longer serialises severity via .value — "
        "a plain Enum does not stringify itself, so the wire value changed"
    )
    endpoint = (REPO_ROOT / _DIAGNOSTICS).read_text(encoding="utf-8")
    assert ".to_dict()" in endpoint, (
        f"#14988: {_DIAGNOSTICS} no longer serialises the causal report via "
        "to_dict() — the alias's safety argument rested on that path"
    )
