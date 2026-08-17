# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``with_error_handling`` must reject bare (no-parentheses) usage (#14191).

#14186 found the only bare call site in the backend (1 against 1904 called):
``@with_error_handling`` with no parentheses passes the decorated function as
``category`` and this factory unconditionally returned its inner ``decorator``
— the module-level name was silently rebound to that decorator object instead
of a wrapped endpoint, and nothing caught it. #14191's audit noted neither
this decorator nor its unrelated same-named sibling in
``autobot-backend/error_handler.py`` (renamed to ``with_default_on_error`` by
this change) had a ``callable()`` guard against that. This pins the guard on
the survivor.
"""

import pytest
from fastapi import HTTPException

from utils.error_boundaries.decorators import with_error_handling
from utils.error_boundaries.types import ErrorCategory


def test_bare_usage_raises_typeerror_instead_of_silently_misbinding():
    with pytest.raises(TypeError, match="parentheses"):

        @with_error_handling
        async def _endpoint():
            raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_called_with_no_arguments_still_works():
    """@with_error_handling() — the common, correct bare-call form — must not
    be caught by the same guard that rejects the parenthesis-free form."""

    @with_error_handling()
    async def _endpoint():
        raise RuntimeError("boom")

    with pytest.raises(HTTPException):
        await _endpoint()


@pytest.mark.asyncio
async def test_called_with_a_category_keyword_still_works():
    @with_error_handling(category=ErrorCategory.VALIDATION)
    async def _endpoint():
        raise RuntimeError("boom")

    with pytest.raises(HTTPException) as caught:
        await _endpoint()

    assert caught.value.status_code == 400
