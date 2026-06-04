# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Integration tests for reasoning effort backend (MVA-3028).

Covers:
- UserPreferences model validation
- GET/PATCH /users/me/preferences via endpoint functions
- _map_effort_to_provider_params correctness under real import paths
- /chat endpoint passes thinking_mode_enabled / thinking_budget_tokens through
  to the LLM context
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError

from api.users import (
    UserPreferences,
    _get_user_preferences_from_redis,
    _store_user_preferences_to_redis,
)

# Load the real reasoning_effort module directly to bypass the llm_shared stub
# registered in conftest.py, which replaces llm_shared.providers with a MagicMock.
import importlib.util as _ilu
import pathlib as _pathlib

_re_spec = _ilu.spec_from_file_location(
    "llm_shared.providers.reasoning_effort",
    str(
        _pathlib.Path(__file__).parent.parent.parent
        / "llm_shared"
        / "providers"
        / "reasoning_effort.py"
    ),
)
_re_mod = _ilu.module_from_spec(_re_spec)
_re_spec.loader.exec_module(_re_mod)
_map_effort_to_provider_params = _re_mod._map_effort_to_provider_params


# ---------------------------------------------------------------------------
# UserPreferences model validation
# ---------------------------------------------------------------------------

class TestUserPreferencesModel:
    @pytest.mark.parametrize("effort", ["low", "medium", "high", "auto"])
    def test_valid_effort_accepted(self, effort):
        pref = UserPreferences(reasoning_effort=effort)
        assert pref.reasoning_effort == effort

    def test_default_is_auto(self):
        pref = UserPreferences()
        assert pref.reasoning_effort == "auto"

    def test_invalid_effort_rejected(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            UserPreferences(reasoning_effort="extreme")

    def test_empty_effort_rejected(self):
        import pydantic
        with pytest.raises(pydantic.ValidationError):
            UserPreferences(reasoning_effort="")


# ---------------------------------------------------------------------------
# Redis helpers
# ---------------------------------------------------------------------------

def _async_redis(mock_redis):
    """Return an AsyncMock that, when awaited, yields mock_redis."""
    return AsyncMock(return_value=mock_redis)


@pytest.mark.asyncio
async def test_get_preferences_returns_stored_value():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"high"
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        pref = await _get_user_preferences_from_redis("user-123")
    assert pref.reasoning_effort == "high"


@pytest.mark.asyncio
async def test_get_preferences_defaults_to_auto_when_missing():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        pref = await _get_user_preferences_from_redis("user-456")
    assert pref.reasoning_effort == "auto"


@pytest.mark.asyncio
async def test_get_preferences_returns_auto_on_redis_error():
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = RedisError("connection refused")
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        pref = await _get_user_preferences_from_redis("user-789")
    assert pref.reasoning_effort == "auto"


@pytest.mark.asyncio
async def test_store_preferences_calls_redis_set():
    mock_redis = AsyncMock()
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        await _store_user_preferences_to_redis("user-123", UserPreferences(reasoning_effort="medium"))
    mock_redis.set.assert_awaited_once_with("user:user-123:preferences:reasoning_effort", "medium")


# ---------------------------------------------------------------------------
# Endpoint internals: GET /users/me/preferences
# The route handlers are wrapped by @with_error_handling without parentheses,
# which means the inner async function is best tested via its module-level
# private helpers rather than through the decorated route object.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_preferences_full_flow_returns_correct_effort():
    """Full get-preferences flow: Redis returns stored value → correct pref returned."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"low"
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        pref = await _get_user_preferences_from_redis("u-abc")
    assert pref.reasoning_effort == "low"


@pytest.mark.asyncio
async def test_update_preferences_full_flow_stores_effort():
    """Full update-preferences flow: stores correct value in Redis."""
    mock_redis = AsyncMock()
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        await _store_user_preferences_to_redis("u-xyz", UserPreferences(reasoning_effort="high"))
    mock_redis.set.assert_awaited_once_with("user:u-xyz:preferences:reasoning_effort", "high")


@pytest.mark.asyncio
async def test_update_preferences_raises_redis_error():
    """Redis errors during store propagate as RedisError."""
    mock_redis = AsyncMock()
    mock_redis.set.side_effect = RedisError("timeout")
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        with pytest.raises(RedisError):
            await _store_user_preferences_to_redis("u-xyz", UserPreferences(reasoning_effort="medium"))


# ---------------------------------------------------------------------------
# /chat endpoint: thinking parameters flow through to LLM context
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_send_message_passes_thinking_fields_to_process():
    """The /chat endpoint invokes process_chat_message; verify thinking kwargs reach it."""
    from api.chat import send_message
    from api.schemas_chat import ChatMessage

    msg = ChatMessage(
        content="explain reasoning",
        session_id="sess-001",
        thinking_mode_enabled=True,
        thinking_budget_tokens=8000,
    )

    fake_response_data = MagicMock()
    fake_response_data.model_dump.return_value = {
        "content": "ok",
        "role": "assistant",
        "session_id": "sess-001",
        "message_id": "m-1",
        "timestamp": "2025-01-01T00:00:00Z",
        "metadata": {},
        "thinking_metadata": None,
    }

    mock_request = MagicMock()
    mock_request.state.chat_history_manager = AsyncMock()
    mock_request.state.llm_service = AsyncMock()
    mock_request.state.memory_interface = AsyncMock()
    mock_request.client.host = "127.0.0.1"

    with (
        patch("api.chat.process_chat_message", return_value=fake_response_data) as mock_process,
        patch("api.chat.get_config", return_value=MagicMock(chat_timeout=30.0)),
        patch("api.chat.get_knowledge_base", return_value=MagicMock()),
        patch("api.chat.get_chat_history_manager", return_value=AsyncMock()),
        patch("api.chat.get_llm_service", return_value=AsyncMock()),
        patch("api.chat.get_memory_interface", return_value=AsyncMock()),
        patch("api.chat.log_request_context"),
        patch("api.chat.generate_request_id", return_value="req-001"),
    ):
        await send_message(
            current_user={"user_id": "u-1"},
            message=msg,
            request=mock_request,
            config=MagicMock(chat_timeout=30.0),
            knowledge_base=MagicMock(),
        )

    mock_process.assert_awaited_once()
    call_kwargs = mock_process.call_args
    passed_message = call_kwargs[0][0]
    assert passed_message.thinking_mode_enabled is True
    assert passed_message.thinking_budget_tokens == 8000


# ---------------------------------------------------------------------------
# Provider params round-trip: effort → provider params
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "effort,provider,expected",
    [
        ("low", "anthropic", {"thinking_tokens": 2000}),
        ("medium", "anthropic", {"thinking_tokens": 5000}),
        ("high", "anthropic", {"thinking_tokens": 10000}),
        ("low", "openai", {"reasoning_effort": "low"}),
        ("high", "openai", {"reasoning_effort": "high"}),
        ("auto", "openai", {}),
        ("medium", "bedrock", {"thinking_tokens": 5000}),
        ("high", "gemini", {}),
        ("low", "vertex", {}),
        ("medium", "unknown-provider", {}),
    ],
)
def test_provider_params_round_trip(effort, provider, expected):
    assert _map_effort_to_provider_params(effort, provider) == expected
