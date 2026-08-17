# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Failure-path behaviour of ``with_default_on_error`` (#14191).

This decorator was named ``with_error_handling`` until #14191, sharing a name
with ``utils.error_boundaries.decorators.with_error_handling`` while behaving
oppositely on the one case both had to make a decision about — what happens to
``HTTPException``. It had zero test coverage under either name, so these pin
its actual failure-path contract: log-and-return-default, the ``reraise``
escape hatch, the ``error_types`` filter, the async path, and the bare-usage
guard that #14186 showed neither sibling decorator had.

Behaviour is asserted by calling the decorator against a function that raises
and observing the return value / re-raise / log record — never by reading the
decorator's source text.
"""

import logging

import pytest

from error_handler import with_default_on_error


class _Boom(Exception):
    """A plain exception, not an AutoBotError subclass."""


class _OtherBoom(Exception):
    """A second, unrelated exception type for error_types filtering tests."""


def test_swallows_and_returns_the_default_on_failure():
    @with_default_on_error(default_return="fallback")
    def _fails():
        raise _Boom("kaboom")

    assert _fails() == "fallback"


def test_default_return_defaults_to_none():
    @with_default_on_error()
    def _fails():
        raise _Boom("kaboom")

    assert _fails() is None


def test_success_path_is_untouched():
    @with_default_on_error(default_return="fallback")
    def _ok():
        return "real result"

    assert _ok() == "real result"


def test_the_failure_is_logged_with_traceback(caplog):
    @with_default_on_error(default_return=None, context="my_operation")
    def _fails():
        raise _Boom("kaboom")

    with caplog.at_level(logging.CRITICAL):
        _fails()

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "my_operation" in logged
    assert "_Boom" in logged
    assert "kaboom" in logged
    assert any(r.exc_info for r in caplog.records), "traceback not captured"


def test_reraise_true_propagates_the_original_exception_after_logging(caplog):
    @with_default_on_error(default_return="fallback", reraise=True)
    def _fails():
        raise _Boom("kaboom")

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(_Boom, match="kaboom"):
            _fails()

    assert any("kaboom" in r.getMessage() for r in caplog.records), "reraise must not skip logging"


def test_reraise_preserves_the_traceback():
    @with_default_on_error(reraise=True)
    def _fails():
        raise _Boom("kaboom")

    try:
        _fails()
    except _Boom as caught:
        # The traceback must include this test's own frame, not just the
        # decorator's — a bare `raise` (not `raise e`) keeps the original chain.
        assert caught.__traceback__ is not None
        frame_names = []
        tb = caught.__traceback__
        while tb is not None:
            frame_names.append(tb.tb_frame.f_code.co_name)
            tb = tb.tb_next
        assert "_fails" in frame_names
    else:
        pytest.fail("expected _Boom to propagate")


def test_error_types_filter_lets_unmatched_exceptions_propagate_unlogged(caplog):
    """An exception outside error_types must not be treated as handled."""

    @with_default_on_error(default_return="fallback", error_types=(_OtherBoom,))
    def _fails():
        raise _Boom("kaboom")

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(_Boom):
            _fails()

    # This is the filter's whole point: an unmatched type is not this
    # decorator's concern, so it must not be logged as a handled failure.
    assert not any("kaboom" in r.getMessage() for r in caplog.records)


def test_error_types_filter_still_handles_matched_exceptions():
    @with_default_on_error(default_return="fallback", error_types=(_Boom,))
    def _fails():
        raise _Boom("kaboom")

    assert _fails() == "fallback"


@pytest.mark.asyncio
async def test_async_swallows_and_returns_the_default_on_failure():
    @with_default_on_error(default_return="fallback")
    async def _fails():
        raise _Boom("kaboom")

    assert await _fails() == "fallback"


@pytest.mark.asyncio
async def test_async_reraise_true_propagates_after_logging(caplog):
    @with_default_on_error(reraise=True)
    async def _fails():
        raise _Boom("kaboom")

    with caplog.at_level(logging.CRITICAL):
        with pytest.raises(_Boom):
            await _fails()

    assert any("kaboom" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_async_success_path_is_untouched():
    @with_default_on_error(default_return="fallback")
    async def _ok():
        return "real result"

    assert await _ok() == "real result"


def test_bare_usage_raises_typeerror_instead_of_silently_misbinding():
    """#14186: the sibling decorator's only bare call site silently rebound the
    decorated function to the inner `decorator` object. This one must fail
    loudly instead of reproducing that defect under its own name.
    """

    with pytest.raises(TypeError, match="parentheses"):

        @with_default_on_error
        def _fails():
            raise _Boom("kaboom")
