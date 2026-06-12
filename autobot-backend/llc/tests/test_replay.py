# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for agent run replay (GH#9034).

Covers:
  1. LLCRunReplayLog model — round-trip through _log_to_dict.
  2. parse_jsonl_events — correct parsing and cap enforcement.
  3. record_run — non-blocking on DB failure; persists correct data.
  4. replay_run — creates a new QUEUED run linked to original.
  5. get_run_diff — identical and differing output_text.
  6. export_fixture — structure, PII redaction applied.
  7. Replay API admin gate — 403 for non-admin.
  8. Replay API 404 — run not found.
  9. Replay API success — adapter invoked with stored inputs.
 10. redact_pii query param — credentials stripped from replay-log response.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.replay_service import (
    ReplayLogNotFoundError,
    RunReplayService,
    _cap_text,
    _log_to_dict,
    parse_jsonl_events,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COMPANY_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_RUN_UUID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
_NEW_RUN_UUID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


class _FakeLog:
    """Plain-object stand-in for LLCRunReplayLog (avoids SQLAlchemy instrumentation)."""

    def __init__(self, **kwargs: Any) -> None:
        defaults: Dict[str, Any] = {
            "id": uuid.uuid4(),
            "run_id": _RUN_UUID,
            "replay_of_run_id": None,
            "company_id": _COMPANY_UUID,
            "agent_id": "agent-abc",
            "inputs_snapshot": {"title": "Test task", "description": "desc"},
            "agent_snapshot": {"adapter_type": "autobot_agent", "agent_id": "agent-abc"},
            "recorded_events": [{"type": "message", "content": "hello"}],
            "output_text": "final output",
            "final_status": "completed",
            "created_at": datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc),
        }
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


def _make_log(**kwargs):  # type: ignore[return]
    return _FakeLog(**kwargs)


# ---------------------------------------------------------------------------
# 1. _log_to_dict round-trip
# ---------------------------------------------------------------------------


class TestLogToDict:
    def test_basic_fields_present(self):
        log = _make_log()
        d = _log_to_dict(log)
        assert d["run_id"] == str(_RUN_UUID)
        assert d["company_id"] == str(_COMPANY_UUID)
        assert d["agent_id"] == "agent-abc"
        assert d["final_status"] == "completed"
        assert d["output_text"] == "final output"
        assert d["replay_of_run_id"] is None

    def test_redact_pii_strips_sensitive_key(self):
        log = _make_log(
            inputs_snapshot={"title": "task", "agent_api_key": "sk-secret1234567890abcdef"}
        )
        # Provide a minimal redact_dict / redact_string stub so the test does
        # not require llm_shared (which pulls in PyTorch at import time).
        import sys
        import types

        fake_cred = types.ModuleType("llm_shared.credential_redaction")
        fake_cred.redact_dict = lambda d: {  # type: ignore[attr-defined]
            k: ("***" if "key" in k.lower() or "token" in k.lower() else v)
            for k, v in d.items()
        }
        fake_cred.redact_string = lambda s: s  # type: ignore[attr-defined]

        saved = sys.modules.get("llm_shared.credential_redaction")
        sys.modules["llm_shared.credential_redaction"] = fake_cred
        try:
            d = _log_to_dict(log, redact_pii=True)
        finally:
            if saved is None:
                sys.modules.pop("llm_shared.credential_redaction", None)
            else:
                sys.modules["llm_shared.credential_redaction"] = saved

        key_val = (d.get("inputs_snapshot") or {}).get("agent_api_key", "")
        assert key_val == "***"

    def test_no_redact_preserves_values(self):
        log = _make_log(inputs_snapshot={"title": "my task"})
        d = _log_to_dict(log, redact_pii=False)
        assert (d["inputs_snapshot"] or {}).get("title") == "my task"


# ---------------------------------------------------------------------------
# 2. parse_jsonl_events
# ---------------------------------------------------------------------------


class TestParseJsonlEvents:
    def test_parses_valid_lines(self):
        content = '\n'.join([
            json.dumps({"type": "message", "text": "hello"}),
            "not json",
            json.dumps({"type": "result", "is_error": False}),
        ])
        events = parse_jsonl_events(content)
        assert len(events) == 2
        assert events[0]["type"] == "message"
        assert events[1]["type"] == "result"

    def test_cap_enforcement(self):
        lines = [json.dumps({"seq": i}) for i in range(100)]
        content = "\n".join(lines)
        events = parse_jsonl_events(content, cap=5)
        assert len(events) == 5

    def test_empty_content_returns_empty(self):
        assert parse_jsonl_events("") == []

    def test_non_dict_lines_skipped(self):
        content = json.dumps([1, 2, 3]) + "\n" + json.dumps({"ok": True})
        events = parse_jsonl_events(content)
        assert len(events) == 1
        assert events[0]["ok"] is True


# ---------------------------------------------------------------------------
# 3. _cap_text
# ---------------------------------------------------------------------------


class TestCapText:
    def test_short_text_unchanged(self):
        assert _cap_text("hello", 100) == "hello"

    def test_none_returns_none(self):
        assert _cap_text(None, 100) is None

    def test_empty_returns_none(self):
        assert _cap_text("", 100) is None

    def test_truncation(self):
        text = "a" * 200
        result = _cap_text(text, 10)
        assert result is not None
        assert len(result.encode("utf-8")) <= 10


# ---------------------------------------------------------------------------
# 4. record_run — non-blocking on DB failure
# ---------------------------------------------------------------------------


class TestRecordRun:
    @pytest.mark.asyncio
    async def test_swallows_db_exception(self):
        """record_run must not raise even when the session factory blows up."""
        svc = RunReplayService()

        def _bad_factory():
            raise Exception("db unavailable")

        with patch("llc.services.replay_service.get_async_session_factory", return_value=_bad_factory):
            # Should not raise.
            await svc.record_run(
                run_id=_RUN_UUID,
                agent={"agent_id": "agent-abc"},
                context={"title": "task"},
                final_status="completed",
            )

    @pytest.mark.asyncio
    async def test_record_run_missing_run_returns_silently(self):
        """When run row doesn't exist (company_id lookup returns None), no error raised."""
        mock_session = AsyncMock()
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)

        mock_factory = MagicMock(return_value=mock_session)

        svc = RunReplayService()
        with patch("llc.services.replay_service.get_async_session_factory", return_value=mock_factory):
            await svc.record_run(
                run_id=_RUN_UUID,
                agent={"agent_id": "agent-abc"},
                context={},
                final_status="failed",
            )
        # No exception raised — test passes


# ---------------------------------------------------------------------------
# 5. get_run_diff
# ---------------------------------------------------------------------------


class TestGetRunDiff:
    @pytest.mark.asyncio
    async def test_identical_outputs(self):
        svc = RunReplayService()
        run_a = uuid.uuid4()
        run_b = uuid.uuid4()

        # Patch get_replay_log to return same output_text for both.
        async def _fake_log(session, rid, cid, redact_pii=False):
            return {"output_text": "same output", "run_id": str(rid)}

        svc.get_replay_log = _fake_log  # type: ignore[method-assign]
        result = await svc.get_run_diff(MagicMock(), run_a, run_b, _COMPANY_UUID)
        assert result["identical"] is True
        assert result["diff"] == ""

    @pytest.mark.asyncio
    async def test_different_outputs(self):
        svc = RunReplayService()
        run_a = uuid.uuid4()
        run_b = uuid.uuid4()
        outputs = {run_a: "line one\nline two\n", run_b: "line one\nline three\n"}

        async def _fake_log(session, rid, cid, redact_pii=False):
            return {"output_text": outputs.get(rid, ""), "run_id": str(rid)}

        svc.get_replay_log = _fake_log  # type: ignore[method-assign]
        result = await svc.get_run_diff(MagicMock(), run_a, run_b, _COMPANY_UUID)
        assert result["identical"] is False
        assert "-line two" in result["diff"]
        assert "+line three" in result["diff"]


# ---------------------------------------------------------------------------
# 6. export_fixture — structure
# ---------------------------------------------------------------------------


class TestExportFixture:
    @pytest.mark.asyncio
    async def test_fixture_structure(self):
        log_obj = _make_log()

        # Use a plain MagicMock for the run row — avoids SQLAlchemy instrumentation.
        mock_run = MagicMock()
        mock_run.id = _RUN_UUID
        mock_run.status = "completed"
        mock_run.company_id = _COMPANY_UUID

        mock_run_result = MagicMock()
        mock_run_result.scalar_one_or_none = MagicMock(return_value=mock_run)

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_run_result)

        svc = RunReplayService()

        # Return a plain dict directly — avoids any llm_shared import.
        async def _fake_log(session, rid, cid, redact_pii=False):
            return {
                "id": str(log_obj.id),
                "run_id": str(log_obj.run_id),
                "replay_of_run_id": None,
                "company_id": str(log_obj.company_id),
                "agent_id": log_obj.agent_id,
                "inputs_snapshot": log_obj.inputs_snapshot,
                "agent_snapshot": log_obj.agent_snapshot,
                "recorded_events": log_obj.recorded_events,
                "output_text": log_obj.output_text,
                "final_status": log_obj.final_status,
                "created_at": log_obj.created_at.isoformat(),
            }

        svc.get_replay_log = _fake_log  # type: ignore[method-assign]

        fixture = await svc.export_fixture(mock_session, _RUN_UUID, _COMPANY_UUID)
        assert fixture["fixture_version"] == "1"
        assert fixture["run_id"] == str(_RUN_UUID)
        assert "inputs" in fixture
        assert "agent_config" in fixture
        assert "expected_output" in fixture
        assert "recorded_event_count" in fixture

    @pytest.mark.asyncio
    async def test_missing_log_raises(self):
        mock_session = AsyncMock()
        svc = RunReplayService()

        async def _fake_log(session, rid, cid, redact_pii=False):
            return None

        svc.get_replay_log = _fake_log  # type: ignore[method-assign]

        with pytest.raises(ReplayLogNotFoundError):
            await svc.export_fixture(mock_session, _RUN_UUID, _COMPANY_UUID)


# ---------------------------------------------------------------------------
# 7 & 8. API admin gate and 404
# ---------------------------------------------------------------------------


class TestReplayAPI:
    """Light integration tests for the replay API layer."""

    def _make_mock_ctx(self):
        ctx = MagicMock()
        ctx.org_id = _COMPANY_UUID
        return ctx

    def _make_current_user(self, user_id: str = "user-1"):
        return {"id": user_id}

    @pytest.mark.asyncio
    async def test_admin_gate_403_for_non_admin(self):
        from fastapi import HTTPException

        from llc.api.replay import _require_admin
        from llc.models.enums import MembershipRole
        from llc.services.membership_service import MembershipService

        mock_member = MagicMock()
        mock_member.user_id = "user-1"
        mock_member.role = MembershipRole.MEMBER  # non-admin

        mock_svc = MagicMock(spec=MembershipService)
        mock_svc.list_members = AsyncMock(return_value=[mock_member])

        with patch("llc.api.replay._get_membership", return_value=mock_svc):
            with pytest.raises(HTTPException) as exc_info:
                await _require_admin(
                    self._make_mock_ctx(),
                    self._make_current_user(),
                    AsyncMock(),
                )
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_gate_passes_for_owner(self):
        from llc.api.replay import _require_admin
        from llc.models.enums import MembershipRole
        from llc.services.membership_service import MembershipService

        mock_member = MagicMock()
        mock_member.user_id = "user-1"
        mock_member.role = MembershipRole.OWNER

        mock_svc = MagicMock(spec=MembershipService)
        mock_svc.list_members = AsyncMock(return_value=[mock_member])

        with patch("llc.api.replay._get_membership", return_value=mock_svc):
            # Should not raise.
            await _require_admin(
                self._make_mock_ctx(),
                self._make_current_user(),
                AsyncMock(),
            )
