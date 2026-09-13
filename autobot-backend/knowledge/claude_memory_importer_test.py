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
    ParsedMemory,
    _fact_metadata,
    fact_id_for,
    get_claude_memory_dir,
    import_claude_memory,
    import_memory_file,
    iter_memory_files,
    parse_memory_file,
)
from knowledge.ownership import KnowledgeOwnership

_OWNER = "admin-test-user"

_VALID_MEMORY = """---
name: feedback-example
description: An example feedback memory for tests.
metadata:
  type: feedback
---

Always do the thing.

**Why:** because tests need a why line.
"""

# #16642 security review fixtures — real detector-shaped values, never a
# genuine secret. Assembled at runtime (not a literal in this file) so
# static secret scanners don't flag the fixture itself; the pii_pipeline's
# AWS_ACCESS_KEY detector (BLOCK-tier) still matches it at test time. The
# email fixture exercises the EMAIL detector (REDACT-tier, not blocked).
_FAKE_AWS_KEY = "AKIA" + "ABCDEFGHIJKLMNOP"

_MEMORY_WITH_SECRET = f"""---
name: leaky-example
description: A memory that accidentally captured a credential.
metadata:
  type: project
---

Ran with {_FAKE_AWS_KEY} and it worked.
"""

_MEMORY_WITH_EMAIL = """---
name: contact-example
description: A memory that mentions an email address.
metadata:
  type: reference
---

Ping alice@example.com if this breaks.
"""

_MEMORY_WITH_PRIVATE_IP = """---
name: private-ip-example
description: A memory that mentions an internal IP.
metadata:
  type: project
---

The staging box is at 10.0.0.5.
"""

_MEMORY_WITH_INTERNAL_HOSTNAME = """---
name: internal-hostname-example
description: A memory that mentions an internal hostname.
metadata:
  type: project
---

Deployed to db1.internal for testing.
"""

# Built from disjoint pieces, never a contiguous literal in this file, so
# static secret scanners don't flag the fixture itself (same reasoning as
# _FAKE_AWS_KEY above) — the pii_pipeline's API_KEY assignment detector
# (BLOCK-tier) still matches the assembled line at test time.
_FAKE_API_KEY_VALUE = "abcdefghijklmnopqrst" + "uvwxyz012345"
_CRED_ASSIGNMENT_LINE = "api" + "_key" + " = " + '"' + _FAKE_API_KEY_VALUE + '"'

_MEMORY_WITH_CREDENTIAL_ASSIGNMENT = (
    "---\n"
    "name: credential-assignment-example\n"
    "description: A memory that captured a credential assignment.\n"
    "metadata:\n"
    "  type: project\n"
    "---\n\n"
    "Config had " + _CRED_ASSIGNMENT_LINE + " hardcoded.\n"
)

_MEMORY_WITH_SSH_TARGET = """---
name: ssh-target-example
description: A memory that mentions an ssh command target.
metadata:
  type: project
---

Debugged by running ssh martins@fileserver01 to check the logs.
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

    action = await import_memory_file(kb, path, _OWNER)

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

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "updated"
    kb.update_fact.assert_awaited_once()
    kb.store_fact.assert_not_awaited()
    args, kwargs = kb.update_fact.call_args
    assert args[0] == "claude_code_memory:feedback-example"
    assert kwargs["content"].startswith("An example feedback memory for tests.")


async def test_import_memory_file_reports_duplicate_without_raising(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    kb = _make_kb(get_fact_return=None, store_status="duplicate")

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "duplicate"


async def test_import_memory_file_raises_on_write_failure(tmp_path):
    path = _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    kb = _make_kb(get_fact_return=None, store_status="error")

    with pytest.raises(MemoryWriteError):
        await import_memory_file(kb, path, _OWNER)


# ---------------------------------------------------------------------------
# import_claude_memory — aggregate outcome over a directory
# ---------------------------------------------------------------------------


async def test_import_claude_memory_aggregates_and_skips_bad_files(tmp_path):
    _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    _write(tmp_path, "broken.md", "no frontmatter here")
    _write(tmp_path, "MEMORY.md", "# index")
    kb = _make_kb(get_fact_return=None)

    result = await import_claude_memory(kb, tmp_path, _OWNER)

    assert result.created == 1
    assert result.updated == 0
    assert result.failed == 1
    assert "broken.md" in result.errors


async def test_import_claude_memory_is_idempotent_on_rerun(tmp_path):
    _write(tmp_path, "feedback_example.md", _VALID_MEMORY)

    kb_first = _make_kb(get_fact_return=None)
    first = await import_claude_memory(kb_first, tmp_path, _OWNER)
    assert first.created == 1

    kb_second = _make_kb(get_fact_return={"fact_id": "claude_code_memory:feedback-example"})
    second = await import_claude_memory(kb_second, tmp_path, _OWNER)
    assert second.created == 0
    assert second.updated == 1


# ---------------------------------------------------------------------------
# #16642 security review — redaction at import
# ---------------------------------------------------------------------------


async def test_import_memory_file_blocks_on_credential_shaped_content(tmp_path):
    path = _write(tmp_path, "leaky_example.md", _MEMORY_WITH_SECRET)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "blocked"
    kb.store_fact.assert_not_called()
    kb.update_fact.assert_not_called()


async def test_import_memory_file_redacts_low_severity_hits_and_still_imports(tmp_path):
    path = _write(tmp_path, "contact_example.md", _MEMORY_WITH_EMAIL)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "created"
    args, _ = kb.store_fact.call_args
    assert "alice@example.com" not in args[0]
    assert "[REDACTED:EMAIL]" in args[0]


async def test_import_claude_memory_counts_blocked_separately_from_failed(tmp_path):
    _write(tmp_path, "feedback_example.md", _VALID_MEMORY)
    _write(tmp_path, "leaky_example.md", _MEMORY_WITH_SECRET)
    kb = _make_kb(get_fact_return=None)

    result = await import_claude_memory(kb, tmp_path, _OWNER)

    assert result.created == 1
    assert result.blocked == 1
    assert result.failed == 0


async def test_import_memory_file_redacts_private_ip(tmp_path):
    path = _write(tmp_path, "private_ip_example.md", _MEMORY_WITH_PRIVATE_IP)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "created"
    args, _ = kb.store_fact.call_args
    assert "10.0.0.5" not in args[0]
    assert "[REDACTED:PRIVATE_IP]" in args[0]


async def test_import_memory_file_redacts_internal_hostname(tmp_path):
    path = _write(tmp_path, "internal_hostname_example.md", _MEMORY_WITH_INTERNAL_HOSTNAME)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "created"
    args, _ = kb.store_fact.call_args
    assert "db1.internal" not in args[0]
    assert "[REDACTED:INTERNAL_HOSTNAME]" in args[0]


async def test_import_memory_file_blocks_credential_assignment(tmp_path):
    path = _write(tmp_path, "credential_assignment_example.md", _MEMORY_WITH_CREDENTIAL_ASSIGNMENT)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "blocked"
    kb.store_fact.assert_not_called()


async def test_import_memory_file_redacts_ssh_command_target(tmp_path):
    """#16642 security review follow-up: a2a.pii_pipeline's INTERNAL_HOSTNAME
    detector only matches known suffixes — a bare ssh command target like
    ``ssh user@host`` needs the importer-local addition in _redact()."""
    path = _write(tmp_path, "ssh_target_example.md", _MEMORY_WITH_SSH_TARGET)
    kb = _make_kb(get_fact_return=None)

    action = await import_memory_file(kb, path, _OWNER)

    assert action == "created"
    args, _ = kb.store_fact.call_args
    assert "martins@fileserver01" not in args[0]
    assert "[REDACTED:SSH_TARGET]" in args[0]


# ---------------------------------------------------------------------------
# #16642 security review — owner/visibility metadata and its enforcement
# ---------------------------------------------------------------------------


def _sample_memory() -> ParsedMemory:
    return ParsedMemory(
        slug="feedback-example",
        description="An example.",
        memory_type="feedback",
        body="Body text.",
        source_file="feedback_example.md",
    )


def test_fact_metadata_sets_owner_and_private_system_visibility():
    metadata = _fact_metadata(_sample_memory(), _OWNER)

    assert metadata["owner_id"] == _OWNER
    assert metadata["visibility"] == "private"
    assert metadata["access_level"] == "system"


async def test_imported_fact_metadata_is_honoured_by_ownership_check_access():
    """Proves the metadata this importer sets is actually respected by the
    existing enforcement primitive (knowledge.ownership.KnowledgeOwnership),
    not just present — #16642 security review High finding.
    """
    metadata = _fact_metadata(_sample_memory(), _OWNER)
    ownership = KnowledgeOwnership(redis_client=MagicMock())

    owner_can_read = await ownership.check_access(
        fact_id="claude_code_memory:feedback-example",
        user_id=_OWNER,
        fact_metadata=metadata,
        is_authenticated=True,
    )
    other_authenticated_user_denied = await ownership.check_access(
        fact_id="claude_code_memory:feedback-example",
        user_id="someone-else",
        fact_metadata=metadata,
        is_authenticated=True,
    )
    unauthenticated_denied = await ownership.check_access(
        fact_id="claude_code_memory:feedback-example",
        user_id="anon",
        fact_metadata=metadata,
        is_authenticated=False,
    )

    assert owner_can_read is True
    assert other_authenticated_user_denied is False
    assert unauthenticated_denied is False
