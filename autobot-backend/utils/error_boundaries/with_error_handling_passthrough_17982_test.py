# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`with_error_handling` lets a pass-through error reach its app-level handler (#17982)."""

import pytest
from fastapi import HTTPException

from api.codebase_analytics.source_storage import RegistryUnavailable
from autobot_shared.error_boundaries.decorators import with_error_handling
from autobot_shared.error_boundaries.types import PassThroughError


def test_registry_unavailable_is_a_pass_through_error():
    assert issubclass(RegistryUnavailable, PassThroughError)


@pytest.mark.asyncio
async def test_async_registry_unavailable_propagates_unchanged():
    err = RegistryUnavailable("down")

    @with_error_handling()
    async def _endpoint():
        raise err

    with pytest.raises(RegistryUnavailable) as caught:
        await _endpoint()
    assert caught.value is err


def test_sync_registry_unavailable_propagates_unchanged():
    @with_error_handling()
    def _endpoint():
        raise RegistryUnavailable("down")

    with pytest.raises(RegistryUnavailable):
        _endpoint()


@pytest.mark.asyncio
async def test_a_generic_exception_is_still_converted():
    @with_error_handling()
    async def _endpoint():
        raise RuntimeError("boom")

    with pytest.raises(HTTPException) as caught:
        await _endpoint()
    assert caught.value.status_code == 500
