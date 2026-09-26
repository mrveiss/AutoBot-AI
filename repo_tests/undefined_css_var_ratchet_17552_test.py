# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A `var()` must name a custom property that exists (#17552).

The owner reported pale text on pale surfaces scattered across the GUI. The
cause was 223 references, in 53 files, to custom properties defined nowhere,
with no fallback. CSS does not treat that as a no-op: the declaration becomes
*invalid at computed-value time*, so ``background`` renders ``transparent``,
``color`` **inherits** from an ancestor instead of taking its intended value,
and a ``border`` shorthand is discarded. A panel loses its surface and its text
keeps whatever colour it inherited -- which on a light page is the reported
symptom.

#17552 cleared the two mechanical groups: the ``--autobot-*`` namespace, which
was defined nowhere at all and in which two components were styled *entirely*,
and six names carrying a ``--color-`` prefix the real token does not have. This
guard stops the population growing back while the remainder is worked down.

**Why the detector is static.** Tailwind v4 contributes theme variables of its
own, so a naive scan over-reports by ~92 names. Rather than shell out to a
build, the detector recognises Tailwind's palette by shape. That was checked
against a real build, not assumed: every name the built stylesheet resolves is
also accepted here, and the build flagged nothing the static rule misses. Where
they disagreed it was three ``--font-weight-*`` built-ins, named below.

**Known gap, stated rather than left to be discovered.** Tailwind tree-shakes
``@theme``: of ~53 ``--color-autobot-*`` aliases declared in
``assets/tailwind.css``, the build emitted 28. This detector reads a declaration
in the repo as sufficient, so a declared-but-tree-shaken token reads as defined
when at runtime it is not. That is why #17552 pointed the fixed components at
the plain theme tokens in ``assets/css/themes/`` -- always present, never
tree-shaken -- rather than at those aliases. Closing the gap needs the built
stylesheet, which this suite has no cheap way to produce.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._undefined_css_var_baseline import TOTAL_SITES, UNDEFINED_CSS_VAR_SITES

_SCANNED_SUFFIXES = {".css", ".scss", ".vue", ".ts", ".js"}
_FRONTEND = Path("autobot-frontend/src")

_DECLARATION = re.compile(r"(--[A-Za-z0-9_-]+)\s*:")
#: The capture group after the name is the comma that introduces a fallback.
_REFERENCE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)\s*(,)?")

#: Tailwind v4's built-in colour ramp: `--color-<hue>-<shade>`.
_TAILWIND_PALETTE = re.compile(r"^--color-[A-Za-z]+-(?:50|100|200|300|400|500|600|700|800|900|950)$")

#: Tailwind built-ins referenced by this tree that are not colour ramp entries.
#: Kept as an explicit set rather than a wider pattern: a wider pattern would
#: also swallow a genuinely misspelt name, and the measured population is three.
#: A new Tailwind built-in used here fails this guard until it is added, which
#: is the safe direction -- it asks a question instead of staying silent.
_TAILWIND_BUILTINS = frozenset({"--font-weight-bold", "--font-weight-medium", "--font-weight-semibold"})


def _scan(root: Path) -> dict[str, int]:
    """``path -> count`` of references naming nothing, with no fallback."""
    declared: set[str] = set()
    references: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if path.suffix not in _SCANNED_SUFFIXES or "node_modules" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        declared |= set(_DECLARATION.findall(text))
        relative = path.relative_to(root).as_posix()
        for name, fallback in _REFERENCE.findall(text):
            if not fallback:
                references.append((name, relative))

    counts: dict[str, int] = {}
    for name, relative in references:
        if name in declared or name in _TAILWIND_BUILTINS or _TAILWIND_PALETTE.match(name):
            continue
        counts[relative] = counts.get(relative, 0) + 1
    return counts


@pytest.fixture(scope="module")
def measured() -> dict[str, int]:
    root = repo_root() / _FRONTEND
    assert root.is_dir(), f"{_FRONTEND} has moved; this guard reads it by path"
    return {f"{_FRONTEND.as_posix()}/{k}": v for k, v in _scan(root).items()}


class TestTheDetectorWorksBeforeItsOutputIsRead:
    """An instrument gets no free pass. Synthetic inputs, so these keep passing
    once the live baseline reaches zero."""

    def _write(self, tmp_path: Path, name: str, body: str) -> Path:
        (tmp_path / name).write_text(body, encoding="utf-8")
        return tmp_path

    def test_it_finds_a_reference_to_nothing(self, tmp_path):
        self._write(tmp_path, "a.css", ".x { color: var(--nowhere-at-all); }")
        assert _scan(tmp_path) == {"a.css": 1}

    def test_a_fallback_is_not_a_finding(self, tmp_path):
        self._write(tmp_path, "a.css", ".x { color: var(--nowhere-at-all, #333); }")
        assert _scan(tmp_path) == {}

    def test_a_declared_name_is_not_a_finding(self, tmp_path):
        self._write(tmp_path, "a.css", ":root { --real: #333; }\n.x { color: var(--real); }")
        assert _scan(tmp_path) == {}

    def test_a_declaration_in_another_file_still_counts(self, tmp_path):
        (tmp_path / "t.css").write_text(":root { --real: #333; }", encoding="utf-8")
        (tmp_path / "u.vue").write_text("<style>.x { color: var(--real); }</style>", encoding="utf-8")
        assert _scan(tmp_path) == {}

    def test_the_tailwind_palette_is_not_a_finding(self, tmp_path):
        self._write(tmp_path, "a.css", ".x { color: var(--color-red-500); background: var(--color-blue-50); }")
        assert _scan(tmp_path) == {}

    def test_a_palette_lookalike_with_a_bad_shade_is_a_finding(self, tmp_path):
        # 550 is not a Tailwind shade; the pattern must not wave it through.
        self._write(tmp_path, "a.css", ".x { color: var(--color-red-550); }")
        assert _scan(tmp_path) == {"a.css": 1}

    def test_it_counts_every_site_not_every_name(self, tmp_path):
        self._write(tmp_path, "a.css", ".x { color: var(--gone); }\n.y { background: var(--gone); }")
        assert _scan(tmp_path) == {"a.css": 2}

    def test_an_unreadable_file_costs_a_finding_not_the_run(self, tmp_path):
        (tmp_path / "bin.css").write_bytes(b"\xff\xfe\x00 not utf-8")
        _scan(tmp_path)  # must not raise


class TestTheBaselineIsInternallyConsistent:
    def test_the_total_matches_the_entries(self):
        assert TOTAL_SITES == sum(UNDEFINED_CSS_VAR_SITES.values())

    def test_no_entry_is_zero(self):
        # A zero would be an entry that should have been deleted.
        assert [f for f, n in UNDEFINED_CSS_VAR_SITES.items() if n <= 0] == []

    def test_every_entry_names_a_file_that_exists(self):
        missing = [f for f in UNDEFINED_CSS_VAR_SITES if not (repo_root() / f).is_file()]
        assert not missing, f"baseline names files that are gone: {missing}"


class TestThePopulationOnlyShrinks:
    def test_no_file_gains_a_reference_to_nothing(self, measured):
        grew = {
            f: (UNDEFINED_CSS_VAR_SITES.get(f, 0), n)
            for f, n in measured.items()
            if n > UNDEFINED_CSS_VAR_SITES.get(f, 0)
        }
        assert not grew, (
            "these files gained a var() naming a property that does not exist "
            f"(pinned, now): {grew}. Point it at a token in autobot-frontend/src/assets/css/themes/ "
            "-- do not add a fallback to get under this check, because a fallback hard-codes a "
            "colour that then ignores the theme."
        )

    def test_no_new_file_joins_the_population(self, measured):
        new = sorted(set(measured) - set(UNDEFINED_CSS_VAR_SITES))
        assert not new, f"new files with undefined var() references: {new}"

    def test_the_total_never_rises(self, measured):
        assert sum(measured.values()) <= TOTAL_SITES

    def test_a_cleared_file_is_removed_from_the_baseline(self, measured):
        stale = sorted(f for f in UNDEFINED_CSS_VAR_SITES if f not in measured)
        assert not stale, (
            f"these files are clean now -- delete their baseline entries and lower " f"TOTAL_SITES: {stale}"
        )


class TestTheTwoGroupsFixedByThisIssueStayFixed:
    """#17552's own work, asserted directly rather than trusted to the count."""

    def test_the_autobot_namespace_is_gone(self, measured):
        root = repo_root() / _FRONTEND
        offenders = [
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.suffix in _SCANNED_SUFFIXES
            and "node_modules" not in p.parts
            and _reads(p)
            and "var(--autobot-" in _reads(p)
        ]
        assert not offenders, (
            "--autobot-* is declared nowhere in the tree; these reference it again: "
            f"{offenders}. The theme tokens are in assets/css/themes/."
        )

    @pytest.mark.parametrize(
        "prefixed,real",
        [
            ("--color-text-primary", "--text-primary"),
            ("--color-text-secondary", "--text-secondary"),
            ("--color-bg-secondary", "--bg-secondary"),
            ("--color-bg-input", "--bg-input"),
            ("--color-bg-hover", "--bg-hover"),
            ("--color-bg-card", "--bg-card"),
        ],
    )
    def test_the_color_prefixed_spelling_does_not_return(self, prefixed, real):
        root = repo_root() / _FRONTEND
        hits = [
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.suffix in _SCANNED_SUFFIXES
            and "node_modules" not in p.parts
            and _reads(p)
            and f"var({prefixed})" in _reads(p)
        ]
        assert not hits, f"{prefixed} is not a token; use {real}. Found in: {hits}"


def _reads(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""
