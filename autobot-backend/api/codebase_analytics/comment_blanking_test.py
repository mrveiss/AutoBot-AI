# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Comment blanking for the frontend call scanner (#17668).

The scanner decided "is this a comment?" per line, by prefix, and three of the four
findings on the live "Potential Bugs" panel were JSDoc examples. These tests are
organised around the two failure *directions*, because only one of them is visible:
a false positive shows up as a wrong finding, a false negative shows up as a clean
panel. The second group matters more for that reason.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

_MODULE = Path(__file__).with_name("comment_blanking.py")
_spec = importlib.util.spec_from_file_location("comment_blanking_under_test", _MODULE)
_cb = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_cb)
blank_comments = _cb.blank_comments

_API = re.compile(r"""['"`](/api/[^'"` ]+)['"`]""")


def _visible(src: str) -> list[str]:
    """The `/api/...` literals a line-oriented scanner would still see."""
    return _API.findall(blank_comments(src))


# ---------------------------------------------------------------------------
# False positives: documentation must not read as a call site
# ---------------------------------------------------------------------------


class TestCommentsAreSilenced:
    def test_a_jsdoc_continuation_line_is_not_a_call(self) -> None:
        # The exact shape of three live findings: the call sits on a `*` line, which
        # starts with neither `//` nor `/*`, so the prefix test passed it through.
        src = """
        /**
         * Usage:
         *   const response = await ApiClient.get('/api/export')
         */
        export function useFileDownload() {}
        """
        assert _visible(src) == []

    def test_a_block_interior_without_a_leading_star_is_not_a_call(self) -> None:
        src = "/*\n  apiClient.get('/api/hidden')\n*/\n"
        assert _visible(src) == []

    def test_a_comment_trailing_real_code_is_not_a_call(self) -> None:
        # The line does not *start* with `//`, so the prefix test scanned it.
        src = "doThing()  // apiClient.get('/api/legacy')\n"
        assert _visible(src) == []

    def test_a_vue_template_comment_is_not_a_call(self) -> None:
        src = "<!-- <a @click=\"apiClient.get('/api/commented')\">x</a> -->\n"
        assert _visible(src) == []

    def test_a_multi_line_block_closes_and_code_after_it_is_scanned(self) -> None:
        src = "/*\n apiClient.get('/api/gone')\n*/\napiClient.get('/api/kept')\n"
        assert _visible(src) == ["/api/kept"]


# ---------------------------------------------------------------------------
# False negatives: the silent direction, which is why string handling exists
# ---------------------------------------------------------------------------


class TestRealCallsSurvive:
    def test_a_url_containing_a_double_slash_does_not_start_a_comment(self) -> None:
        # Without string awareness the `//` in `https://` blanks the rest of the
        # line. That silences a genuine call and reports nothing, which is the
        # failure direction that looks like success.
        scheme = "https:" + "//"
        src = f"await fetch('{scheme}h.invalid/api/keep')\n"
        assert _visible(src) == []  # the path is inside the URL, not a bare literal
        assert "h.invalid/api/keep" in blank_comments(src)

    def test_a_plain_call_is_untouched(self) -> None:
        src = "await apiClient.post('/api/themes', form)\n"
        assert _visible(src) == ["/api/themes"]

    def test_a_block_comment_marker_inside_a_string_is_not_a_comment(self) -> None:
        src = "const glob = '/* not a comment */'\nawait apiClient.get('/api/after')\n"
        assert _visible(src) == ["/api/after"]

    def test_an_escaped_quote_does_not_end_the_string(self) -> None:
        src = "const s = 'it\\\\'s fine'\nawait apiClient.get('/api/after')\n"
        assert "/api/after" in _visible(src)

    def test_a_comment_inside_a_template_interpolation_is_blanked(self) -> None:
        """`${...}` is code, not template text (#17670 review).

        The literal around it is copied verbatim so a URL survives, which means a
        comment inside an interpolation survived too until interpolations were
        processed recursively.
        """
        src = "const x = `${/* apiClient.get('/api/hidden') */ ''}`\n"
        assert _visible(src) == []

    def test_nested_braces_in_an_interpolation_do_not_end_it_early(self) -> None:
        src = "const y = `${ {a: 1}['a'] /* api.get('/api/gone') */ }`\n"
        assert _visible(src) == []

    def test_a_brace_inside_an_interpolation_comment_does_not_close_it(self) -> None:
        """`_matching_brace` counted raw braces, so a `}` in a comment ended the
        interpolation early and the rest of the comment was copied out as template
        text -- the leak this module exists to close, one level down (#17670 review).
        """
        src = "const x = `${/* } api.get('/api/hidden') */ ''}`\n"
        assert _visible(src) == []

    def test_a_brace_inside_an_interpolation_string_does_not_close_it(self) -> None:
        # Same cause as the comment case: a brace in a string is not a delimiter.
        src = "const y = `${ m['}'] /* api.get('/api/gone') */ }`\n"
        assert _visible(src) == []

    def test_template_text_around_an_interpolation_is_untouched(self) -> None:
        # The path is template *text*; only the `${...}` is treated as code.
        src = "await apiClient.get(`/api/items/${id}`)\n"
        assert "`/api/items/${id}`" in blank_comments(src)

    def test_a_template_literal_is_passed_through(self) -> None:
        src = "await apiClient.get(`/api/items/${id}`)\n"
        assert "`/api/items/${id}`" in blank_comments(src)


# ---------------------------------------------------------------------------
# Structure: reported positions must stay correct
# ---------------------------------------------------------------------------


class TestPositionsArePreserved:
    @pytest.mark.parametrize(
        "src",
        [
            "/**\n * a\n */\ncode()\n",
            "a()  // tail\nb()\n",
            "<!-- x -->\ny()\n",
            "const u = 'x:" + "//h/a'\n",
            "/* unterminated\nstill inside\n",
        ],
    )
    def test_length_and_line_count_are_unchanged(self, src: str) -> None:
        # Comment characters become spaces rather than disappearing, so every
        # `file:line` the scanner reports still points at the same place.
        out = blank_comments(src)
        assert len(out) == len(src)
        assert out.count("\n") == src.count("\n")

    def test_line_numbers_of_surviving_calls_are_unchanged(self) -> None:
        src = "/**\n * apiClient.get('/api/doc')\n */\napiClient.get('/api/real')\n"
        after = blank_comments(src).splitlines()
        assert [i for i, line in enumerate(after, 1) if "/api/real" in line] == [4]


# ---------------------------------------------------------------------------
# Non-vacuity: the sweeps above pass on an empty string
# ---------------------------------------------------------------------------


def test_the_blanker_actually_blanks_something() -> None:
    """A `blank_comments` that returned its input unchanged would pass several
    assertions above -- every one about a *surviving* call. This fails on identity.
    """
    src = "/**\n * apiClient.get('/api/doc')\n */\n"
    assert blank_comments(src) != src
