# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A class string that fills with ``bg-autobot-primary`` reads ``text-autobot-text-on-primary`` (#21543).

**The defect.** ``--color-autobot-primary`` is ``--color-primary``, which is white in High Contrast Dark and
pale in Dark, so ``bg-autobot-primary text-white`` renders an invisible label there. #20425 closed this
for CSS rules; the guard behind it reads declarations and never saw the Tailwind class form.

**The boundary.** One class string: a run of class tokens in a ``.vue``, ``.ts``, ``.js`` or ``.css`` file
under ``autobot-frontend/src`` or ``autobot-slm-frontend/src`` (the control plane's keys carry ``slm:``).
It counts when the run holds a primary fill (``bg-autobot-primary`` with any variant prefix, opacity
suffix, or the ``-hover``/``-active``/``-light``/``-dark``/``-bg`` shade) AND a white ``text-`` utility
(``text-white``, ``text-[white]``, ``text-[#fff]``, any variant prefix). Not counted: the token
``text-autobot-text-on-primary``, a white label on any other fill, a primary fill with no text utility,
a label in a different attribute or element, and anything inside a comment. Test files are not read.

**The pin.** ``WHITE_ON_PRIMARY_CLASS_LABELS`` is empty: every site is converted. Entries only shrink.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._hardcoded_colour_baseline import WHITE_ON_PRIMARY_CLASS_LABELS
from repo_tests._hardcoded_colour_detect import (
    REACH_CLASS_FORM_FILES,
    _class_form_scanned_files,
    _scan_white_class_on_primary,
    white_class_on_primary_in,
)
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import BaseUnavailable, base_table, raised_entries

_ISSUE = "https://github.com/mrveiss/AutoBot-AI/issues/21543"
_USE_TOKEN = f" Use text-autobot-text-on-primary for a label on bg-autobot-primary. See {_ISSUE}."

_FIRES = {
    "same-line": '<button class="px-4 bg-autobot-primary text-white rounded">x</button>',
    "label-first": '<button class="text-white bg-autobot-primary">x</button>',
    "multi-line-attribute": '<button\n  class="px-4 py-2\n    bg-autobot-primary\n    rounded text-white"\n>x</button>',
    "hover-fill": '<a class="hover:bg-autobot-primary-hover text-white">x</a>',
    "fill-with-hover-shade": '<a class="bg-autobot-primary hover:bg-autobot-primary-hover text-white">x</a>',
    "opacity-fill": '<a class="bg-autobot-primary/90 text-white">x</a>',
    "hover-label": '<a class="bg-autobot-primary hover:text-white">x</a>',
    "arbitrary-white": '<a class="bg-autobot-primary text-[#fff]">x</a>',
    "bound-class-ternary": "<a :class=\"on ? 'bg-autobot-primary text-white' : 'bg-autobot-bg-card'\">x</a>",
    "bound-class-object-key": "<a :class=\"{ 'bg-autobot-primary text-white': on }\">x</a>",
    "ts-class-string": "export const t = { cls: 'bg-autobot-primary text-white' }",
    "apply-statement": ".badge { @apply bg-autobot-primary text-white rounded; }",
}
_QUIET = {
    "the-token": '<a class="bg-autobot-primary text-autobot-text-on-primary">x</a>',
    "white-on-another-fill": '<a class="bg-red-600 text-white">x</a>',
    "white-on-a-token-fill": '<a class="bg-autobot-error-solid text-white">x</a>',
    "primary-text-not-fill": '<a class="text-autobot-primary text-white">x</a>',
    "primary-border-not-fill": '<a class="border-autobot-primary text-white">x</a>',
    "fill-without-a-text-utility": '<a class="bg-autobot-primary rounded">x</a>',
    "label-in-another-attribute": '<a class="bg-autobot-primary" :class="[\'text-white\']">x</a>',
    "label-on-a-sibling-element": '<a class="bg-autobot-primary"><b class="text-white">x</b></a>',
    "inverse-token": '<a class="bg-autobot-primary text-autobot-text-inverse">x</a>',
    "block-comment": "/* bg-autobot-primary text-white */\nconst a = 1",
    "html-comment": '<!-- <a class="bg-autobot-primary text-white">x</a> -->\n<b/>',
    "line-comment": "// cls: 'bg-autobot-primary text-white'\nconst a = 1",
    "trailing-line-comment": "const a = 1 // 'bg-autobot-primary text-white'",
}


class TestTheDetectorWorksBeforeItsOutputIsRead:
    """Synthetic, so these keep testing something now the baseline is empty."""

    @pytest.mark.parametrize("source", _FIRES.values(), ids=list(_FIRES))
    def test_a_white_label_on_the_primary_fill_fires(self, source: str) -> None:
        assert white_class_on_primary_in(source) == 1

    @pytest.mark.parametrize("source", _QUIET.values(), ids=list(_QUIET))
    def test_the_token_other_fills_and_comments_stay_quiet(self, source: str) -> None:
        assert white_class_on_primary_in(source) == 0

    def test_two_offending_strings_count_twice(self) -> None:
        two = '<a class="bg-autobot-primary text-white">x</a>\n<b class="text-white bg-autobot-primary">y</b>'
        assert white_class_on_primary_in(two) == 2

    def test_the_scan_keys_both_apps_and_skips_test_files(self, tmp_path: Path) -> None:
        bad = '<template><a class="bg-autobot-primary text-white">x</a></template>'
        for rel in (
            "autobot-frontend/src/views/A.vue",
            "autobot-slm-frontend/src/views/B.vue",
            "autobot-frontend/src/__tests__/C.vue",
            "autobot-frontend/src/views/D.spec.ts",
        ):
            target = tmp_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(bad, encoding="utf-8")
        assert _scan_white_class_on_primary(tmp_path) == {"views/A.vue": 1, "slm:views/B.vue": 1}


class TestTheRealTree:
    def test_the_scan_reached_both_apps(self) -> None:
        files = _class_form_scanned_files(repo_root())
        assert len(files) >= REACH_CLASS_FORM_FILES.floor, (
            "the class-form scan read fewer files than declared." + _USE_TOKEN
        )
        assert any(
            f.startswith("autobot-slm-frontend/") for f in files
        ), "no control-plane file was read; the scan is blind to it."
        assert any(
            f.startswith("autobot-frontend/") for f in files
        ), "no user-frontend file was read; the scan is blind to it."

    def test_no_entry_rose_against_the_base(self) -> None:
        try:
            base = base_table(
                repo_root(), ("repo_tests/_hardcoded_colour_baseline.py",), "WHITE_ON_PRIMARY_CLASS_LABELS"
            )
        except BaseUnavailable as err:
            if "no literal WHITE_ON_PRIMARY_CLASS_LABELS" not in str(err):
                raise
            pytest.skip("the table is introduced by #21543, so the base has none; this arms once it lands")
        rose = raised_entries(WHITE_ON_PRIMARY_CLASS_LABELS, base)
        assert not rose, f"class-form entries raised or added against the base (base, now): {rose}." + _USE_TOKEN

    def test_every_pinned_count_matches_the_tree(self) -> None:
        measured = _scan_white_class_on_primary(repo_root())
        assert measured == WHITE_ON_PRIMARY_CLASS_LABELS, (
            f"measured {measured}, pinned {WHITE_ON_PRIMARY_CLASS_LABELS}. A white label on the primary fill is "
            "invisible in High Contrast Dark (#20425). Equality, so a converted file's entry is deleted "
            "rather than left as headroom." + _USE_TOKEN
        )
