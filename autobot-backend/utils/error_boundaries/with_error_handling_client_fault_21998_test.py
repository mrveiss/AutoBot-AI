# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``with_error_handling`` answers an exception that declares a client-fault category with its 4xx (#21998).

``ValidationError`` raised under a route whose fallback category is SERVER_ERROR used to be a
500 logged at ERROR; the boundary mapped by the route's declared category only.
"""

import logging

import pytest
from fastapi import HTTPException

from autobot_shared.error_boundaries.decorators import with_error_handling
from autobot_shared.error_boundaries.types import ErrorCategory
from exceptions import ValidationError


@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="bad_input_async")
async def _async_bad_input():
    raise ValidationError("per_page must be 1-100")


@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="bad_input_sync")
def _sync_bad_input():
    raise ValidationError("per_page must be 1-100")


@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="real_fault")
async def _real_fault():
    raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_validation_error_is_400_with_reason_and_warning(caplog):
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc:
        await _async_bad_input()

    assert exc.value.status_code == 400
    assert exc.value.detail["error"]["details"]["reason"] == "per_page must be 1-100"
    assert [r.levelno for r in caplog.records if "bad_input_async" in r.getMessage()] == [logging.WARNING]


def test_sync_validation_error_is_400():
    with pytest.raises(HTTPException) as exc:
        _sync_bad_input()
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_other_exceptions_keep_the_route_category_and_no_reason(caplog):
    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as exc:
        await _real_fault()

    assert exc.value.status_code == 500
    assert "reason" not in exc.value.detail["error"]["details"]
    assert [r.levelno for r in caplog.records if "real_fault" in r.getMessage()] == [logging.ERROR]
