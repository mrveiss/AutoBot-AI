# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PATCH /users/me/preferences is truly partial; ui_mode/ui_start/theme_variant (#18240)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest

from api.users import UserPreferences, get_user_preferences, update_user_preferences

_USER = {"user_id": "u-partial"}


def _fake_redis():
    store: dict[str, str] = {}

    async def _set(key, value):
        store[key] = value

    async def _get(key):
        return store.get(key)

    client = AsyncMock()
    client.set.side_effect = _set
    client.get.side_effect = _get
    return client, store


async def _patch(body: dict, client):
    prefs = UserPreferences(**body)
    with patch("api.users.get_async_redis_client", new=AsyncMock(return_value=client)):
        res = await update_user_preferences(prefs, MagicMock(), _USER)
    return res.data.preferences


@pytest.mark.asyncio
async def test_omitted_field_keeps_stored_value_but_sent_field_changes():
    client, store = _fake_redis()
    await _patch({"theme": "dark", "ui_mode": "minimal"}, client)
    # Contrast pair: omitting ui_mode leaves it; sending it changes it.
    omitted = await _patch({"font_size": "large"}, client)
    assert omitted.ui_mode == "minimal" and omitted.theme == "dark"
    assert omitted.font_size == "large"
    sent = await _patch({"ui_mode": "full"}, client)
    assert sent.ui_mode == "full" and sent.theme == "dark"
    assert store["user:u-partial:preferences:ui_mode"] == "full"


@pytest.mark.asyncio
async def test_empty_patch_writes_nothing():
    client, _ = _fake_redis()
    await _patch({}, client)
    client.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_returns_defaults_when_unset():
    client, _ = _fake_redis()
    with patch("api.users.get_async_redis_client", new=AsyncMock(return_value=client)):
        res = await get_user_preferences(MagicMock(), _USER)
    p = res.data.preferences
    assert (p.ui_mode, p.ui_start, p.theme_variant) == ("full", "last", "default")


@pytest.mark.parametrize(
    "field,value",
    [
        ("ui_mode", "minimal"),
        ("ui_mode", "full"),
        ("ui_start", "last"),
        ("ui_start", "minimal"),
        ("theme_variant", "default"),
        ("theme_variant", "ember-2_x"),
        ("theme_variant", "a" * 63),
    ],
)
def test_new_fields_accept_good(field, value):
    assert getattr(UserPreferences(**{field: value}), field) == value


@pytest.mark.parametrize(
    "field,value",
    [
        ("ui_mode", "last"),
        ("ui_mode", "full\n"),
        ("ui_mode", ""),
        ("ui_start", "other"),
        ("ui_start", "last\n"),
        ("theme_variant", "default\n"),
        ("theme_variant", "Ember"),
        ("theme_variant", "-x"),
        ("theme_variant", "../x"),
        ("theme_variant", "a" * 64),
        ("theme_variant", ""),
    ],
)
def test_new_fields_reject_bad(field, value):
    with pytest.raises(pydantic.ValidationError):
        UserPreferences(**{field: value})
