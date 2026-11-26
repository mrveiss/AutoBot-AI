# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one definition of the HTML comment pattern, and the plain remover built on it (#22261, #21643).

``tools/lint/_comment_syntax.py`` builds its script-aware, newline-keeping ``strip_html_comments`` on this
pattern; the backend, the research scripts and the pipeline scripts cannot import ``tools.lint``, so they reach it
here. ``repo_tests/html_comment_regex_single_21643_test.py`` fails a second copy of the pattern text anywhere in
the tracked Python of those trees.
"""

from __future__ import annotations

import re

#: One HTML comment, as a pattern string to embed in a larger alternation; compile it with ``HTML_COMMENT_FLAGS``.
HTML_COMMENT_PATTERN = r"<!--.*?-->"
HTML_COMMENT_FLAGS = re.DOTALL

#: The compiled form, for a caller that wants ``.sub`` / ``.finditer`` on its own text.
HTML_COMMENT = re.compile(HTML_COMMENT_PATTERN, HTML_COMMENT_FLAGS)


def remove_html_comments(text: str, replacement: str = "") -> str:
    """*text* with each ``<!-- ... -->`` replaced by *replacement*; an unclosed ``<!--`` stays as text."""
    return HTML_COMMENT.sub(replacement, text)
