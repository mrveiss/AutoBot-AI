# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared JS-family lexer: nesting, regex-or-division, unterminated input, linear time (#22194)."""

import time

import pytest

from autobot_shared.js_lexer import BLOCK_COMMENT, CODE, LINE_COMMENT, REGEX, STRING, blank_block_comment, lex_js


def _kinds(text: str, kind: str, **kwargs) -> list[str]:
    return [piece for k, piece in lex_js(text, **kwargs).pieces if k == kind]


@pytest.mark.parametrize(
    "text",
    [
        "const a = `x ${`in ${1}`} y`; // c\nb()",
        "x = /a\\/b/g.test('/*') /* c */",
        "`a ${ {b: 1}.b } c` // tail",
        "'unclosed\n\"also",
        "`a ${b",
        "/* open",
    ],
)
def test_the_pieces_join_back_to_the_text(text):
    assert "".join(piece for _, piece in lex_js(text).pieces) == text


def test_braces_inside_an_expression_do_not_close_it():
    text = "`a ${ {b: '}'}.b } c` // real"
    assert _kinds(text, STRING) == ["`a ", "'}'", " c`"]
    assert _kinds(text, LINE_COMMENT) == ["// real"]


def test_a_comment_inside_an_expression_is_a_comment():
    text = "`a ${ x /* } ` */ + 1 } b`"
    assert _kinds(text, BLOCK_COMMENT) == ["/* } ` */"]
    assert _kinds(text, STRING) == ["`a ", " b`"]
    assert lex_js(text).unterminated is None


def test_strings_holding_comment_markers_are_strings():
    text = "x = \"a // b /* c\"; y = 'http://z'; // real"
    assert _kinds(text, STRING) == ['"a // b /* c"', "'http://z'"]
    assert _kinds(text, LINE_COMMENT) == ["// real"]
    assert not _kinds(text, BLOCK_COMMENT)


@pytest.mark.parametrize(
    "text, construct",
    [("/* x", "block comment"), ("'abc", "quote"), ("`a", "quote"), ("`a ${b", "quote"), ("a = 1", None)],
)
def test_unterminated_input_is_named(text, construct):
    assert lex_js(text).unterminated == construct


def test_a_quote_ends_at_its_line():
    assert _kinds("don't /* x */\ny", BLOCK_COMMENT) == []  # the apostrophe's string swallows its own line only
    assert _kinds("don't\n/* x */ y", BLOCK_COMMENT) == ["/* x */"]


@pytest.mark.parametrize(
    "text, regex",
    [
        ("i++ / 2 // c", []),  # a postfix increment ends an operand: division, then a comment
        ("i-- / 2 / c", []),
        ("(a) / 2 / b // c", []),  # after `)` the slash divides
        ("x => /a\\/b/.test(s) // c", ["/a\\/b/"]),  # an arrow body is an expression
        ("return /[/]/.test(s)", ["/[/]/"]),
        ("if (!/x/.test(s)) f()", ["/x/"]),  # a prefix `!` negates
        ("y = x! / 2 / 3", []),  # a postfix `!` asserts non-null: division
        ("a = b < /re/ ? 1 : 2", []),  # `<` is not a regex opener: `</tag>` in `.vue`
    ],
)
def test_the_slash_rules(text, regex):
    assert _kinds(text, REGEX) == regex


def test_css_has_no_line_comments_regexes_or_template_nesting():
    text = "a { b: url(//x) } `${'`'}`\n/* c */"
    lexed = lex_js(text, line_comments=False)
    assert _kinds(text, LINE_COMMENT, line_comments=False) == []
    assert _kinds(text, STRING, line_comments=False)[0] == "`${'`"  # flat to the next backtick
    assert [k for k, _ in lexed.pieces].count(BLOCK_COMMENT) == 1


def test_a_block_comment_blanks_to_its_newlines():
    assert blank_block_comment("/* a\n b */") == "  \n   "
    assert blank_block_comment("/* open") == "     "


def test_five_hundred_nested_templates_need_no_recursion():
    depth = 500
    text = "`${" * depth + "x" + "}`" * depth + " // c"
    lexed = lex_js(text)
    assert lexed.unterminated is None
    assert _kinds(text, LINE_COMMENT) == ["// c"]
    assert _kinds(text, STRING) == ["`"] * (2 * depth)  # each level: its opening and its closing backtick
    assert "${x}" in _kinds(text, CODE)
    assert "".join(piece for _, piece in lexed.pieces) == text


@pytest.mark.parametrize("unit", ["(/[", "a=(b)/c;", "x=/\\/"])
def test_a_long_minified_line_is_lexed_in_linear_time(unit):
    """Every `/` here may open a regex that never closes: rescanning the rest of the line each time is quadratic."""
    text = unit * 30_000
    started = time.perf_counter()
    lexed = lex_js(text)
    assert time.perf_counter() - started < 5.0  # quadratic: ~10**9 steps, minutes
    assert "".join(piece for _, piece in lexed.pieces) == text
