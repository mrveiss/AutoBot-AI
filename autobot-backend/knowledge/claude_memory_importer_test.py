# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for claude_memory_importer (#16642).

Covers frontmatter parsing and the idempotent upsert decision (create vs.
update vs. duplicate) against a mocked knowledge_facts write path.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from knowledge.claude_memory_importer import (
    MemoryParseError,
    MemoryWriteError,
    fact_id_for,
    get_claude_memory_dir,
    import_claude_memory,
    import_memory_file,
    iter_memory_files,
    parse_memory_file,
)

_VALID_MEMORY = """---
name: feedback-example
description: An example feedback memory for tests.
metadata:
  type: feedback
---

Always do the thing.

**Why:** because tests need a why line.
"""


def _write(tmp_path, name: str, content: str):
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# get_claude_memory_dir — env override vs. computed default
# ---------------------------------------------------------------------------


def test_get_claude_memory_dir_honours_env_override(monkeypatch):
    monkeypatch.setenv("AUTOBOT_CLAUDE_MEMORY_DIR", "/tmp/some-override")

    assert get_claude_memory_dir() == Path("/tmp/some-override")


def test_get_claude_memory_dir_default_is_under_claude_projects(monkeypatch):
    monkeypatch.delenv("AUTOBOT_CLAUDE_MEMORY_DIR", raising=False)

    result = get_claude_memory_dir()

    assert result.name == "memory"
    assert ".claude/projects" in str(result)


# ---------------------------------------------------------------------------
# parse_memory_file
# ---------------------------------------------------------------------------


def test_parse_memory_file_extracts_frontmatter_and_body(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)

    memory = parse_memory_file(path)

    assert memory.slug == "feedback-example"
    assert memory.description == "An example feedback memory for tests."
    assert memory.memory_type == "feedback"
    assert "Always do the thing." in memory.body
    assert memory.source_file == "feedback_example.md"


def test_parse_memory_file_raises_without_frontmatter(tmp_path):
    path = _write(tmp_path, "plain.md", "Just a paragraph, no frontmatter.")

    with pytest.raises(MemoryParseError):
        parse_memory_file(path)


def test_parse_memory_file_raises_without_name(tmp_path):
    content = """---
description: Missing a name field.
metadata:
  type: project
---

Body text.
"""
    path = _write(tmp_path, "no_name.md", content)

    with pytest.raises(MemoryParseError):
        parse_memory_file(path)


def test_parse_memory_file_defaults_missing_type_to_unknown(tmp_path):
    content = """---
name: no-type
description: No metadata.type given.
---

Body text.
"""
    path = _write(tmp_path, "no_type.md", content)

    memory = parse_memory_file(path)

    assert memory.memory_type == "unknown"


# ---------------------------------------------------------------------------
# iter_memory_files
# ---------------------------------------------------------------------------


def test_iter_memory_files_excludes_index(tmp_path):
    _write(tmp_path, "MEMORY.md", "# index, not a memory")
    real = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)

    found = list(iter_memory_files(tmp_path))

    assert found == [real]


def test_iter_memory_files_on_missing_dir_yields_nothing(tmp_path):
    missing = tmp_path / "does_not_exist"

    assert list(iter_memory_files(missing)) == []


# ---------------------------------------------------------------------------
# fact_id_for — deterministic id is what makes re-import idempotent
# ---------------------------------------------------------------------------


def test_fact_id_for_is_deterministic_and_namespaced():
    assert fact_id_for("feedback-example") == "claude_code_memory:feedback-example"
    assert fact_id_for("feedback-example") == fact_id_for("feedback-example")


# ---------------------------------------------------------------------------
# import_memory_file — create / update / duplicate / error branches
# ---------------------------------------------------------------------------


def _make_kb(get_fact_return=None, store_status="success", update_status="success"):
    kb = MagicMock()
    kb.get_fact = MagicMock(return_value=get_fact_return)
    kb.store_fact = AsyncMock(return_value={"status": store_status, "fact_id": "x", "message": "m"})
    kb.update_fact = AsyncMock(return_value={"status": update_status, "fact_id": "x", "message": "m"})
    return kb


async def test_import_memory_file_creates_when_fact_absent(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path)

    assert action == "created"
    kb.store_fact.assert_awaited_once()
    kb.update_fact.assert_not_called()
    _, kwargs = kb.store_fact.call_args
    assert kwargs["fact_id"] == "claude_code_memory:feedback-example"
    assert kwargs["metadata"]["category"] == "claude_code_memory"
    assert kwargs["metadata"]["memory_type"] == "feedback"


async def test_import_memory_file_updates_when_fact_present(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    kb = _make_kb(get_fact_return={"fact_id": "claude_code_memory:feedback-example"})

    action = await import_memory_file(kb, path)

    assert action == "updated"
    kb.update_fact.assert_awaited_once()
    kb.store_fact.assert_not_awaited()
    args, kwargs = kb.update_fact.call_args
    assert args[0] == "claude_code_memory:feedback-example"
    assert kwargs["content"].startswith("An example feedback memory for tests.")


async def test_import_memory_file_reports_duplicate_without_raising(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    kb = _make_kb(get_fact_return=None, store_status="duplicate")

    action = await import_memory_file(kb, path)

    assert action == "duplicate"


async def test_import_memory_file_raises_on_write_failure(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    kb = _make_kb(get_fact_return=None, store_status="error")

    with pytest.raises(MemoryWriteError):
        await import_memory_file(kb, path)


# ---------------------------------------------------------------------------
# import_claude_memory — aggregate outcome over a directory
# ---------------------------------------------------------------------------


async def test_import_claude_memory_aggregates_and_skips_bad_files(tmp_path):
    _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    _write(tmp_path, "broken.md", "no frontmatter here")
    _write(tmp_path, "MEMORY.md", "# index")
    kb = _make_kb(get_fact_return=None)

    result = await import_claude_memory(kb, tmp_path)

    assert result.created == 1
    assert result.updated == 0
    assert result.failed == 1
    assert "broken.md" in result.errors


async def test_import_claude_memory_is_idempotent_on_rerun(tmp_path):
    _write(tmp_path, "feedback_example.md", _VALID_MEMORY)

    kb_first = _make_kb(get_fact_return=None)
    first = await import_claude_memory(kb_first, tmp_path)
    assert first.created == 1

    kb_second = _make_kb(get_fact_return={"fact_id": "claude_code_memory:feedback-example"})
    second = await import_claude_memory(kb_second, tmp_path)
    assert second.created == 0
    assert second.updated == 1
