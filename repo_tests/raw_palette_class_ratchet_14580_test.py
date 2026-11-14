# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A palette class in a template cannot follow the theme (#14580, #17566).

`color-no-hex` reads `<style>` only; `bg-red-50` in a template is invisible to
it and stays light-red in a dark theme. This ratchet freezes the population in
both frontends and fails on growth, so new code is blocked now and the existing
debt drains through the sweeps that own it.

The detector and its reach declaration are `repo_tests._raw_palette_detect`; the
frozen numbers are `repo_tests._raw_palette_baseline`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table, raised_entries
from repo_tests._raw_palette_baseline import RAW_PALETTE_CLASSES
from repo_tests._raw_palette_detect import (
    RAW_PALETTE_CLASS,
    REACH_PALETTE_FILES,
    SLM_KEY_PREFIX,
    scan,
    scan_tree,
    scanned_files,
)

#: Printed with every failure, so a gate that says "forbidden" does not produce a workaround
#: (#17567). The token vocabulary is the same in both apps (docs/design/REFINED_TOKEN_MAPPING.md).
_FIX = (
    "Use a design token instead of a palette step: a Tailwind utility on the autobot-* scale "
    "(bg-autobot-bg-card, text-autobot-text-secondary, border-autobot-border, text-autobot-error, ...) "
    "or var(--token) in a <style> block; status colours map to --color-error/-success/-warning/-info. "
    "Mapping: docs/design/REFINED_TOKEN_MAPPING.md. Owners: #14580 (the check), #17566 (the SLM sweep)."
)


@pytest.fixture(scope="module")
def measured() -> dict[str, int]:
    return scan(repo_root())


class TestTheDetectorWorksBeforeItsOutputIsRead:
    """Synthetic, so these keep testing something once the baseline drains."""

    def _scan(self, tmp_path: Path, body: str) -> dict[str, int]:
        (tmp_path / "A.vue").write_text(body, encoding="utf-8")
        return scan_tree(tmp_path)

    def test_a_plain_palette_class_is_found(self, tmp_path):
        assert self._scan(tmp_path, '<template><p class="bg-red-50 text-gray-700"/></template>') == {
            "bg-red-50": 1,
            "text-gray-700": 1,
        }

    def test_a_variant_prefix_does_not_hide_it(self, tmp_path):
        found = self._scan(tmp_path, '<template><p class="hover:bg-blue-500 dark:border-slate-800/60"/></template>')
        assert found == {"bg-blue-500": 1, "border-slate-800/60": 1}

    def test_a_class_binding_is_found(self, tmp_path):
        assert self._scan(tmp_path, "<template><p :class=\"ok ? 'text-green-600' : 'text-red-600'\"/></template>") == {
            "text-green-600": 1,
            "text-red-600": 1,
        }

    def test_the_design_system_scale_is_not_flagged(self, tmp_path):
        body = '<template><p class="bg-autobot-bg-card text-autobot-error bg-white text-black border"/></template>'
        assert self._scan(tmp_path, body) == {}

    def test_a_style_block_is_not_this_guards_to_read(self, tmp_path):
        assert self._scan(tmp_path, "<style>.x { @apply bg-red-500; }</style>") == {}

    def test_a_longer_word_is_not_a_palette_class(self, tmp_path):
        assert self._scan(tmp_path, '<template><p class="textbg-red-500x icon-red-500"/></template>') == {}

    def test_the_slm_keeps_its_own_counts(self, tmp_path):
        for name in ("autobot-frontend", "autobot-slm-frontend"):
            d = tmp_path / name / "src"
            d.mkdir(parents=True)
            (d / "A.vue").write_text('<template><p class="bg-red-500"/></template>', encoding="utf-8")
        assert scan(tmp_path) == {"bg-red-500": 1, f"{SLM_KEY_PREFIX}bg-red-500": 1}

    def test_the_pattern_is_compiled(self):
        assert RAW_PALETTE_CLASS.search("bg-red-500")


class TestThePopulationOnlyShrinks:
    def test_the_sweep_reaches_both_apps(self):
        read = scanned_files(repo_root())
        assert len(read) >= REACH_PALETTE_FILES.floor, (
            f"opened {len(read)} components, floor {REACH_PALETTE_FILES.floor} -- "
            "an empty result would mean 'nothing was read', not 'nothing was found'"
        )
        assert any(f.startswith(SLM_KEY_PREFIX) for f in read), "the control plane was never opened"

    def test_no_entry_rose_against_the_base(self):
        """#19283: the tripwire for a raised entry is the base commit's table, not a hand total."""
        base = base_table(repo_root(), ("repo_tests/_raw_palette_baseline.py",), "RAW_PALETTE_CLASSES")
        rose = raised_entries(RAW_PALETTE_CLASSES, base)
        assert not rose, f"entries raised or added against the base (base, now): {rose}. {_FIX}"

    def test_no_entry_is_zero(self):
        assert all(n > 0 for n in RAW_PALETTE_CLASSES.values())

    def test_no_class_gains_a_use(self, measured):
        grew = {k: (RAW_PALETTE_CLASSES.get(k, 0), n) for k, n in measured.items() if n > RAW_PALETTE_CLASSES.get(k, 0)}
        assert not grew, f"raw palette classes used more often than pinned (pinned, now): {grew}. {_FIX}"

    def test_a_drained_class_leaves_the_baseline(self, measured):
        stale = sorted(k for k, n in RAW_PALETTE_CLASSES.items() if measured.get(k, 0) < n)
        assert not stale, (
            "fewer uses than pinned -- lower the entry (or delete it at zero), "
            f"or the freed headroom lets the class come back: {stale}"
        )
