# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every reader of the legacy transcripts resolves ONE directory, from SSOT config (#18293).

The retired writer put ``data/conversation_transcripts`` under its working directory --
the backend's code directory, which an Ansible install also sets as ``AUTOBOT_BASE_DIR``.
The data-storage view and session-delete cleanup looked under the project root's
``data/`` instead, and the first fix read ``Path.cwd()``, so a script started anywhere
else read an empty directory. The location is now the SSOT setting
``AUTOBOT_LEGACY_TRANSCRIPTS_DIR`` (default ``data/conversation_transcripts`` under
``base_dir``); the old project-root join is the contrast.
"""

from pathlib import Path

import pytest

import api.data_storage as data_storage
from api.data_storage_categories import (
    LEGACY_TRANSCRIPTS_CATEGORY,
    category_dir,
    get_cleanable_categories,
    get_protected_categories,
)
from autobot_shared.ssot_config import PathConfig, config
from autobot_shared.ssot_constants import PATH
from autobot_shared.store_authority import legacy_conversation_transcripts_dir
from chat_history.legacy_transcripts import legacy_transcript_file, read_legacy_transcript_pairs
from chat_history.session import SessionMixin

SESSION = "sess-18293"
_PAYLOAD = '{"messages": [{"user": "q", "assistant": "a"}]}'


def _write(directory: Path, session_id: str = SESSION) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.json"
    path.write_text(_PAYLOAD, encoding="utf-8")
    return path


@pytest.fixture
def legacy_dir(tmp_path, monkeypatch) -> Path:
    """Point the SSOT setting at a temp directory -- the one thing every reader must follow."""
    directory = (tmp_path / "backend" / "data" / "conversation_transcripts").resolve()
    monkeypatch.setattr(config.path, "legacy_transcripts_dir", str(directory))
    return directory


def test_the_default_is_the_writers_path_under_base_dir(monkeypatch) -> None:
    monkeypatch.delenv("AUTOBOT_LEGACY_TRANSCRIPTS_DIR", raising=False)
    path_config = PathConfig(_env_file=None, AUTOBOT_BASE_DIR="/srv/backend")
    assert path_config.legacy_transcripts_dir == "data/conversation_transcripts"
    assert path_config.resolve(path_config.legacy_transcripts_dir) == Path("/srv/backend/data/conversation_transcripts")


def test_the_environment_overrides_the_default(monkeypatch) -> None:
    monkeypatch.setenv("AUTOBOT_LEGACY_TRANSCRIPTS_DIR", "/srv/elsewhere/legacy")
    assert PathConfig(_env_file=None).legacy_transcripts_dir == "/srv/elsewhere/legacy"


def test_the_working_directory_does_not_move_it(legacy_dir, tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    first = legacy_conversation_transcripts_dir()
    monkeypatch.chdir(Path(__file__).parent)
    assert legacy_conversation_transcripts_dir() == first == legacy_dir


def test_every_reader_resolves_the_same_directory(legacy_dir) -> None:
    assert category_dir(data_storage.DATA_DIR, LEGACY_TRANSCRIPTS_CATEGORY) == legacy_dir
    assert data_storage._safe_data_path(LEGACY_TRANSCRIPTS_CATEGORY) == legacy_dir
    assert legacy_transcript_file(SESSION) is None
    assert legacy_transcript_file(_write(legacy_dir).stem) == legacy_dir / f"{SESSION}.json"


def test_the_old_project_root_resolution_is_a_different_directory(legacy_dir) -> None:
    """Contrast: what data_storage and delete-cleanup joined before #18293."""
    assert (data_storage.DATA_DIR / "conversation_transcripts").resolve() != legacy_dir
    assert (PATH.DATA_DIR / "conversation_transcripts").resolve() != legacy_dir


@pytest.mark.asyncio
async def test_the_legacy_reader_reads_the_configured_directory(legacy_dir) -> None:
    _write(legacy_dir)
    assert await read_legacy_transcript_pairs(SESSION) == [{"user": "q", "assistant": "a"}]
    assert await read_legacy_transcript_pairs("../escape") == []


def test_the_legacy_category_is_protected_from_bulk_cleanup() -> None:
    protected = {c["path"] for c in get_protected_categories()}
    cleanable = {c["path"] for c in get_cleanable_categories()}
    assert LEGACY_TRANSCRIPTS_CATEGORY in protected and LEGACY_TRANSCRIPTS_CATEGORY not in cleanable


@pytest.mark.asyncio
async def test_session_delete_clears_the_llm_context_cache_too() -> None:
    from unittest.mock import MagicMock

    mixin = SessionMixin.__new__(SessionMixin)
    mixin.redis_client = MagicMock()

    await mixin._clear_session_redis_cache(SESSION)

    mixin.redis_client.delete.assert_called_once_with(f"chat:session:{SESSION}", f"chat:conversation:{SESSION}")


@pytest.mark.asyncio
async def test_admin_conversation_delete_refuses_a_legacy_transcript(legacy_dir) -> None:
    """Protected like its bulk category: disposal goes through the #17038 queue only."""
    from fastapi import HTTPException

    transcript = _write(legacy_dir)

    with pytest.raises(HTTPException) as raised:
        await data_storage.delete_conversation.__wrapped__(SESSION, None)

    assert raised.value.status_code == 403
    assert transcript.exists()


@pytest.mark.parametrize(
    "session_id",
    ["../escape", "a/b", "a\\b", "", "x" * 256, "name with space", "nul\x00byte", "dot.json", "~root"],
)
def test_an_id_outside_the_store_alphabet_never_names_a_file(legacy_dir, session_id) -> None:
    """Allowlist fullmatch before the join, normpath containment after it (CodeQL py/path-injection)."""
    _write(legacy_dir)
    assert legacy_transcript_file(session_id) is None


def test_every_id_shape_the_store_accepts_still_resolves(legacy_dir) -> None:
    for session_id in ("5f0c9a5e-1b2c-4d3e-8f90-0a1b2c3d4e5f", "session_12", "test-session-ab_1", "x" * 200):
        assert legacy_transcript_file(_write(legacy_dir, session_id).stem) == legacy_dir / f"{session_id}.json"
