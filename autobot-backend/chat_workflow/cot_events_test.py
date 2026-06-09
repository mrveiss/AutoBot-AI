# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for Issue #3232 — Chain-of-Thought event emission with causal context.

Tests verify:
1. CausalLink dataclass creation and serialization
2. All emit_* functions accept optional causal_chain parameter
3. Causal chain is preserved in event payloads (when provided)
4. Causal chain is omitted from payload when None (backward compatible)
5. Sensitive data in causal reasons is redacted
6. build_causal_chain helper constructs chains correctly
7. Events without causal context still emit normally (existing behavior)
"""

# Import only the module under test (cot_events.py is pure Python with minimal deps)
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

# Load cot_events.py directly without triggering the full backend import chain
cot_events_path = Path(__file__).parent / "cot_events.py"
spec = importlib.util.spec_from_file_location("cot_events", cot_events_path)
cot_events = importlib.util.module_from_spec(spec)
sys.modules["cot_events"] = cot_events
try:
    spec.loader.exec_module(cot_events)
except Exception as exc:
    raise RuntimeError(f"Failed to load cot_events module: {exc}") from exc

CausalLink = cot_events.CausalLink
build_causal_chain = cot_events.build_causal_chain
emit_llm_chunk = cot_events.emit_llm_chunk
emit_plan = cot_events.emit_plan
emit_step_complete = cot_events.emit_step_complete
emit_step_start = cot_events.emit_step_start
emit_tool_call = cot_events.emit_tool_call
emit_tool_result = cot_events.emit_tool_result


class TestCausalLink:
    """Tests for CausalLink dataclass."""

    def test_causal_link_creation(self):
        """CausalLink can be created with required fields."""
        link = CausalLink(
            source_event_id="step-1",
            target_event_id="tool-call-2",
            reason="security_check_failed",
        )
        assert link.source_event_id == "step-1"
        assert link.target_event_id == "tool-call-2"
        assert link.reason == "security_check_failed"

    def test_causal_link_to_dict(self):
        """CausalLink.to_dict() returns proper dict structure."""
        link = CausalLink(
            source_event_id="check-1",
            target_event_id="action-2",
            reason="timeout_detected",
        )
        result = link.to_dict()
        assert result["source_event_id"] == "check-1"
        assert result["target_event_id"] == "action-2"
        assert result["reason"] == "timeout_detected"
        assert isinstance(result, dict)

    def test_causal_link_redacts_sensitive_reason(self):
        """CausalLink.to_dict() redacts sensitive patterns in reason."""
        link = CausalLink(
            source_event_id="step-1",
            target_event_id="step-2",
            reason="api_key_validation_failed",  # Contains "key"
        )
        result = link.to_dict()
        # Reason should be redacted because it contains sensitive fragment
        assert result["reason"] == "<redacted>"

    def test_causal_link_redacts_token_in_reason(self):
        """CausalLink.to_dict() redacts 'token' in reason."""
        link = CausalLink(
            source_event_id="auth-1",
            target_event_id="auth-2",
            reason="bearer_token_expired",
        )
        result = link.to_dict()
        assert result["reason"] == "<redacted>"

    def test_causal_link_redacts_password_in_reason(self):
        """CausalLink.to_dict() redacts 'password' in reason."""
        link = CausalLink(
            source_event_id="auth-1",
            target_event_id="auth-2",
            reason="password_reset_required",
        )
        result = link.to_dict()
        assert result["reason"] == "<redacted>"

    def test_causal_link_preserves_non_sensitive_reason(self):
        """CausalLink.to_dict() preserves non-sensitive reasons."""
        link = CausalLink(
            source_event_id="step-1",
            target_event_id="step-2",
            reason="retry_limit_exceeded",
        )
        result = link.to_dict()
        assert result["reason"] == "retry_limit_exceeded"

    def test_causal_link_preserves_complex_reason(self):
        """CausalLink.to_dict() preserves complex non-sensitive reasons."""
        reason = "detected_loop_in_graph_execution_with_max_depth_100"
        link = CausalLink(
            source_event_id="check-1",
            target_event_id="halt-2",
            reason=reason,
        )
        result = link.to_dict()
        assert result["reason"] == reason


class TestBuildCausalChain:
    """Tests for build_causal_chain helper function."""

    def test_build_from_empty_list_returns_none(self):
        """build_causal_chain with empty list returns None."""
        result = build_causal_chain([])
        assert result is None

    def test_build_from_none_returns_none(self):
        """build_causal_chain with None returns None."""
        result = build_causal_chain(None)
        assert result is None

    def test_build_single_link(self):
        """build_causal_chain constructs single link correctly."""
        result = build_causal_chain(
            [
                ("event-1", "event-2", "reason_x"),
            ]
        )
        assert result is not None
        assert len(result) == 1
        assert result[0].source_event_id == "event-1"
        assert result[0].target_event_id == "event-2"
        assert result[0].reason == "reason_x"

    def test_build_multiple_links(self):
        """build_causal_chain constructs multiple links correctly."""
        result = build_causal_chain(
            [
                ("event-1", "event-2", "reason_a"),
                ("event-2", "event-3", "reason_b"),
                ("event-3", "event-4", "reason_c"),
            ]
        )
        assert result is not None
        assert len(result) == 3
        assert result[0].source_event_id == "event-1"
        assert result[1].source_event_id == "event-2"
        assert result[2].source_event_id == "event-3"

    def test_build_chain_with_mixed_sensitive_reasons(self):
        """build_causal_chain handles mix of sensitive and non-sensitive reasons."""
        result = build_causal_chain(
            [
                ("a", "b", "normal_reason"),
                ("b", "c", "token_validation_failed"),
                ("c", "d", "another_normal_reason"),
            ]
        )
        assert result is not None
        assert len(result) == 3
        # Verify that sensitive reason is in the object (redaction happens at .to_dict())
        assert result[1].reason == "token_validation_failed"
        # After serialization, it should be redacted
        serialized = result[1].to_dict()
        assert serialized["reason"] == "<redacted>"


class TestEmitFunctionSignatures:
    """Tests verifying that all emit_* functions accept causal_chain parameter."""

    def test_emit_step_start_accepts_causal_chain(self):
        """emit_step_start accepts causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            # Should not raise about unexpected parameter
            chain = build_causal_chain([("a", "b", "reason")])
            emit_step_start(
                step_name="test",
                causal_chain=chain,
            )

    def test_emit_step_complete_accepts_causal_chain(self):
        """emit_step_complete accepts causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            chain = build_causal_chain([("a", "b", "reason")])
            emit_step_complete(
                step_name="test",
                start_time=1000.0,
                causal_chain=chain,
            )

    def test_emit_tool_call_accepts_causal_chain(self):
        """emit_tool_call accepts causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            chain = build_causal_chain([("a", "b", "reason")])
            emit_tool_call(
                tool_name="test",
                arguments={},
                causal_chain=chain,
            )

    def test_emit_tool_result_accepts_causal_chain(self):
        """emit_tool_result accepts causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            chain = build_causal_chain([("a", "b", "reason")])
            emit_tool_result(
                tool_name="test",
                result="ok",
                start_time=1000.0,
                causal_chain=chain,
            )

    def test_emit_llm_chunk_accepts_causal_chain(self):
        """emit_llm_chunk accepts causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            chain = build_causal_chain([("a", "b", "reason")])
            emit_llm_chunk(chunk="text", causal_chain=chain)

    def test_emit_plan_accepts_causal_chain(self):
        """emit_plan accepts causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            chain = build_causal_chain([("a", "b", "reason")])
            emit_plan(steps=["step1"], causal_chain=chain)


class TestBackwardCompatibility:
    """Tests verifying backward compatibility (existing code still works)."""

    def test_emit_step_start_without_causal_chain(self):
        """emit_step_start works without causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            result = emit_step_start(step_name="test")
            assert isinstance(result, float)

    def test_emit_step_complete_without_causal_chain(self):
        """emit_step_complete works without causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            emit_step_complete(step_name="test", start_time=1000.0)
            # Should not raise

    def test_emit_tool_call_without_causal_chain(self):
        """emit_tool_call works without causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            result = emit_tool_call(tool_name="test", arguments={})
            assert isinstance(result, float)

    def test_emit_tool_result_without_causal_chain(self):
        """emit_tool_result works without causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            emit_tool_result(tool_name="test", result="ok", start_time=1000.0)
            # Should not raise

    def test_emit_llm_chunk_without_causal_chain(self):
        """emit_llm_chunk works without causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            emit_llm_chunk(chunk="text")
            # Should not raise

    def test_emit_plan_without_causal_chain(self):
        """emit_plan works without causal_chain parameter."""
        with patch("asyncio.get_running_loop", side_effect=RuntimeError):
            emit_plan(steps=["step1", "step2"])
            # Should not raise


class TestCausalChainInPayloads:
    """Tests for causal chain inclusion in event payloads."""

    def test_none_causal_chain_creates_no_key_in_payload(self):
        """When causal_chain is None, no 'causal_chain' key in payload."""
        # Intercept _try_publish to verify payload structure
        captured_payloads = []

        def capture_publish(event_type, payload):
            captured_payloads.append((event_type, payload))

        with patch("cot_events._try_publish", side_effect=capture_publish):
            emit_step_start(step_name="test", session_id="sess-1")
            assert len(captured_payloads) == 1
            _, payload = captured_payloads[0]
            assert "causal_chain" not in payload

    def test_empty_list_causal_chain_creates_no_key_in_payload(self):
        """When causal_chain is empty list, no 'causal_chain' key in payload."""
        captured_payloads = []

        def capture_publish(event_type, payload):
            captured_payloads.append((event_type, payload))

        with patch("cot_events._try_publish", side_effect=capture_publish):
            # build_causal_chain returns None for empty list
            chain = build_causal_chain([])
            emit_step_start(step_name="test", session_id="sess-1", causal_chain=chain)
            assert len(captured_payloads) == 1
            _, payload = captured_payloads[0]
            assert "causal_chain" not in payload

    def test_causal_chain_serialized_in_payload(self):
        """When causal_chain is provided, it appears in payload as list of dicts."""
        captured_payloads = []

        def capture_publish(event_type, payload):
            captured_payloads.append((event_type, payload))

        with patch("cot_events._try_publish", side_effect=capture_publish):
            chain = build_causal_chain(
                [
                    ("prev", "current", "scheduled"),
                    ("current", "next", "completed"),
                ]
            )
            emit_step_start(step_name="test", session_id="sess-1", causal_chain=chain)
            assert len(captured_payloads) == 1
            _, payload = captured_payloads[0]
            assert "causal_chain" in payload
            assert isinstance(payload["causal_chain"], list)
            assert len(payload["causal_chain"]) == 2
            assert payload["causal_chain"][0]["source_event_id"] == "prev"
            assert payload["causal_chain"][1]["reason"] == "completed"

    def test_all_event_types_support_causal_chain(self):
        """All emit_* functions properly include causal_chain in payload."""
        captured_payloads = []

        def capture_publish(event_type, payload):
            captured_payloads.append((event_type, payload))

        chain = build_causal_chain([("a", "b", "reason")])

        with patch("cot_events._try_publish", side_effect=capture_publish):
            # Test all six event types
            emit_step_start(step_name="test", causal_chain=chain)
            emit_step_complete(step_name="test", start_time=1000.0, causal_chain=chain)
            emit_tool_call(tool_name="test", arguments={}, causal_chain=chain)
            emit_tool_result(tool_name="test", result="ok", start_time=1000.0, causal_chain=chain)
            emit_llm_chunk(chunk="text", causal_chain=chain)
            emit_plan(steps=["step"], causal_chain=chain)

        # All 6 should have been published with causal_chain
        assert len(captured_payloads) == 6
        for event_type, payload in captured_payloads:
            assert "causal_chain" in payload, f"Event {event_type} missing causal_chain"
            assert isinstance(payload["causal_chain"], list)
            assert len(payload["causal_chain"]) == 1


class TestSensitiveDataRedaction:
    """Tests for redaction of sensitive data in causal reasons."""

    def test_all_sensitive_fragments_redacted_in_reason(self):
        """CausalLink redacts all sensitive key fragments in reason field."""
        sensitive_words = [
            "password",
            "passwd",
            "secret",
            "token",
            "api_key",
            "apikey",
            "auth",
            "credential",
            "private_key",
            "privatekey",
            "access_key",
            "accesskey",
            "bearer",
        ]

        for word in sensitive_words:
            link = CausalLink(
                source_event_id="test",
                target_event_id="test",
                reason=f"some_{word}_check",
            )
            result = link.to_dict()
            assert result["reason"] == "<redacted>", f"Failed to redact {word}"

    def test_case_insensitive_redaction(self):
        """Redaction is case-insensitive."""
        variations = [
            ("SECRET_FOUND", "<redacted>"),
            ("Secret_Found", "<redacted>"),
            ("sEcReT_FoUnD", "<redacted>"),
            ("TOKEN_EXPIRED", "<redacted>"),
            ("Token_Expired", "<redacted>"),
        ]

        for reason, expected in variations:
            link = CausalLink(
                source_event_id="test",
                target_event_id="test",
                reason=reason,
            )
            result = link.to_dict()
            assert result["reason"] == expected, f"Failed for {reason}"
