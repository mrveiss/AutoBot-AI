# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
ACP wire vocabulary (#14825).

These are the shapes an external editor parses, so the discriminator strings and
key casing are contract, not style. ACP requires camelCase property keys with
snake_case reserved for discriminators; a silent rename here breaks every client
without failing anything else in this repo.
"""

import pytest

from acp.protocol import (
    ACP_PROTOCOL_VERSION,
    AcpError,
    AcpErrorCode,
    AcpMethod,
    StopReason,
    agent_capabilities,
    agent_message_chunk,
    agent_thought_chunk,
    plan_update,
    text_block,
    tool_call_update,
)


def test_protocol_version_is_an_integer():
    # ACP negotiates on an integer version; a string would fail min() in the
    # handshake and silently pin the wrong revision.
    assert isinstance(ACP_PROTOCOL_VERSION, int)


def test_method_names_match_the_acp_specification():
    # Exact strings — an editor dispatches on these.
    assert AcpMethod.INITIALIZE == "initialize"
    assert AcpMethod.SESSION_NEW == "session/new"
    assert AcpMethod.SESSION_PROMPT == "session/prompt"
    assert AcpMethod.SESSION_UPDATE == "session/update"
    assert AcpMethod.SESSION_CANCEL == "session/cancel"
    assert AcpMethod.SESSION_REQUEST_PERMISSION == "session/request_permission"


def test_stop_reasons_match_the_specification():
    assert StopReason.END_TURN == "end_turn"
    assert StopReason.CANCELLED == "cancelled"
    assert StopReason.REFUSAL == "refusal"
    assert StopReason.MAX_TOKENS == "max_tokens"


def test_text_block_shape():
    assert text_block("hi") == {"type": "text", "text": "hi"}


def test_agent_message_chunk_shape():
    update = agent_message_chunk("s-1", "hello")
    assert update["sessionId"] == "s-1"
    assert update["update"]["sessionUpdate"] == "agent_message_chunk"
    assert update["update"]["content"]["text"] == "hello"


def test_agent_thought_chunk_is_distinct_from_a_message_chunk():
    # Clients render reasoning separately from the reply; collapsing the two
    # would surface internal thinking as assistant output.
    thought = agent_thought_chunk("s-1", "considering")
    message = agent_message_chunk("s-1", "considering")
    assert thought["update"]["sessionUpdate"] == "agent_thought_chunk"
    assert thought["update"]["sessionUpdate"] != message["update"]["sessionUpdate"]


def test_tool_call_update_carries_lifecycle_fields():
    update = tool_call_update("s-1", "t-1", "Run tests", "in_progress", kind="execute")
    inner = update["update"]
    assert inner["sessionUpdate"] == "tool_call"
    assert inner["toolCallId"] == "t-1"
    assert inner["title"] == "Run tests"
    assert inner["status"] == "in_progress"
    assert inner["kind"] == "execute"


def test_tool_call_update_omits_content_when_none_is_given():
    # Absent rather than null: an empty content key renders as an empty block
    # in some clients.
    assert "content" not in tool_call_update("s-1", "t-1", "x", "pending")["update"]


def test_tool_call_update_includes_content_when_given():
    update = tool_call_update("s-1", "t-1", "x", "completed", content=[text_block("out")])
    assert update["update"]["content"] == [{"type": "text", "text": "out"}]


def test_plan_update_shape():
    update = plan_update("s-1", [{"content": "step one", "status": "pending"}])
    assert update["update"]["sessionUpdate"] == "plan"
    assert update["update"]["entries"][0]["content"] == "step one"


def test_capabilities_do_not_claim_unimplemented_features():
    caps = agent_capabilities()
    # loadSession is False because session/load is not served; advertising it
    # would make a client call a method that does not exist.
    assert caps["loadSession"] is False
    assert caps["promptCapabilities"]["image"] is False
    assert caps["promptCapabilities"]["audio"] is False


def test_error_renders_as_a_jsonrpc_error_member():
    err = AcpError(AcpErrorCode.INVALID_PARAMS, "bad cwd")
    assert err.to_dict() == {"code": -32602, "message": "bad cwd"}


def test_error_includes_data_only_when_present():
    assert "data" not in AcpError(AcpErrorCode.INTERNAL_ERROR, "x").to_dict()
    assert AcpError(AcpErrorCode.INTERNAL_ERROR, "x", {"k": 1}).to_dict()["data"] == {"k": 1}


def test_error_codes_use_the_standard_jsonrpc_range():
    assert int(AcpErrorCode.METHOD_NOT_FOUND) == -32601
    assert int(AcpErrorCode.PARSE_ERROR) == -32700


def test_error_is_raisable():
    with pytest.raises(AcpError):
        raise AcpError(AcpErrorCode.INVALID_REQUEST, "nope")
