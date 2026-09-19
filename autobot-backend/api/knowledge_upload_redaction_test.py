# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#13708: the manual "upload a file to the KB" endpoint had its own separate
extraction path (media.document.extraction, not
knowledge/connectors/content_extraction.py's already-redacted wrappers) and
never went through the credential redactor at all.

Drives the real ``upload_file_to_knowledge`` endpoint function end-to-end
(only the KB store and auth are mocked -- ``_extract_file_content`` and
``redact_content`` both run for real), so this proves the redaction step is
reachable through the actual endpoint, not just through the isolated
extraction wrapper functions a prior review found the earlier tests were
calling directly instead.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

_SECRET = "sk-" + "abcdefghijklmnopqrstuvwxyz123456"


@pytest.mark.asyncio
async def test_uploaded_text_file_is_redacted_before_it_reaches_the_kb():
    from api import knowledge as mod

    body = f"Setup instructions: your API key is {_SECRET} -- keep it private.".encode("utf-8")
    upload = SimpleNamespace(filename="setup.txt", read=AsyncMock(return_value=body))
    req = MagicMock()
    req.form = AsyncMock(return_value={"file": upload, "title": "Setup"})
    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "f1"})

    with (
        patch.object(mod, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(mod, "get_auth_middleware", MagicMock()),
        patch.object(mod, "audit_record", MagicMock()),
    ):
        await mod.upload_file_to_knowledge(admin_check=True, req=req)

    stored_content = kb.store_fact.await_args.kwargs["content"]
    assert _SECRET not in stored_content, "credential reached the KB store unredacted"
    assert "Setup instructions" in stored_content


@pytest.mark.asyncio
async def test_uploaded_text_file_with_no_secret_is_unchanged():
    """Negative control: an ordinary upload must not be mangled by the redaction pass."""
    from api import knowledge as mod

    body = b"Team meeting notes: standup is at 10am, retro is on Friday."
    upload = SimpleNamespace(filename="notes.txt", read=AsyncMock(return_value=body))
    req = MagicMock()
    req.form = AsyncMock(return_value={"file": upload, "title": "Notes"})
    kb = MagicMock()
    kb.store_fact = AsyncMock(return_value={"fact_id": "f1"})

    with (
        patch.object(mod, "get_or_create_knowledge_base", AsyncMock(return_value=kb)),
        patch.object(mod, "get_auth_middleware", MagicMock()),
        patch.object(mod, "audit_record", MagicMock()),
    ):
        await mod.upload_file_to_knowledge(admin_check=True, req=req)

    stored_content = kb.store_fact.await_args.kwargs["content"]
    assert "Team meeting notes" in stored_content
    assert "standup is at 10am" in stored_content
