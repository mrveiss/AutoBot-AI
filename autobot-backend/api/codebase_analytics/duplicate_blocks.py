# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Code blocks for the duplicate detector: model, normalization and qualification (#22157).

Two normalizations exist on purpose. ``normalize_exact`` removes comments and
whitespace only, so two blocks that agree after it are the same code. The
structural form additionally erases every string literal, so it also equates
blocks that differ only in their text (prompts, messages, paths). A block
qualifies on the size of its STRUCTURAL form: judged on the raw text, thirty
50-line ``_get_system_prompt`` methods normalised to nine tokens each and were
reported as one another's 100% duplicates.
"""

import re
from dataclasses import dataclass, field
from typing import Optional, Set

from autobot_shared.content_digest import content_digest

# Minimum lines for a code block to be considered for duplicate detection
# Issue #609: Reduced from 5 to 4 to catch more smaller duplicates
MIN_DUPLICATE_LINES = 4
# Minimum characters of the NORMALIZED block (#22157: was measured on the raw text)
MIN_DUPLICATE_CHARS = 80

# A quoted string is matched first so a comment marker inside it is not a comment.
_STRING_OR_COMMENT_RE = re.compile(
    r"""(?P<string>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')|\#[^\n]*|//[^\n]*""",
)


@dataclass
class CodeBlock:
    """Represents a block of code for duplicate detection."""

    file_path: str
    start_line: int
    end_line: int
    content: str
    normalized_content: str
    content_hash: str
    line_count: int
    # Issue #659: Pre-computed token set for 30-40% faster similarity computation
    # Avoids recomputing tokens on every comparison
    token_set: Set[str] = field(default_factory=set)
    # #22157: hash of the comment- and whitespace-normalized text only; equal here
    # means the same code, where ``content_hash`` also equates differing strings.
    exact_hash: str = ""


def normalize_structural(content: str) -> str:
    """Normalize code for structural comparison by removing comments, string text and whitespace variation."""
    # Remove single-line comments
    content = re.sub(r"#.*$", "", content, flags=re.MULTILINE)
    content = re.sub(r"//.*$", "", content, flags=re.MULTILINE)

    # Remove multi-line comments
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = re.sub(r'""".*?"""', '""', content, flags=re.DOTALL)
    content = re.sub(r"'''.*?'''", "''", content, flags=re.DOTALL)

    # Normalize string literals
    content = re.sub(r'"[^"]*"', '"STR"', content)
    content = re.sub(r"'[^']*'", "'STR'", content)

    # Normalize whitespace
    content = re.sub(r"\s+", " ", content)

    return content.strip().lower()


def normalize_exact(content: str) -> str:
    """Normalize by removing comments and whitespace variation ONLY; strings and case are kept."""
    content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
    content = _STRING_OR_COMMENT_RE.sub(lambda m: m.group("string") or "", content)
    return re.sub(r"\s+", " ", content).strip()


def make_block(file_path: str, start_line: int, end_line: int, content: str, line_count: int) -> Optional[CodeBlock]:
    """Build a block, or None when its normalized form is too small to be a duplicate (#22157)."""
    normalized = normalize_structural(content)
    if len(normalized) < MIN_DUPLICATE_CHARS:
        return None
    return CodeBlock(
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        content=content,
        normalized_content=normalized,
        content_hash=content_digest(normalized),
        line_count=line_count,
        token_set=set(normalized.split()),
        exact_hash=content_digest(normalize_exact(content)),
    )
