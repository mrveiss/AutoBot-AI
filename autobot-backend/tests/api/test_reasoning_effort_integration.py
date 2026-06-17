# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Integration tests for reasoning effort backend (MVA-3028).

Covers:
- UserPreferences model validation
- GET/PATCH /users/me/preferences via endpoint functions
- _map_effort_to_provider_params correctness under real import paths
- /chat endpoint passes thinking_mode_enabled / thinking_budget_tokens through
  to the LLM context
"""

# Load the real reasoning_effort module directly to bypass the llm_shared stub
# registered in conftest.py, which replaces llm_shared.providers with a MagicMock.
import importlib.util as _ilu
import pathlib as _pathlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from redis.exceptions import RedisError

from api.users import (
    UserPreferences,
    _get_user_preferences_from_redis,
    _store_user_preferences_to_redis,
)

_re_spec = _ilu.spec_from_file_location(
    "llm_shared.providers.reasoning_effort",
    str(_pathlib.Path(__file__).parent.parent.parent / "llm_shared" / "providers" / "reasoning_effort.py"),
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


def _redis_get_only(field: str, value: bytes):
    """Return an async get() that yields value only for the given preference field."""

    async def _get(key):
        return value if key.endswith(f":{field}") else None

    return _get


@pytest.mark.asyncio
async def test_get_preferences_returns_stored_value():
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = _redis_get_only("reasoning_effort", b"high")
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
    mock_redis.set.assert_any_await("user:user-123:preferences:reasoning_effort", "medium")


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
    mock_redis.get.side_effect = _redis_get_only("reasoning_effort", b"low")
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        pref = await _get_user_preferences_from_redis("u-abc")
    assert pref.reasoning_effort == "low"


@pytest.mark.asyncio
async def test_update_preferences_full_flow_stores_effort():
    """Full update-preferences flow: stores correct value in Redis."""
    mock_redis = AsyncMock()
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        await _store_user_preferences_to_redis("u-xyz", UserPreferences(reasoning_effort="high"))
    mock_redis.set.assert_any_await("user:u-xyz:preferences:reasoning_effort", "high")


# ---------------------------------------------------------------------------
# Appearance preferences (#8988): theme/accent/density persist per account
# ---------------------------------------------------------------------------


class TestAppearancePreferencesModel:
    def test_appearance_defaults(self):
        pref = UserPreferences()
        assert pref.theme == "dark"
        assert pref.accent_color == "blue"
        assert pref.layout_density == "comfortable"
        assert pref.font_size == "medium"
        assert pref.theme_preset == "auto"

    @pytest.mark.parametrize("theme", ["dark", "light", "system"])
    def test_valid_theme_accepted(self, theme):
        assert UserPreferences(theme=theme).theme == theme

    def test_invalid_theme_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            UserPreferences(theme="neon")

    def test_invalid_accent_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            UserPreferences(accent_color="chartreuse")

    def test_invalid_density_rejected(self):
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            UserPreferences(layout_density="cramped")


@pytest.mark.asyncio
async def test_store_appearance_writes_all_fields():
    """Storing appearance prefs writes a Redis key per field."""
    mock_redis = AsyncMock()
    prefs = UserPreferences(
        reasoning_effort="low",
        theme="light",
        accent_color="purple",
        layout_density="compact",
        font_size="large",
        theme_preset="catppuccin-latte",
    )
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        await _store_user_preferences_to_redis("u-app", prefs)
    mock_redis.set.assert_any_await("user:u-app:preferences:theme", "light")
    mock_redis.set.assert_any_await("user:u-app:preferences:accent_color", "purple")
    mock_redis.set.assert_any_await("user:u-app:preferences:layout_density", "compact")
    mock_redis.set.assert_any_await("user:u-app:preferences:font_size", "large")
    mock_redis.set.assert_any_await("user:u-app:preferences:theme_preset", "catppuccin-latte")


@pytest.mark.asyncio
async def test_appearance_round_trip_returns_stored_values():
    """Save → load returns the stored appearance prefs (cross-device round-trip)."""
    store: dict[str, str] = {}

    async def _set(key, value):
        store[key] = value

    async def _get(key):
        return store.get(key)

    mock_redis = AsyncMock()
    mock_redis.set.side_effect = _set
    mock_redis.get.side_effect = _get

    saved = UserPreferences(
        theme="light",
        accent_color="teal",
        layout_density="spacious",
        font_size="small",
        theme_preset="solarized-light",
    )
    with patch("api.users.get_redis_client", new=_async_redis(mock_redis)):
        await _store_user_preferences_to_redis("u-rt", saved)
        loaded = await _get_user_preferences_from_redis("u-rt")

    assert loaded.theme == "light"
    assert loaded.accent_color == "teal"
    assert loaded.layout_density == "spacious"
    assert loaded.font_size == "small"
    assert loaded.theme_preset == "solarized-light"


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
