#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The accept set, the reject set, and the two leaks the old variants had (#18093).

Seven call sites each had their own front-matter regex in four incompatible variants.
These tests pin the union of what they accepted, plus the three behaviours none of them
got right: no carriage return reaching the YAML parser, a body returned verbatim, and a
document that is nothing but front matter treated as valid.
"""

import pathlib
import re

import pytest

from autobot_shared.frontmatter import split_frontmatter, strip_frontmatter

_REPO = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# The accept set — every shape at least one old variant handled
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "label,text,yaml_text,body",
    [
        ("lf", "---\nname: x\ndesc: y\n---\nbody\n", "name: x\ndesc: y", "body\n"),
        ("crlf", "---\r\nname: x\r\ndesc: y\r\n---\r\nbody\r\n", "name: x\ndesc: y", "body\r\n"),
        ("fence trailing spaces", "---  \nname: x\n---  \nbody\n", "name: x", "body\n"),
        ("fence trailing tab", "---\t\nname: x\n---\nbody\n", "name: x", "body\n"),
        ("no trailing newline", "---\nname: x\n---", "name: x", ""),
        ("empty block", "---\n---\nbody\n", "", "body\n"),
        ("no body", "---\nname: x\n---\n", "name: x", ""),
        ("body has its own fence", "---\nname: x\n---\nbody\n---\nmore\n", "name: x", "body\n---\nmore\n"),
    ],
)
def test_accepted_shapes(label: str, text: str, yaml_text: str, body: str) -> None:
    assert split_frontmatter(text) == (yaml_text, body), label


# --------------------------------------------------------------------------- #
# The reject set — returned unchanged so a caller can fall back
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "label,text",
    [
        ("empty string", ""),
        ("plain text", "no front matter here"),
        ("unterminated fence", "---\nname: x\nnever closed\n"),
        ("fence not at the start", "intro\n---\nname: x\n---\n"),
        ("four dashes", "----\nname: x\n----\n"),
        ("indented fence", "  ---\nname: x\n---\n"),
        ("fence with trailing text", "--- yaml\nname: x\n---\n"),
    ],
)
def test_rejected_shapes_return_the_input_unchanged(label: str, text: str) -> None:
    """A reject must not be lossy: callers pass the original straight through."""
    assert split_frontmatter(text) == (None, text), label
    assert strip_frontmatter(text) == text, label


# --------------------------------------------------------------------------- #
# The three things no old variant got right
# --------------------------------------------------------------------------- #


def test_no_carriage_return_reaches_the_yaml() -> None:
    """Every old variant that accepted CRLF leaked the \\r into the captured YAML.

    `yaml.safe_load` then saw a trailing carriage return on the final value, so a key
    compared by equality downstream carried an invisible character.
    """
    yaml_text, _ = split_frontmatter("---\r\nname: x\r\ntools: a,b\r\n---\r\nbody\r\n")
    assert yaml_text is not None
    assert "\r" not in yaml_text


def test_the_body_is_returned_verbatim() -> None:
    """Line endings in the body are the caller's content, not ours to normalise.

    `claude_memory_importer` stores this body as memory text, so rewriting its newlines
    would silently alter stored content.
    """
    _, body = split_frontmatter("---\nname: x\n---\nline1\r\nline2\r\n")
    assert body == "line1\r\nline2\r\n"


def test_a_document_that_is_only_front_matter_is_valid() -> None:
    """`claude_memory_importer`'s pattern required a newline after the closing fence.

    It was the only variant that rejected this, so a memory file with no body raised
    MemoryParseError while the same file parsed fine everywhere else.
    """
    assert split_frontmatter("---\nname: x\n---") == ("name: x", "")
    assert split_frontmatter("---\nname: x\n---\n") == ("name: x", "")


def test_unicode_line_separators_survive_inside_a_value() -> None:
    """`str.splitlines()` would split on U+2028 and cut a value in two.

    The module splits on "\\n" alone for exactly this reason; this test is the pin,
    because the offset arithmetic for the body depends on the split being reversible.

    The separator is written as the `\\u2028` escape, never as the literal character: as
    a raw byte it is invisible in a diff and in most editors, so a formatter or a
    copy-paste that dropped it would leave this test passing while testing nothing.
    """
    text = "---\nname: a\u2028b\n---\nbody\n"
    # Control: the separator really is one str.splitlines() breaks on, so the pin below
    # is testing the hazard it names and not an ordinary character.
    assert len("a\u2028b".splitlines()) == 2, "control: U+2028 must be a splitlines() boundary"
    # noqa SIM905: the split() call IS what is under test here. Ruff wants a list
    # literal, which would delete the call and leave the control checking nothing.
    assert len("a\u2028b".split("\n")) == 1, "control: and must NOT be a split(chr(10)) boundary"  # noqa: SIM905

    yaml_text, body = split_frontmatter(text)
    assert yaml_text == "name: a\u2028b"
    assert body == "body\n"


@pytest.mark.parametrize(
    "text",
    [
        "---\nname: x\n---\nbody\n",
        "---\r\nname: x\r\n---\r\nbody\r\n",
        "no front matter",
        "---\nunterminated\n",
    ],
)
def test_split_is_lossless(text: str) -> None:
    """The returned body is always a suffix of the input, never a rewrite of it."""
    _, body = split_frontmatter(text)
    assert text.endswith(body)


# --------------------------------------------------------------------------- #
# The forks are gone and cannot come back unnoticed
# --------------------------------------------------------------------------- #

_MIGRATED = (
    "autobot-backend/markdown_reference_system.py",
    "autobot-backend/services/specialized_agent_service.py",
    "autobot-backend/skills/generator.py",
    "autobot-backend/skills/sync/base_sync.py",
    "autobot-backend/skills/validator.py",
    "autobot-backend/skills/manifest_parser.py",
    "autobot-backend/knowledge/claude_memory_importer.py",
)

# A fence pattern is `---` inside a regex literal, in any of the four old spellings.
_FENCE_PATTERN_RE = re.compile(r"re\.(?:compile|match|search|sub)\(\s*r?[\"'][^\"']*---")


@pytest.mark.parametrize("relpath", _MIGRATED)
def test_migrated_sites_hold_no_frontmatter_regex(relpath: str) -> None:
    source = (_REPO / relpath).read_text(encoding="utf-8")
    found = _FENCE_PATTERN_RE.findall(source)
    assert not found, f"{relpath} compiles its own front-matter pattern again: {found}"


@pytest.mark.parametrize("relpath", _MIGRATED)
def test_migrated_sites_use_the_canonical(relpath: str) -> None:
    source = (_REPO / relpath).read_text(encoding="utf-8")
    assert "from autobot_shared.frontmatter import" in source, f"{relpath} does not import the canonical parser"
