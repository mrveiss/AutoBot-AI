# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
r"""No new hard-coded English UI text in a `.vue` file (#12732).

The boundary, the kinds of literal and the shrink rule are in
`repo_tests/_hardcoded_ui_literal_baseline.py`; the detector is
`repo_tests/_ui_literal_scan.py` (shared with the SLM guard #15665) and the
enumeration `repo_tests/_hardcoded_ui_literal_detect.py`.

**Second derivation (template-text and attribute).** The detector walks the
filesystem and reads the template with `html.parser`. `_ui_literal_rederive.py`
enumerates with `git ls-files` and matches with regexes; the two are compared as
SETS of (file, kind, literal). They are not equal and are not expected to be:
the regexes are the narrower prototype. Every difference must be explained by a
named, enumerated exclusion (listed in `_ui_literal_rederive.py`), and the test
fails on any difference that none explains. Differences found while freezing:
a greedy template match that began inside a `<script>` JSDoc mention of
`<template>` (detector fix: script and style blocks are blanked first), the
#15665 identifier rule, which hid every plain one-word label (narrowed for both
guards: a plain word is prose), and attributes skipped on or inside `<pre>`/`<code>` (detector fix: only
the content of an opaque element is opaque).

**The script kind stays un-re-derived, stated rather than left ambiguous.**
It matches JavaScript string literals after a handful of call shapes; the only
independent method would be a JavaScript parser, which this suite does not
carry, and a hand-rolled one would share the regex's blind spots. It is covered
by its known positive and by synthetic fixtures instead.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest
from repo_tests._hardcoded_ui_literal_baseline import (
    HARDCODED_UI_LITERAL_IDS,
    HARDCODED_UI_LITERALS,
    literal_digest,
)
from repo_tests._hardcoded_ui_literal_detect import (
    APP_TREES,
    REACH_UI_LITERAL_FILES,
    literals_in,
    scan,
    scanned_files,
)
from repo_tests._paths import repo_root
from repo_tests._ui_literal_rederive import (
    explain_parser_only,
    explain_regex_only,
    rederived,
    regex_literals,
    tracked_vue_files,
)
from repo_tests._ui_literal_scan import script_literals, template_hits

_PANEL = "autobot-frontend/src/components/knowledge/connectors/ConnectorHistoryPanel.vue"
_PANEL_LITERALS = {
    ("template-text", "Sync History"),
    ("template-text", "Running"),
    ("template-text", "No sync history yet."),
    ("attribute", "Close"),
}
_FIX = (
    "Use t('...') with an English key in en.json (English-only i18n; SLM locales go "
    "through scripts/lift_locale_translations.py). The untranslated ratchet may rise by "
    "exactly the moved keys (owner ruling, #12732)."
)


@pytest.fixture(scope="module")
def measured() -> dict[str, list[tuple[str, str]]]:
    return scan(repo_root())


def identity_diff(recorded, measured):
    """Per-file multiset diff of recorded digests against measured (kind, literal) pairs.

    Returns (new, stale): new is {file: [(kind, literal)]} with the CURRENT text from the scan,
    stale is {file: [digest]}. The baseline holds digests only (#18802), so a stale entry is
    named by its digest.
    """
    new, stale = {}, {}
    for f in sorted(set(recorded) | set(measured)):
        pairs = measured.get(f, [])
        have, had = Counter(literal_digest(k, t) for k, t in pairs), Counter(recorded.get(f, []))
        added = have - had
        if added:
            text = {literal_digest(k, t): (k, t) for k, t in pairs}
            new[f] = sorted(text[d] for d in added.elements())
        if gone := sorted((had - have).elements()):
            stale[f] = gone
    return new, stale


class TestThePopulationOnlyShrinks:
    def test_no_file_gains_a_literal(self, measured):
        new, _ = identity_diff(HARDCODED_UI_LITERAL_IDS, measured)
        assert not new, f"hard-coded UI text not in the baseline (file: [(kind, literal)]) {new}. {_FIX}"

    def test_a_removed_literal_is_deleted_in_the_commit_that_did_the_work(self, measured):
        _, stale = identity_diff(HARDCODED_UI_LITERAL_IDS, measured)
        assert not stale, (
            "literals gone from these files; delete these digests from "
            f"hardcoded_ui_literal_baseline_12732.json: {stale}"
        )

    def test_a_swap_in_one_file_fails_both_ways(self):
        """A per-file count passed this (#18802): one literal out, another in, same total."""
        recorded = {"A.vue": [literal_digest("script", "Old text")]}
        new, stale = identity_diff(recorded, {"A.vue": [("script", "New text")]})
        assert new == {"A.vue": [("script", "New text")]}
        assert stale == {"A.vue": [literal_digest("script", "Old text")]}
        assert identity_diff(recorded, {"A.vue": [("script", "Old text")]}) == ({}, {})

    def test_a_duplicate_literal_counts_twice(self):
        recorded = {"A.vue": [literal_digest("attribute", "Close")]}
        new, _ = identity_diff(recorded, {"A.vue": [("attribute", "Close")] * 2})
        assert new == {"A.vue": [("attribute", "Close")]}

    def test_the_kind_is_part_of_the_identity(self):
        """The same text as a different kind is a different literal."""
        assert literal_digest("attribute", "Close") != literal_digest("template-text", "Close")

    def test_the_baseline_stores_no_literal_text(self):
        """Digests only: no secret-shaped placeholder text in a tracked file (#18802)."""
        digest = re.compile(r"^[0-9a-f]{8}$")
        bad = {f: d for f, v in HARDCODED_UI_LITERAL_IDS.items() for d in v if not digest.match(d)}
        assert not bad, f"baseline entries that are not 8-hex digests: {bad}"

    def test_a_file_that_reaches_zero_leaves_the_dict(self, measured):
        gone = sorted(f for f in HARDCODED_UI_LITERALS if f not in measured)
        assert not gone, f"now at 0 literals (or deleted); remove from the baseline: {gone}"

    def test_the_baseline_has_no_zero_or_foreign_entries(self):
        files = set(scanned_files(repo_root()))
        bad = [f for f, n in HARDCODED_UI_LITERALS.items() if n <= 0 or f not in files]
        assert not bad, f"entries that are zero or outside the boundary: {bad}"

    def test_the_baseline_is_sorted(self):
        keys = list(HARDCODED_UI_LITERAL_IDS)
        assert keys == sorted(keys)
        unsorted = [f for f, v in HARDCODED_UI_LITERAL_IDS.items() if v != sorted(v)]
        assert not unsorted, f"digests not sorted within: {unsorted}"


class TestTheBoundaryDoesNotMoveSilently:
    def test_the_sweep_reaches_the_tree(self):
        read = len(scanned_files(repo_root()))
        assert read >= REACH_UI_LITERAL_FILES.floor, f"opened only {read} files, floor {REACH_UI_LITERAL_FILES.floor}"

    def test_both_apps_are_enumerated(self):
        files = scanned_files(repo_root())
        for tree in APP_TREES:
            assert any(f.startswith(tree.as_posix() + "/") for f in files), tree

    def test_a_known_component_is_in_and_non_product_files_are_out(self):
        files = scanned_files(repo_root())
        assert _PANEL in files
        tracked = tracked_vue_files(repo_root())
        assert not [f for f in files if "__tests__/" in f or ".stories." in f or ".spec." in f]
        excluded = [f for f in tracked if f not in files]
        assert all("__tests__/" in f or ".stories." in f or ".spec." in f or ".test." in f for f in excluded)

    def test_each_app_has_pinned_literals(self):
        for tree in APP_TREES:
            assert any(f.startswith(tree.as_posix() + "/") for f in HARDCODED_UI_LITERALS), tree


class TestKnownPositive:
    def test_the_detector_finds_the_history_panel_literals(self):
        text = (repo_root() / _PANEL).read_text(encoding="utf-8")
        assert _PANEL_LITERALS <= set(literals_in(text))


class TestEachMatcherOnSyntheticSources:
    def _kinds(self, source: str, kind: str) -> list[str]:
        return [t for k, t in literals_in(source) if k == kind]

    def test_template_text_is_found(self):
        assert self._kinds("<template><p>Hello world</p></template>", "template-text") == ["Hello world"]

    def test_template_text_negatives(self):
        src = "<template><p>{{ t('x') }}</p><i>OK</i><b>ab</b><u>HELP</u>" "<!-- <s>Hidden words</s> --></template>"
        assert self._kinds(src, "template-text") == []

    def test_a_template_tag_in_a_script_comment_does_not_open_the_template(self):
        src = "<script>\n/* <template #x> <b>Edit</b> */\n</script>\n<template><p>Real text</p></template>"
        assert self._kinds(src, "template-text") == ["Real text"]

    def test_text_outside_the_template_is_ignored(self):
        assert self._kinds("<script>const a = '<p>Hello there</p>'</script>", "template-text") == []

    def test_unbound_attribute_is_found(self):
        src = '<template><input placeholder="Search here" aria-label="Go"></template>'
        assert self._kinds(src, "attribute") == ["Search here"]

    def test_aria_description_is_found(self):
        assert self._kinds('<template><i aria-description="Opens the menu"></i></template>', "attribute") == [
            "Opens the menu"
        ]

    def test_attribute_negatives(self):
        src = (
            '<template><a :title="x" @title="y" data-title="Some words" '
            'title="{{ a }}" label="x"></a><!-- <i alt="Hidden words"> --></template>'
        )
        assert self._kinds(src, "attribute") == []

    def test_script_literal_is_found(self):
        src = "<script>msg.value = 'Failed to load'; throw new Error(\"Bad request\")</script>"
        assert self._kinds(src, "script") == ["Failed to load", "Bad request"]

    def test_script_negatives(self):
        src = "<script>a.value = 'lower case'; b.value = t('x'); title: 'A'</script>"
        assert self._kinds(src, "script") == []

    def test_script_quotes_close_on_the_opening_delimiter(self):
        """An apostrophe inside double quotes, and double quotes inside single (#18802)."""
        src = "<script>alert(\"Can't connect\"); e.value = 'Say \"hi\" now'; title: `It's ${n}`</script>"
        assert self._kinds(src, "script") == ["Can't connect", 'Say "hi" now', "It's ${n}"]

    def test_script_quote_negatives(self):
        """A mismatched pair is not a literal, nor is a lower-case string with an apostrophe."""
        assert self._kinds("<script>alert(\"Unclosed text')</script>", "script") == []
        assert self._kinds('<script>x.value = "don\'t count"</script>', "script") == []

    def test_script_text_in_template_is_not_a_script_literal(self):
        assert self._kinds("<template><p>message: 'Hello there'</p></template>", "script") == []


# ---- second derivation -------------------------------------------------------


def _detected(root: Path) -> set[tuple[str, str, str]]:
    return {(rel, kind, text) for rel, found in scan(root).items() for kind, text in found if kind != "script"}


def _unexplained(root: Path) -> list[tuple[str, str, str, str]]:
    """Differences between the two derivations that no named exclusion explains."""
    detected, other = _detected(root), rederived(root)
    out = []
    for side, items, explain in (
        ("regex-only", other - detected, explain_regex_only),
        ("parser-only", detected - other, explain_parser_only),
    ):
        for rel, kind, text in sorted(items):
            source = (root / rel).read_text(encoding="utf-8", errors="replace")
            if explain(source, kind, text) is None:
                out.append((side, rel, kind, text))
    return out


class TestSecondDerivation:
    def test_the_rederivation_finds_its_own_known_positive(self):
        found = regex_literals((repo_root() / _PANEL).read_text(encoding="utf-8"))
        assert _PANEL_LITERALS <= found

    def test_the_regexes_apply_the_predicate_on_synthetic_input(self):
        src = (
            '<template><p>Hello world</p><i>OK</i><b>{{ t("x") }}</b>'
            '<!-- <s>Hidden words</s> --><a :title="x" title="Real words"></a></template>'
        )
        assert regex_literals(src) == {("template-text", "Hello world"), ("attribute", "Real words")}

    def test_enumerations_agree(self):
        assert set(tracked_vue_files(repo_root())) == set(scanned_files(repo_root()))

    def test_both_derivations_find_a_large_shared_core(self):
        detected, other = _detected(repo_root()), rederived(repo_root())
        assert len(detected & other) >= 0.5 * len(other), "the derivations no longer describe the same population"

    def test_every_difference_has_a_named_justification(self):
        assert not _unexplained(repo_root()), f"unexplained differences: {_unexplained(repo_root())[:10]}"

    def test_the_exclusion_rules_explain_synthetic_differences(self):
        src = "<template><code>autobot-backend</code><p>By {{ x }} here</p></template>"
        assert explain_regex_only(src, "template-text", "some directory") is None
        assert explain_regex_only(src, "template-text", "autobot-backend") == "opaque-element"
        assert explain_parser_only(src, "template-text", "By   here") == "beside-interpolation"
        assert explain_parser_only(src, "template-text", "Nothing explains this") is None

    def test_an_exclusion_is_positional_and_requires_the_rest_to_match(self):
        src = "<template><p>Same name</p><code>Same name</code></template>"
        assert explain_regex_only(src, "template-text", "Same name") is None
        assert explain_parser_only(src, "template-text", "3 items found") == "outside-regex-class"
        assert explain_parser_only(src, "template-text", "Plain words here") is None
        assert explain_parser_only(src, "attribute", "*.pdf, *.md") == "outside-regex-class"


def test_script_blocks_end_at_any_valid_closing_tag() -> None:
    """`</script >` and `</SCRIPT foo>` close a block too (CodeQL py/bad-tag-filter, #12732)."""
    source = (
        "<template><p>Shown text here</p></template>\n"
        "<script setup>const a = 1</script >\n"
        '<script>alert("Spaced closing tag")</SCRIPT data-x>\n'
    )
    assert script_literals(source) == ["Spaced closing tag"]
    assert [kind for kind, _ in literals_in(source)] == ["template-text", "script"]


def test_each_line_of_a_multi_line_text_node_has_its_own_line_number() -> None:
    """A literal reports its own line, even after a multi-line interpolation (#18802 review)."""
    source = "<template>\n  <p>\n    First line here\n    {{\n      count\n    }}\n    Third real line\n  </p>\n</template>\n"
    assert [(hit.line, hit.text) for hit in template_hits(source)] == [(3, "First line here"), (7, "Third real line")]
