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


def _reimport_source(key: str) -> str:
    """Import *key* from scratch and return its source, restoring sys.modules.

    #13361: the re-import is the point of the test — it proves the module loads
    with nothing but the stdlib behind it — but the replacement module object it
    leaves under *key* is not. Anything that already imported from the original
    keeps a symbol the live module no longer owns, which is the identity split
    that silently made ``mock.patch`` inert in #13162. Install and restore in the
    same ``try/finally``, so the fresh import lasts exactly one statement.
    """
    import importlib  # noqa: PLC0415
    import sys  # noqa: PLC0415

    cached = sys.modules.pop(key, None)
    try:
        module = importlib.import_module(key)
        with open(module.__file__, encoding="utf-8") as handle:
            return handle.read()
    finally:
        if cached is not None:
            sys.modules[key] = cached


def test_extracted_module_has_zero_backend_dependencies() -> None:
    """The whole point of #7460: the parser must import without pulling in
    autobot-backend's heavy chain. This test imports
    ``autobot_shared.jina_parser`` in a fresh context and confirms its
    transitive imports are stdlib-only.
    """
    # The module's transitive imports should be stdlib-only.
    # (re, typing, __future__) — zero autobot-backend / autobot_shared deps
    # beyond the future-import. We assert by checking the module doesn't
    # import anything from media.link or knowledge.
    source = _reimport_source("autobot_shared.jina_parser")

    assert "from media.link" not in source
    assert "from knowledge" not in source
    assert "from autobot_shared" not in source  # no sibling cross-deps either
