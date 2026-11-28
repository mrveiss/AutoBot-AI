# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A failed membership lookup answers a fixed 500 and logs the cause (#21396).

``require_board_role`` used to put the exception text in the response ``detail``;
driver messages and connection targets belong in the server log only.
"""

from __future__ import annotations

import logging
import uuid
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

from llc.deps import MEMBERSHIP_LOOKUP_FAILED_DETAIL, logged_server_error, require_board_role

_COMPANY_ID = uuid.UUID("00000000-0000-0000-0000-000000000a11")
_LEAK_MARKER = "LEAK-MARKER-db-host-7f3a"
_LOG_NAME = "llc.deps"


def _app(membership_svc: object) -> FastAPI:
    app = FastAPI()

    @app.get("/probe")
    async def probe() -> dict:
        role = await require_board_role(
            _COMPANY_ID,
            {"id": "user-1"},
            MagicMock(),
            {"owner"},
            membership_svc,
        )
        return {"actor": role}

    return app


async def _get(membership_svc: object) -> httpx.Response:
    transport = httpx.ASGITransport(app=_app(membership_svc))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/probe")


@pytest.mark.asyncio
async def test_lookup_failure_returns_fixed_detail_without_exception_text(caplog):  # noqa: ANN001
    svc = MagicMock()
    svc.list_members = AsyncMock(side_effect=RuntimeError(f"connect failed\r\nforged line {_LEAK_MARKER}"))

    with caplog.at_level(logging.ERROR, logger=_LOG_NAME):
        resp = await _get(svc)

    assert resp.status_code == 500
    assert resp.json() == {"detail": MEMBERSHIP_LOOKUP_FAILED_DETAIL}
    assert _LEAK_MARKER not in resp.text
    assert "RuntimeError" not in resp.text


@pytest.mark.asyncio
async def test_lookup_failure_is_logged_without_raw_line_breaks(caplog):  # noqa: ANN001
    svc = MagicMock()
    svc.list_members = AsyncMock(side_effect=RuntimeError(f"connect failed\r\nforged line {_LEAK_MARKER}"))

    with caplog.at_level(logging.ERROR, logger=_LOG_NAME):
        await _get(svc)

    records = [r for r in caplog.records if r.name == _LOG_NAME and r.levelno == logging.ERROR]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "RuntimeError" in message
    assert str(_COMPANY_ID) in message
    assert "\r" not in message and "\n" not in message
    assert "[at " in message and ".py:" in message


def test_scope_with_line_breaks_is_neutralised_in_the_log(caplog):  # noqa: ANN001
    log = logging.getLogger(_LOG_NAME)
    with caplog.at_level(logging.ERROR, logger=_LOG_NAME):
        error = logged_server_error(log, "Fixed text", "company x\r\n2026-01-01 ERROR forged", RuntimeError("boom"))

    assert error.status_code == 500 and error.detail == "Fixed text"
    message = caplog.records[-1].getMessage()
    assert "\r" not in message and "\n" not in message
    assert "forged" in message
