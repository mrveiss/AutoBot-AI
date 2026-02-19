# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
A2A Security, Tracing & Capability Tests

Issue #968: Unit tests for the new security cards, distributed tracing,
capability verifier, and updated task manager.
"""

import time
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# SecurityCardSigner tests
# ---------------------------------------------------------------------------


_TEST_SECRET = b"test-secret-for-unit-tests"


class TestSecurityCardSigner:
    """Patch _get_secret at the module level so the module-level _SECRET
    constant does not matter in test environments."""

    def _sample_card(self):
        return {
            "name": "TestAgent",
            "url": "https://example.com/api/a2a",
            "version": "1.0.0",
            "skills": [],
        }

    def test_sign_returns_required_fields(self):
        from a2a.security import SecurityCardSigner

        with patch("a2a.security._get_secret", return_value=_TEST_SECRET):
            signed = SecurityCardSigner.sign(self._sample_card())
        assert "card" in signed
        assert "issued_at" in signed
        assert "signature" in signed

    def test_verify_valid_signature(self):
        from a2a.security import SecurityCardSigner

        with patch("a2a.security._get_secret", return_value=_TEST_SECRET):
            signed = SecurityCardSigner.sign(self._sample_card())
            card = SecurityCardSigner.verify(signed)
        assert card["name"] == "TestAgent"

    def test_verify_tampered_card_raises(self):
        from a2a.security import SecurityCardSigner

        with patch("a2a.security._get_secret", return_value=_TEST_SECRET):
            signed = SecurityCardSigner.sign(self._sample_card())
            signed["card"]["name"] = "EvilAgent"
            with pytest.raises(ValueError, match="Invalid security card signature"):
                SecurityCardSigner.verify(signed)

    def test_verify_tampered_signature_raises(self):
        from a2a.security import SecurityCardSigner

        with patch("a2a.security._get_secret", return_value=_TEST_SECRET):
            signed = SecurityCardSigner.sign(self._sample_card())
            signed["signature"] = "00" * 32
            with pytest.raises(ValueError, match="Invalid security card signature"):
                SecurityCardSigner.verify(signed)

    def test_verify_expired_card_raises(self):
        from a2a.security import SecurityCardSigner

        with patch("a2a.security._get_secret", return_value=_TEST_SECRET):
            with patch("a2a.security.time.time", return_value=time.time() - 7200):
                signed = SecurityCardSigner.sign(self._sample_card())
            with pytest.raises(ValueError, match="expired"):
                SecurityCardSigner.verify(signed)

    def test_verify_missing_fields_raises(self):
        from a2a.security import SecurityCardSigner

        with pytest.raises(ValueError, match="missing field"):
            SecurityCardSigner.verify({"card": {}, "issued_at": 0})

    def test_sign_raises_without_secret(self):
        from a2a.security import SecurityCardSigner

        with patch(
            "a2a.security._get_secret", side_effect=RuntimeError("AUTOBOT_A2A_SECRET")
        ):
            with pytest.raises(RuntimeError, match="AUTOBOT_A2A_SECRET"):
                SecurityCardSigner.sign({})

    def test_roundtrip_with_skills(self):
        from a2a.security import SecurityCardSigner

        card = {
            "name": "AutoBot",
            "skills": [{"id": "chat", "description": "Chat"}],
        }
        with patch("a2a.security._get_secret", return_value=_TEST_SECRET):
            signed = SecurityCardSigner.sign(card)
            result = SecurityCardSigner.verify(signed)
        assert result["skills"][0]["id"] == "chat"


# ---------------------------------------------------------------------------
# TraceContext / tracing tests
# ---------------------------------------------------------------------------


class TestTracing:
    def test_new_trace_id_is_32_hex(self):
        from a2a.tracing import new_trace_id

        tid = new_trace_id()
        assert len(tid) == 32
        int(tid, 16)  # must be valid hex

    def test_extract_caller_agent_header_priority(self):
        from a2a.tracing import extract_caller_id

        cid = extract_caller_id("my-agent", "user123", "1.2.3.4")
        assert cid == "agent:my-agent"

    def test_extract_caller_jwt_sub(self):
        from a2a.tracing import extract_caller_id

        cid = extract_caller_id(None, "user123", "1.2.3.4")
        assert cid == "user:user123"

    def test_extract_caller_ip_fallback(self):
        from a2a.tracing import extract_caller_id

        cid = extract_caller_id(None, None, "1.2.3.4")
        assert cid == "ip:1.2.3.4"

    def test_extract_caller_anonymous(self):
        from a2a.tracing import extract_caller_id

        cid = extract_caller_id(None, None, None)
        assert cid == "anonymous"

    def test_trace_context_record(self):
        from a2a.tracing import TraceContext, new_trace_id

        tc = TraceContext(trace_id=new_trace_id(), caller_id="agent:test")
        tc.record("task.submitted", {"task_id": "abc"})
        tc.record("task.working")
        assert len(tc.events) == 2
        assert tc.events[0].event == "task.submitted"
        assert tc.events[1].event == "task.working"

    def test_trace_context_to_dict(self):
        from a2a.tracing import TraceContext, new_trace_id

        tc = TraceContext(trace_id=new_trace_id(), caller_id="user:alice")
        tc.record("task.submitted")
        d = tc.to_dict()
        assert d["caller_id"] == "user:alice"
        assert len(d["events"]) == 1
        assert "timestamp" in d["events"][0]


# ---------------------------------------------------------------------------
# TaskManager with tracing
# ---------------------------------------------------------------------------


class TestTaskManagerWithTrace:
    def setup_method(self):
        from a2a.task_manager import TaskManager

        self.mgr = TaskManager()

    def test_create_task_assigns_trace(self):
        task = self.mgr.create_task("Hello", caller_id="agent:bot")
        assert task.trace_context is not None
        assert task.trace_context.caller_id == "agent:bot"
        assert len(task.trace_context.trace_id) == 32

    def test_create_task_custom_trace_id(self):
        task = self.mgr.create_task("Hello", trace_id="aabbcc" * 5 + "aa")
        assert task.trace_context.trace_id == "aabbcc" * 5 + "aa"

    def test_state_transitions_recorded_in_trace(self):
        from a2a.types import TaskState

        task = self.mgr.create_task("Test")
        self.mgr.update_state(task.id, TaskState.WORKING)
        self.mgr.update_state(task.id, TaskState.COMPLETED)
        events = [e.event for e in task.trace_context.events]
        assert "task.submitted" in events
        assert "task.state_transition" in events

    def test_cancel_records_trace_event(self):
        task = self.mgr.create_task("Cancel me")
        self.mgr.cancel_task(task.id)
        events = [e.event for e in task.trace_context.events]
        assert "task.cancelled" in events

    def test_get_audit_log(self):
        task = self.mgr.create_task("Audit me", caller_id="user:bob")
        from a2a.types import TaskState

        self.mgr.update_state(task.id, TaskState.WORKING)
        log = self.mgr.get_audit_log(task.id)
        assert isinstance(log, list)
        assert len(log) >= 2

    def test_get_audit_log_missing_task(self):
        assert self.mgr.get_audit_log("nonexistent") is None

    def test_task_to_dict_includes_trace(self):
        task = self.mgr.create_task("Trace dict", caller_id="agent:x")
        d = task.to_dict()
        assert "trace" in d
        assert d["trace"]["callerId"] == "agent:x"
        assert len(d["trace"]["traceId"]) == 32


# ---------------------------------------------------------------------------
# CapabilityVerifier tests
# ---------------------------------------------------------------------------


class TestCapabilityVerifier:
    def test_verify_local_card_no_agent_stack(self):
        """Without the full backend, returns report with warnings (not a crash)."""
        from a2a.capability_verifier import verify_local_card

        report = verify_local_card()
        assert isinstance(report.verified, bool)
        assert isinstance(report.warnings, list)

    def test_report_to_dict(self):
        from a2a.capability_verifier import CapabilityReport

        r = CapabilityReport(
            verified=True,
            claimed_skills=["chat"],
            verified_skills=["chat"],
            unverified_skills=[],
        )
        d = r.to_dict()
        assert d["verified"] is True
        assert d["claimed_skills"] == ["chat"]

    @pytest.mark.asyncio
    async def test_verify_remote_card_http_error(self):
        """Returns unverified report on network error."""
        from a2a.capability_verifier import verify_remote_card

        with patch("a2a.capability_verifier._fetch_and_verify") as mock_fetch:
            from a2a.capability_verifier import CapabilityReport

            mock_fetch.return_value = CapabilityReport(
                verified=False, warnings=["Network error"]
            )
            report = await verify_remote_card("https://unreachable.invalid")
        assert report.verified is False

    @pytest.mark.asyncio
    async def test_verify_remote_card_valid(self):
        """Good card with full skill metadata → verified=True."""
        from a2a.capability_verifier import _check_card_skills

        card_data = {
            "skills": [
                {
                    "id": "chat",
                    "description": "Chat with the agent",
                    "tags": ["hello"],
                    "examples": ["Hi!"],
                }
            ]
        }
        report = _check_card_skills(card_data)
        assert report.verified is True
        assert "chat" in report.verified_skills

    @pytest.mark.asyncio
    async def test_verify_remote_card_missing_metadata(self):
        """Skill missing description + tags → unverified."""
        from a2a.capability_verifier import _check_card_skills

        card_data = {"skills": [{"id": "mystery"}]}
        report = _check_card_skills(card_data)
        assert report.verified is False
        assert "mystery" in report.unverified_skills


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------


class TestRateLimiting:
    def teardown_method(self):
        from api.a2a import _rate_buckets

        _rate_buckets.clear()

    def test_within_limit_passes(self):
        from api.a2a import _check_rate_limit

        for _ in range(5):
            _check_rate_limit("1.2.3.4")  # should not raise

    def test_exceeds_limit_raises(self):
        from api.a2a import _RATE_LIMIT, _check_rate_limit, _rate_buckets
        from fastapi import HTTPException

        now = time.time()
        _rate_buckets["9.9.9.9"] = [now] * _RATE_LIMIT
        with pytest.raises(HTTPException) as exc_info:
            _check_rate_limit("9.9.9.9")
        assert exc_info.value.status_code == 429

    def test_old_entries_expire(self):
        from api.a2a import _RATE_LIMIT, _check_rate_limit, _rate_buckets

        old_time = time.time() - 120  # 2 minutes ago
        _rate_buckets["5.5.5.5"] = [old_time] * _RATE_LIMIT
        _check_rate_limit("5.5.5.5")  # should NOT raise — entries are stale


# ---------------------------------------------------------------------------
# JWT sub extraction tests
# ---------------------------------------------------------------------------


class TestJwtSubExtraction:
    def test_extracts_sub_from_valid_jwt(self):
        import base64
        import json

        from api.a2a import _extract_jwt_sub

        header = base64.urlsafe_b64encode(b'{"alg":"HS256"}').rstrip(b"=").decode()
        payload = (
            base64.urlsafe_b64encode(json.dumps({"sub": "user42"}).encode())
            .rstrip(b"=")
            .decode()
        )
        token = f"Bearer {header}.{payload}.fakesig"
        assert _extract_jwt_sub(token) == "user42"

    def test_returns_none_for_missing_auth(self):
        from api.a2a import _extract_jwt_sub

        assert _extract_jwt_sub(None) is None

    def test_returns_none_for_malformed_token(self):
        from api.a2a import _extract_jwt_sub

        assert _extract_jwt_sub("Bearer not.a.valid.token.at.all") is None
