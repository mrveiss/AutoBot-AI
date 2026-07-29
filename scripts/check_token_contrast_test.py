# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""WCAG AA contrast gate for design tokens (#12730, umbrella step 4).

#12711 reported the symptom this catches: text rendered dark-on-dark and
light-on-light. Checking the *token definitions* rather than rendered pixels is
deliberate — tokens are where the contrast decision is actually made, and it
needs no browser, so it can gate every PR cheaply.

The maths is pinned against published WCAG reference values rather than against
this implementation's own output, so a refactor cannot quietly redefine what
"AA" means.
"""

import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "check_token_contrast", Path(__file__).parent / "check_token_contrast.py"
)
contrast = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contrast)


class TestContrastMaths:
    """Reference values from the WCAG 2.1 definition — not self-generated."""

    def test_black_on_white_is_the_maximum(self):
        assert round(contrast.contrast_ratio("#000000", "#ffffff"), 2) == 21.0

    def test_identical_colours_have_no_contrast(self):
        assert contrast.contrast_ratio("#3b82f6", "#3b82f6") == 1.0

    def test_ratio_is_symmetric(self):
        """Order must not matter — the spec defines lighter-over-darker."""
        a = contrast.contrast_ratio("#10b981", "#000000")
        b = contrast.contrast_ratio("#000000", "#10b981")

        assert a == b

    @pytest.mark.parametrize("shorthand,longhand", [("#fff", "#ffffff"), ("#000", "#000000"), ("#0f8", "#00ff88")])
    def test_shorthand_hex_expands(self, shorthand, longhand):
        assert contrast.relative_luminance(shorthand) == contrast.relative_luminance(longhand)

    def test_alpha_channel_is_ignored_not_misparsed(self):
        """#rrggbbaa must read as its rgb, not shift the channels."""
        assert contrast.relative_luminance("#10b981ff") == contrast.relative_luminance("#10b981")


class TestTokenParsing:
    CSS = """
    :root {
      --color-success: #10b981;
      --text-on-success: #000000;
      --bg-overlay: rgba(0, 0, 0, 0.5);
      --color-primary: #3b82f6;
    }
    @media (color-gamut: p3) {
      :root { --color-success: oklch(69.6% 0.149 162.5); }
    }
    """

    def test_hex_tokens_are_collected(self):
        tokens = contrast.parse_hex_tokens(self.CSS)

        assert tokens["--color-success"] == "#10b981"
        assert tokens["--text-on-success"] == "#000000"

    def test_first_definition_wins_over_theme_overrides(self):
        """The later oklch block must not silently replace the base value."""
        assert contrast.parse_hex_tokens(self.CSS)["--color-success"] == "#10b981"

    def test_non_hex_tokens_are_reported_not_dropped(self):
        """Silent skipping would imply coverage the gate does not have."""
        skipped = contrast.parse_non_hex_tokens(self.CSS)

        assert "--bg-overlay" in skipped
        assert "--color-success" not in skipped, "a token with a hex base is checked, not skipped"


class TestPairDerivation:
    def test_text_on_x_pairs_with_color_x(self):
        tokens = {"--text-on-success": "#000000", "--color-success": "#10b981"}

        assert ("--text-on-success", "--color-success", contrast.AA_LARGE) in contrast.build_pairs(tokens)

    def test_unpaired_token_is_not_invented(self):
        """No --color-brand means no pair — never compare against a guess."""
        pairs = contrast.build_pairs({"--text-on-brand": "#ffffff"})

        assert pairs == []

    def test_text_inverse_is_excluded_by_design(self):
        """It exists to sit on an inverted surface; measuring it would misreport."""
        tokens = {"--text-inverse": "#0f172a", "--bg-primary": "#0f172a"}

        assert contrast.build_pairs(tokens) == []


class TestRealTokens:
    """The gate against the actual stylesheet — this is what CI enforces."""

    def test_every_derived_pair_meets_aa(self):
        css = contrast.TOKENS_CSS.read_text(encoding="utf-8")
        tokens = contrast.parse_hex_tokens(css)
        pairs = contrast.build_pairs(tokens)

        assert pairs, "no pairs derived — the naming convention or file path has changed"

        failures = [
            (fg, bg, contrast.contrast_ratio(tokens[fg], tokens[bg]), need)
            for fg, bg, need in pairs
            if contrast.contrast_ratio(tokens[fg], tokens[bg]) < need
        ]

        assert not failures, "tokens below WCAG AA: " + ", ".join(
            f"{fg} on {bg} = {ratio:.2f}:1 < {need}" for fg, bg, ratio, need in failures
        )


class TestOklchConversion:
    """oklch -> sRGB, so wide-gamut overrides are measurable (#12922).

    #12915 fixed `--text-on-success` in the hex block, but the wide-gamut block
    re-declared the same pair in oklch and kept shipping white-on-green at
    2.54:1 on P3 displays. Those overrides were not merely unchecked — they
    shadow names already in the hex map, so they never reached the "NOT CHECKED"
    list either. They were invisible.
    """

    @pytest.mark.parametrize(
        "oklch,expected",
        [
            ("oklch(100% 0 0)", "#ffffff"),
            ("oklch(0% 0 0)", "#000000"),
            ("oklch(69.6% 0.149 162.5)", "#10b981"),
        ],
    )
    def test_known_colours_round_trip_to_their_srgb_hex(self, oklch, expected):
        """Pinned against the sRGB values the same tokens carry in the hex block."""
        assert contrast.oklch_to_hex(oklch) == expected

    def test_non_oklch_values_return_none(self):
        """rgba()/hex must fall through to their own handling, not be misparsed."""
        assert contrast.oklch_to_hex("#10b981") is None
        assert contrast.oklch_to_hex("rgba(0, 0, 0, 0.5)") is None

    def test_out_of_gamut_components_are_clamped(self):
        """A browser clamps when rendering oklch on sRGB; the ratio must match that."""
        result = contrast.oklch_to_hex("oklch(100% 0.4 120)")

        assert result is not None and len(result) == 7

    def test_wide_gamut_overrides_are_parsed_from_the_stylesheet(self):
        css = contrast.TOKENS_CSS.read_text(encoding="utf-8")

        overrides = contrast.parse_oklch_tokens(css)

        assert "--text-on-success" in overrides
        assert "--color-success" in overrides

    def test_parsed_oklch_tokens_are_not_reported_as_unchecked(self):
        """Otherwise the gate would claim coverage it has, then list it as missing."""
        css = contrast.TOKENS_CSS.read_text(encoding="utf-8")

        overrides = contrast.parse_oklch_tokens(css)
        skipped = contrast.parse_non_hex_tokens(css)

        assert not (set(overrides) & set(skipped))

    def test_wide_gamut_pairs_meet_aa(self):
        """The gate that would have caught #12922 at the time."""
        css = contrast.TOKENS_CSS.read_text(encoding="utf-8")
        merged = {**contrast.parse_hex_tokens(css), **contrast.parse_oklch_tokens(css)}

        failures = [
            (fg, bg, contrast.contrast_ratio(merged[fg], merged[bg]), need)
            for fg, bg, need in contrast.build_pairs(merged)
            if contrast.contrast_ratio(merged[fg], merged[bg]) < need
        ]

        assert not failures, "wide-gamut pairs below AA: " + ", ".join(
            f"{fg} on {bg} = {r:.2f}:1 < {n}" for fg, bg, r, n in failures
        )
