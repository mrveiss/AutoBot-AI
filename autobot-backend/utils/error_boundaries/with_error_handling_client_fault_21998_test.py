# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``with_error_handling`` answers an exception that declares a client-fault category with its 4xx (#21998).

``ValidationError`` raised under a route whose fallback category is SERVER_ERROR used to be a
500 logged at ERROR; the boundary mapped by the route's declared category only.
"""

import inspect
import logging

import pytest
from fastapi import HTTPException

import exceptions
from autobot_shared.error_boundaries.decorators import with_error_handling
from autobot_shared.error_boundaries.types import ErrorCategory
from exceptions import AutoBotError, ValidationError


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
    assert exc.value.detail["error"]["details"]["reason"] == "Validation failed"
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


@pytest.mark.parametrize(
    "exc,status,level",
    [
        (exceptions.AuthenticationError("token abc"), 401, logging.WARNING),
        (exceptions.AuthorizationError("role x"), 403, logging.WARNING),
        (exceptions.ResourceNotFoundError("nope"), 404, logging.WARNING),
        (exceptions.ResourceLimitError("slow down"), 429, logging.WARNING),
        (exceptions.InternalError("db dsn"), 500, logging.ERROR),
    ],
)
@pytest.mark.asyncio
async def test_declared_category_wins_over_route_fallback(exc, status, level, caplog):
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="declared_op")
    async def _endpoint():
        raise exc

    with caplog.at_level(logging.WARNING), pytest.raises(HTTPException) as raised:
        await _endpoint()

    assert raised.value.status_code == status
    assert [r.levelno for r in caplog.records if "declared_op" in r.getMessage()] == [level]


@pytest.mark.parametrize("category,status", [(ErrorCategory.USER_INPUT, 400), (ErrorCategory.NOT_FOUND, 404)])
@pytest.mark.asyncio
async def test_route_category_still_applies_to_undeclared_exceptions(category, status):
    @with_error_handling(category=category, operation="route_cat_op")
    async def _endpoint():
        raise ValueError("x")

    with pytest.raises(HTTPException) as raised:
        await _endpoint()
    assert raised.value.status_code == status


@pytest.mark.asyncio
async def test_value_details_and_message_are_not_returned():
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="leak_op")
    async def _endpoint():
        raise ValidationError("secret-message", field="f", value="secret-value")

    with pytest.raises(HTTPException) as raised:
        await _endpoint()
    body = str(raised.value.detail)
    assert "secret-message" not in body and "secret-value" not in body


def _all_autobot_errors():
    return [c for _, c in inspect.getmembers(exceptions, inspect.isclass) if issubclass(c, AutoBotError)]


@pytest.mark.parametrize("cls", _all_autobot_errors(), ids=lambda c: c.__name__)
def test_get_error_code_and_boundary_agree_for_every_exception_class(cls):
    """One mapping: the status comes from error_category for both consumers (#21998)."""
    from autobot_shared.error_boundaries.types import APIErrorResponse

    instance = cls.__new__(cls)
    instance.details = {}
    expected = 500 if cls.error_category is None else APIErrorResponse.get_status_code_for_category(cls.error_category)
    assert exceptions.get_error_code(instance) == expected
    assert not hasattr(exceptions, "ERROR_CODES")


@pytest.mark.parametrize(
    "cls,status",
    [
        (exceptions.ValidationError, 400),
        (exceptions.AuthenticationError, 401),
        (exceptions.AuthorizationError, 403),
        (exceptions.ResourceNotFoundError, 404),
        (exceptions.ResourceLimitError, 429),
        (exceptions.InternalError, 500),
        (exceptions.WorkflowValidationError, 400),  # was 422: no 422 category exists
        (exceptions.WorkflowExecutionError, 500),  # a failed run is a server fault (was 422)
        (exceptions.LLMTimeoutError, 502),  # was 504: closest upstream-failure category
    ],
)
def test_status_table_is_written_out_not_recomputed(cls, status):
    """Literal expected statuses, so a wrongly declared category is caught (#21998)."""
    instance = cls.__new__(cls)
    instance.details = {}
    assert exceptions.get_error_code(instance) == status
