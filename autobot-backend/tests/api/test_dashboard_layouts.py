# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET/PUT/DELETE /users/me/dashboard-layouts/{page}: per user, per page, validated (#18242)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest
from fastapi import HTTPException

from api.schemas_users_dashboard_layouts import DashboardLayout
from api.users import get_dashboard_layout, put_dashboard_layout, reset_dashboard_layout

_ALICE = {"user_id": "alice"}
_BOB = {"user_id": "bob"}


def _fake_redis():
    store: dict[str, str] = {}

    async def _set(key, value):
        store[key] = value

    async def _get(key):
        return store.get(key)

    async def _delete(key):
        store.pop(key, None)

    client = AsyncMock()
    client.set.side_effect = _set
    client.get.side_effect = _get
    client.delete.side_effect = _delete
    return client, store


def _layout(*widget_ids: str, span: int = 6) -> DashboardLayout:
    widgets = [{"id": w, "type": "system", "title": w, "span": span} for w in widget_ids]
    return DashboardLayout(dashboards=[{"id": "main", "name": "Main", "widgets": widgets}], activeId="main")


async def _call(fn, *args, client):
    with patch("api.users.get_async_redis_client", new=AsyncMock(return_value=client)):
        return await fn(*args)


@pytest.mark.asyncio
async def test_a_saved_layout_reads_back_for_its_owner_and_page_only():
    client, _ = _fake_redis()
    await _call(put_dashboard_layout, "home", _layout("a", "b"), MagicMock(), _ALICE, client=client)
    mine = await _call(get_dashboard_layout, "home", MagicMock(), _ALICE, client=client)
    assert [w.id for w in mine.data.layout.dashboards[0].widgets] == ["a", "b"]
    # Contrast: another user, and another page of the same user, see no stored layout.
    other_user = await _call(get_dashboard_layout, "home", MagicMock(), _BOB, client=client)
    other_page = await _call(get_dashboard_layout, "company-os", MagicMock(), _ALICE, client=client)
    assert other_user.data.layout.dashboards == [] and other_page.data.layout.dashboards == []


@pytest.mark.asyncio
async def test_reset_drops_the_stored_layout():
    client, store = _fake_redis()
    await _call(put_dashboard_layout, "home", _layout("a"), MagicMock(), _ALICE, client=client)
    res = await _call(reset_dashboard_layout, "home", MagicMock(), _ALICE, client=client)
    assert res.data.layout.dashboards == [] and store == {}


@pytest.mark.asyncio
async def test_an_unknown_page_is_404_and_writes_nothing():
    client, store = _fake_redis()
    with pytest.raises(HTTPException) as err:
        await _call(put_dashboard_layout, "admin", _layout("a"), MagicMock(), _ALICE, client=client)
    assert err.value.status_code == 404 and store == {}


@pytest.mark.asyncio
async def test_duplicate_widget_ids_are_422():
    client, store = _fake_redis()
    with pytest.raises(HTTPException) as err:
        await _call(put_dashboard_layout, "home", _layout("a", "a"), MagicMock(), _ALICE, client=client)
    assert err.value.status_code == 422 and store == {}


@pytest.mark.asyncio
async def test_an_invalid_stored_document_reads_as_defaults_not_an_error():
    client, store = _fake_redis()
    store["user:alice:dashboard_layout:home"] = '{"dashboards": "not a list"}'
    res = await _call(get_dashboard_layout, "home", MagicMock(), _ALICE, client=client)
    assert res.data.layout.dashboards == []


@pytest.mark.parametrize("span", [3, 5, 7, 13])
def test_a_span_outside_4_6_8_12_is_rejected(span):
    with pytest.raises(pydantic.ValidationError):
        _layout("a", span=span)


def test_the_height_is_bounded():
    widget = {"id": "a", "type": "system", "height": 100}
    with pytest.raises(pydantic.ValidationError):
        DashboardLayout(dashboards=[{"id": "main", "name": "Main", "widgets": [widget]}])


@pytest.mark.asyncio
async def test_a_layout_over_64_kb_is_413_and_writes_nothing():
    client, store = _fake_redis()
    big = DashboardLayout(
        dashboards=[
            {"id": "main", "name": "Main", "widgets": [{"id": "a", "type": "system", "props": {"blob": "x" * 70_000}}]}
        ]
    )
    with pytest.raises(HTTPException) as err:
        await _call(put_dashboard_layout, "home", big, MagicMock(), _ALICE, client=client)
    assert err.value.status_code == 413 and store == {}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "call",
    [
        lambda: (get_dashboard_layout, ("home", MagicMock(), {})),
        lambda: (put_dashboard_layout, ("home", _layout("a"), MagicMock(), {})),
        lambda: (reset_dashboard_layout, ("home", MagicMock(), {})),
    ],
    ids=["get", "put", "delete"],
)
async def test_a_token_without_a_user_id_is_401_on_every_endpoint(call):
    client, store = _fake_redis()
    fn, args = call()
    with pytest.raises(HTTPException) as err:
        await _call(fn, *args, client=client)
    assert err.value.status_code == 401 and store == {}
    client.get.assert_not_awaited()


_ENDPOINTS = [
    lambda: (get_dashboard_layout, ("home", MagicMock(), _ALICE)),
    lambda: (put_dashboard_layout, ("home", _layout("a"), MagicMock(), _ALICE)),
    lambda: (reset_dashboard_layout, ("home", MagicMock(), _ALICE)),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("call", _ENDPOINTS, ids=["get", "put", "delete"])
async def test_no_redis_client_is_503_on_every_endpoint(call):
    """get_async_redis_client returns None when Redis is disabled or its breaker is open (#18242 review)."""
    fn, args = call()
    with pytest.raises(HTTPException) as err:
        await _call(fn, *args, client=None)
    assert err.value.status_code == 503
    # Contrast: the same call with a client answers normally.
    client, _ = _fake_redis()
    assert (await _call(fn, *args, client=client)).success is True
