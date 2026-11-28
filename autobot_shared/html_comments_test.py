# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared HTML-comment pattern and remover (#22261)."""

from __future__ import annotations

import re

from autobot_shared.html_comments import HTML_COMMENT, HTML_COMMENT_FLAGS, HTML_COMMENT_PATTERN, remove_html_comments


def test_a_single_and_a_multi_line_comment_are_removed() -> None:
    assert remove_html_comments("a<!-- x -->b<!--\ny\n-->c") == "abc"


def test_the_replacement_is_used_and_an_unclosed_opener_stays_as_text() -> None:
    assert remove_html_comments("a<!-- x -->b", " ") == "a b"
    assert remove_html_comments("a<!-- open") == "a<!-- open"


def test_the_pattern_embeds_in_an_alternation_and_the_compiled_form_matches_it() -> None:
    both = re.compile(HTML_COMMENT_PATTERN + r"|`[^`]*`", HTML_COMMENT_FLAGS)
    assert both.sub("", "a<!-- x -->b`c`d") == "abd"
    assert HTML_COMMENT.pattern == HTML_COMMENT_PATTERN
