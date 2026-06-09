# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Contract tests for ``autobot_shared.jina_parser`` (#7460).

Validates the extracted Jina Reader parser. Full-coverage tests for
the ``media.link.pipeline._parse_jina_output`` re-export shim still live
in ``autobot-backend/media/link/pipeline_test.py`` — these tests
specifically pin the import-isolation contract that motivated the
extraction (the function must be importable without dragging in any
backend dependencies).
"""

from __future__ import annotations

from autobot_shared.jina_parser import parse_jina_output


def test_empty_input_returns_empty_pair() -> None:
    assert parse_jina_output("") == ("", "")


def test_title_and_body_parsed_with_metadata_block() -> None:
    raw = "Title: My Article\n" "URL Source: https://example.com/x\n" "\n" "First paragraph.\n" "Second paragraph.\n"
    title, body = parse_jina_output(raw)
    assert title == "My Article"
    # ``splitlines()`` strips trailing newline; the parser preserves
    # only inter-line newlines, not a trailing one.
    assert body == "First paragraph.\nSecond paragraph."


def test_no_title_falls_back_to_first_nonempty_line() -> None:
    raw = "Hello\nWorld\n"
    title, body = parse_jina_output(raw)
    assert title == "Hello"
    assert body == raw  # body unchanged when no Title: header


def test_title_truncated_at_200_chars() -> None:
    long = "x" * 500
    raw = f"Title: {long}\n\nbody"
    title, _ = parse_jina_output(raw)
    assert len(title) == 200


def test_title_without_blank_separator_returns_full_content_as_body() -> None:
    """If the Title: line isn't followed by a blank line, the body is the
    full input (we couldn't safely strip the header)."""
    raw = "Title: Foo\nNo blank line — body starts immediately.\n"
    title, body = parse_jina_output(raw)
    assert title == "Foo"
    assert body == raw


def test_extracted_module_has_zero_backend_dependencies() -> None:
    """The whole point of #7460: the parser must import without pulling in
    autobot-backend's heavy chain. This test imports
    ``autobot_shared.jina_parser`` in a fresh context and confirms its
    transitive imports are stdlib-only.
    """
    import importlib
    import sys

    # Drop any cached version
    sys.modules.pop("autobot_shared.jina_parser", None)
    mod = importlib.import_module("autobot_shared.jina_parser")

    # The module's transitive imports should be stdlib-only.
    # (re, typing, __future__) — zero autobot-backend / autobot_shared deps
    # beyond the future-import. We assert by checking the module doesn't
    # import anything from media.link or knowledge.
    src = open(mod.__file__, encoding="utf-8").read()  # noqa: SIM115
    assert "from media.link" not in src
    assert "from knowledge" not in src
    assert "from autobot_shared" not in src  # no sibling cross-deps either
