# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A colour written in JavaScript cannot follow the theme (#17560, #17567).

The detector, its reach declarations and the rationale for every rule it
applies live in :mod:`repo_tests._hardcoded_colour_detect`; this file holds the
assertions. Split when the two together passed the 600-line ceiling (#5060) --
the seam is data and detection on one side, verdicts on the other, which is the
same seam `_hardcoded_colour_baseline.py` already sits on.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._hardcoded_colour_baseline import (
    EXEMPT_BASENAMES,
    HARDCODED_COLOUR_LITERALS,
    IMPORTANT_DECLARATIONS,
    TOTAL_IMPORTANT,
    TOTAL_OCCURRENCES,
)
from repo_tests._hardcoded_colour_detect import (
    _FRONTEND,
    _HEX,
    REACH_COLOUR_FILES,
    REACH_IMPORTANT_FILES,
    REACH_STYLE_BLOCKS,
    _colour_scanned_files,
    _important_scanned_files,
    _is_colour,
    _owned_token_names,
    _scan,
    _scan_important,
    _token_redefinitions,
)
from repo_tests._paths import repo_root


@pytest.fixture(scope="module")
def measured() -> dict[str, int]:
    root = repo_root() / _FRONTEND
    assert root.is_dir(), f"{_FRONTEND} has moved; this guard reads it by path"
    return _scan(root)


@pytest.fixture(scope="module")
def measured_important() -> dict[str, int]:
    return _scan_important(repo_root() / _FRONTEND)


class TestTheDetectorWorksBeforeItsOutputIsRead:
    """Synthetic, so these keep testing something once the baseline drains."""

    def _w(self, tmp_path: Path, name: str, body: str) -> Path:
        (tmp_path / name).write_text(body, encoding="utf-8")
        return tmp_path

    def test_it_finds_a_bare_literal(self, tmp_path):
        self._w(tmp_path, "a.ts", "const c = { color: '#ef4444' }")
        assert _scan(tmp_path) == {"#ef4444": 1}

    def test_a_value_on_the_next_line_is_still_a_colour(self, tmp_path):
        # The property supplies the context and the literal sits below it.
        self._w(tmp_path, "a.ts", "const s = {\n  color:\n    '#ff00aa'\n}\n")
        assert _scan(tmp_path) == {"#ff00aa": 1}

    def test_the_carry_does_not_run_past_one_line(self, tmp_path):
        # `id` is two lines below the colour context and must not inherit it.
        self._w(tmp_path, "a.ts", "const s = {\n  color: 'red',\n  label: 'x',\n  id: '#1234'\n}\n")
        assert _scan(tmp_path) == {}

    def test_a_digit_only_short_literal_in_a_value_is_a_colour(self, tmp_path):
        # #000 and #1234 are valid CSS and carry no a-f letter to identify them.
        self._w(tmp_path, "a.ts", "const a = { color: '#000' }\nconst b = { background: '#1234' }\n")
        assert _scan(tmp_path) == {"#000": 1, "#1234": 1}

    def test_a_digit_only_issue_ref_in_a_comment_is_not_a_colour(self, tmp_path):
        # The real false positive this rule produced: the word "palette" supplies
        # colour context, and `(` looked like a value position.
        self._w(
            tmp_path,
            "a.vue",
            "<template>\n  <!-- Global command palette - opened via Ctrl/Cmd+K (#8989) -->\n</template>\n",
        )
        assert _scan(tmp_path) == {}

    def test_a_digit_only_issue_ref_in_a_line_comment_is_not_a_colour(self, tmp_path):
        self._w(tmp_path, "a.ts", "// background colour work for #8989 and #1234\n")
        assert _scan(tmp_path) == {}

    def test_an_issue_reference_is_not_a_colour(self, tmp_path):
        # The error that turned 395 into 6555.
        self._w(tmp_path, "a.ts", "// background work for #17552 and #9909 — see the color notes")
        assert _scan(tmp_path) == {}

    def test_a_getcssvar_fallback_is_not_a_finding(self, tmp_path):
        # The error that named the exemplar as the worst offender.
        self._w(tmp_path, "a.ts", "const c = getCssVar('--color-error', '#ef4444')")
        assert _scan(tmp_path) == {}

    def test_a_literal_beside_a_resolved_one_is_still_found(self, tmp_path):
        self._w(
            tmp_path,
            "a.ts",
            "const ok = getCssVar('--color-error', '#ef4444')\nconst bad = { borderColor: '#f59e0b' }\n",
        )
        assert _scan(tmp_path) == {"#f59e0b": 1}

    def test_a_hex_with_no_colour_context_is_ignored(self, tmp_path):
        self._w(tmp_path, "a.ts", "const commit = 'abc123' // see a1b2c3d\nconst id = '#ff00aa'\n")
        assert _scan(tmp_path) == {}

    def test_three_and_eight_digit_colours_count(self, tmp_path):
        self._w(tmp_path, "a.ts", "const a = { color: '#fff' }\nconst b = { background: '#ff00aa80' }\n")
        assert _scan(tmp_path) == {"#fff": 1, "#ff00aa80": 1}

    def test_theme_definitions_are_out_of_scope(self, tmp_path):
        (tmp_path / "assets").mkdir()
        (tmp_path / "assets" / "css").mkdir()
        (tmp_path / "assets" / "css" / "x.ts").write_text("const c = { color: '#ef4444' }", encoding="utf-8")
        assert _scan(tmp_path) == {}

    def test_an_unreadable_file_costs_a_finding_not_the_run(self, tmp_path):
        (tmp_path / "b.ts").write_bytes(b"\xff\xfe color: #ef4444")
        _scan(tmp_path)  # must not raise


class TestTheBaselineIsInternallyConsistent:
    def test_the_total_matches_the_entries(self):
        assert TOTAL_OCCURRENCES == sum(HARDCODED_COLOUR_LITERALS.values())

    def test_no_entry_is_zero(self):
        assert [f for f, n in HARDCODED_COLOUR_LITERALS.items() if n <= 0] == []

    def test_every_entry_is_a_colour_literal(self):
        malformed = [k for k in HARDCODED_COLOUR_LITERALS if not _HEX.fullmatch(k) or not _is_colour(k)]
        assert not malformed, f"baseline keys must be colour literals: {malformed}"

    def test_every_entry_is_lowercased(self):
        # Case-folded, so #FFF and #fff are one entry rather than two.
        assert [k for k in HARDCODED_COLOUR_LITERALS if k != k.lower()] == []

    def test_each_exempt_basename_is_unique_in_the_tree(self):
        root = repo_root() / _FRONTEND
        for name in EXEMPT_BASENAMES:
            found = list(root.rglob(name))
            assert len(found) == 1, f"{name} matches {len(found)} files; a basename exemption needs exactly one"


class TestThePopulationOnlyShrinks:
    def test_the_colour_sweep_reaches_the_tree(self):
        read = len(_colour_scanned_files(repo_root()))
        floor = REACH_COLOUR_FILES.floor
        assert read >= floor, (
            f"opened only {read} files, floor {floor} -- an empty result would mean "
            "'nothing was read', not 'nothing was written'"
        )

    def test_every_pinned_colour_matches_its_measured_count(self, measured):
        """Equality, not a ceiling.

        A `<=` bound accepts a reduced non-zero count without the baseline
        moving, and an unpinned reduction is headroom: take `#fff` from 34 to
        20, leave the pin at 34, and fourteen occurrences can return later with
        nothing failing. The pin only pins if it has to be lowered.
        """
        drifted = {
            name: (HARDCODED_COLOUR_LITERALS.get(name, 0), n)
            for name, n in measured.items()
            if n != HARDCODED_COLOUR_LITERALS.get(name, 0)
        }
        assert not drifted, (
            f"pinned count does not match the tree (pinned, now): {drifted}. Growing is the "
            "defect; shrinking is welcome and still requires lowering the entry, because an "
            "unlowered pin is headroom for the occurrence to come back. Resolve colours from "
            "the theme -- getCssVar('--color-error', '#ef4444') -- so they follow [data-theme]."
        )

    def test_no_new_colour_literal_appears(self, measured):
        new = sorted(set(measured) - set(HARDCODED_COLOUR_LITERALS))
        assert not new, f"these colours are written but never resolved from a token: {new}"

    def test_the_total_never_rises(self, measured):
        assert sum(measured.values()) <= TOTAL_OCCURRENCES

    def test_a_tokenised_colour_is_removed_from_the_baseline(self, measured):
        stale = sorted(f for f in HARDCODED_COLOUR_LITERALS if f not in measured)
        assert (
            not stale
        ), f"these colours are fully tokenised now -- delete their entries and lower TOTAL_OCCURRENCES: {stale}"


class TestTheSharedNotificationSourceStaysShared:
    """#17560's own migration, asserted rather than trusted to the count."""

    def test_cache_management_resolves_its_colours(self):
        source = (repo_root() / "autobot-frontend/src/utils/cacheManagement.ts").read_text(encoding="utf-8")
        assert "getNotificationColors" in source, (
            "cacheManagement.ts stopped using the shared notification colours; it previously "
            "held three disagreeing severity maps"
        )

    def test_it_holds_no_severity_palette_of_its_own(self):
        source = (repo_root() / "autobot-frontend/src/utils/cacheManagement.ts").read_text(encoding="utf-8")
        for gone in ("#2196f3", "#ff9800", "#f44336", "#e3f2fd"):
            assert gone not in source, f"a Material-palette literal is back: {gone}"

    def test_the_shared_source_resolves_rather_than_restates(self):
        source = (repo_root() / "autobot-frontend/src/composables/useCssVars.ts").read_text(encoding="utf-8")
        assert "getNotificationColors" in source
        # Every literal in the mapping must be a getCssVar fallback, never a direct return.
        assert "return '#" not in source, "the shared source returns a literal instead of resolving one"


class TestTheImportantDetectorWorks:
    def test_it_finds_one(self, tmp_path):
        (tmp_path / "a.vue").write_text("<style>.x { color: red !important; }</style>", encoding="utf-8")
        assert _scan_important(tmp_path) == {"a.vue": 1}

    def test_spacing_does_not_hide_it(self, tmp_path):
        (tmp_path / "a.vue").write_text("<style>.x { color: red !  important; }</style>", encoding="utf-8")
        assert _scan_important(tmp_path) == {"a.vue": 1}

    def test_outside_a_style_block_is_not_counted(self, tmp_path):
        # A template or script mentioning the word is not a CSS override.
        (tmp_path / "a.vue").write_text("<template><p>this is !important to read</p></template>", encoding="utf-8")
        assert _scan_important(tmp_path) == {}

    def test_a_scoped_or_lang_attribute_still_matches(self, tmp_path):
        (tmp_path / "a.vue").write_text('<style scoped lang="scss">.x { top: 0 !important; }</style>', encoding="utf-8")
        assert _scan_important(tmp_path) == {"a.vue": 1}


class TestTheImportantPopulationOnlyShrinks:
    def test_the_important_sweep_reaches_the_components(self):
        read = len(_important_scanned_files(repo_root()))
        floor = REACH_IMPORTANT_FILES.floor
        assert read >= floor, (
            f"opened only {read} components, floor {floor} -- an empty result would mean "
            "'nothing was read', not 'nothing was found'"
        )

    def test_the_total_matches_the_entries(self):
        assert TOTAL_IMPORTANT == sum(IMPORTANT_DECLARATIONS.values())

    def test_every_pinned_important_matches_its_measured_count(self, measured_important):
        grew = {
            f: (IMPORTANT_DECLARATIONS.get(f, 0), n)
            for f, n in measured_important.items()
            if n != IMPORTANT_DECLARATIONS.get(f, 0)
        }
        assert not grew, (
            f"pinned count does not match the tree (pinned, now): {grew}. Equality, not a "
            "ceiling -- an unlowered pin leaves headroom for a removed !important to return. "
            "Raise specificity or fix the cascade; !important overrides the design system "
            "rather than using it."
        )

    def test_no_new_file_joins_the_population(self, measured_important):
        new = sorted(set(measured_important) - set(IMPORTANT_DECLARATIONS))
        assert not new, f"new files using !important: {new}"

    def test_the_total_never_rises(self, measured_important):
        assert sum(measured_important.values()) <= TOTAL_IMPORTANT

    def test_a_cleared_file_is_removed_from_the_baseline(self, measured_important):
        stale = sorted(f for f in IMPORTANT_DECLARATIONS if f not in measured_important)
        assert not stale, f"clean now -- delete their entries and lower TOTAL_IMPORTANT: {stale}"


class TestFormTwoStaysAbsent:
    """#17567 form 2: redefining a design-system token inside a component.

    Measured at **zero**, and asserted rather than left as a claim in a comment.
    The discriminator is ownership -- whether the name is one the theme declares
    -- not whether a component declares any custom property at all. 34
    component-local aliases exist and are correct: `--rule-accent:
    var(--color-success)` maps a state to a token once so the rest of the
    component reads the alias. A guard on the raw count would flag all 34, and
    the cheapest way to pass it is to inline or hardcode.
    """

    def test_the_detector_rejects_an_owned_token(self, tmp_path):
        (tmp_path / "bad.vue").write_text("<style scoped>.x { --text-primary: #f00; }</style>", encoding="utf-8")
        offenders, blocks = _token_redefinitions(tmp_path, {"--text-primary"})
        assert offenders == {"bad.vue": ["--text-primary"]}
        assert blocks == 1

    def test_a_declaration_after_a_css_comment_is_found(self, tmp_path):
        # `{ /* why */ --text-primary: red; }` separates the name from its `{`,
        # so a position-anchored pattern saw no declaration and the override
        # passed the zero-clash test.
        (tmp_path / "c.vue").write_text(
            "<style>.x { /* explanation */ --text-primary: red; }</style>", encoding="utf-8"
        )
        offenders, _ = _token_redefinitions(tmp_path, {"--text-primary"})
        assert offenders == {"c.vue": ["--text-primary"]}

    def test_the_detector_accepts_a_component_local_alias(self, tmp_path):
        # The real shape, from WorkflowCanvas.vue: a local name assigned FROM a token.
        (tmp_path / "ok.vue").write_text(
            "<style scoped>.s { --rule-accent: var(--color-success); }</style>", encoding="utf-8"
        )
        offenders, blocks = _token_redefinitions(tmp_path, {"--color-success"})
        assert offenders == {}
        assert blocks == 1

    def test_the_detector_ignores_a_bem_modifier_in_a_selector(self, tmp_path):
        (tmp_path / "bem.vue").write_text("<style>.wr-btn--primary:hover { color: red; }</style>", encoding="utf-8")
        offenders, _ = _token_redefinitions(tmp_path, {"--primary"})
        assert offenders == {}

    def test_the_sweep_reaches_the_components(self):
        """A zero is only a finding if the sweep read something (#17567).

        The theme-name floor below checks a DIFFERENT population -- three CSS
        files -- so it stays satisfied even if every component were skipped.
        This floor binds to the sweep's own reach.
        """
        root = repo_root() / _FRONTEND
        _, blocks = _token_redefinitions(root, _owned_token_names(root))
        floor = REACH_STYLE_BLOCKS.floor
        assert blocks >= floor, (
            f"parsed only {blocks} component style blocks, floor {floor} -- "
            "the zero below would mean 'nothing was read', not 'nothing was found'"
        )

    def test_no_component_redefines_a_design_system_token(self):
        root = repo_root() / _FRONTEND
        owned = _owned_token_names(root)
        assert len(owned) > 500, f"only {len(owned)} theme names parsed; the check would be vacuous"
        offenders, _ = _token_redefinitions(root, owned)
        assert not offenders, (
            "these components redefine a design-system token locally, which is the override "
            f"form #17567 records as absent: {offenders}"
        )
