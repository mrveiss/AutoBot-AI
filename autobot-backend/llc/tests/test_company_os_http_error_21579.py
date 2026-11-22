# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`company_os.http_error` answers with a fixed text or `public_detail`, never `str(exc)` (#21579)."""

import logging

import pytest

from llc.api.company_os import http_error
from llc.services.authz import NotAuthorisedError
from llc.services.company_os.errors import (
    CompanyOsConflict,
    CompanyOsError,
    CompanyOsNotFound,
    GraphInvalid,
)

_MARKER = "hunter2leak"
_LEAKY = f"driver failed password={_MARKER}"

_CASES = [
    (NotAuthorisedError, 403, "Forbidden"),
    (CompanyOsNotFound, 404, "Not found"),
    (CompanyOsConflict, 409, "Conflict"),
    (CompanyOsError, 400, "Invalid request"),
]
_IDS = ["not_authorised", "not_found", "conflict", "invalid"]


def _public(base):
    class _P(base):
        public_detail = "Shown to the caller"

    return _P


def _non_public(base):
    class _NonPublic(base):
        public_detail = None  # not a str: `http_refusal` treats the error as non-public

    return _NonPublic


@pytest.mark.parametrize(("cls", "code", "fixed"), _CASES[1:], ids=_IDS[1:])
def test_a_service_error_without_public_detail_gets_the_fixed_text(cls, code, fixed, caplog) -> None:
    sub = _non_public(cls)
    with caplog.at_level(logging.WARNING):
        got = http_error(sub(_LEAKY))
    assert (got.status_code, got.detail) == (code, fixed)
    assert _MARKER not in str(got.detail)
    assert sub.__name__ in caplog.text
    assert _MARKER not in caplog.text


@pytest.mark.parametrize(("cls", "code", "fixed"), _CASES[1:], ids=_IDS[1:])
def test_the_real_service_errors_are_public_and_show_their_own_message(cls, code, fixed) -> None:
    got = http_error(cls("Work item 7 not found"))
    assert (got.status_code, got.detail) == (code, "Work item 7 not found")


@pytest.mark.parametrize(("cls", "code", "fixed"), _CASES, ids=_IDS)
def test_a_service_error_with_public_detail_gets_exactly_that_text(cls, code, fixed) -> None:
    got = http_error(_public(cls)(_LEAKY))
    assert (got.status_code, got.detail) == (code, "Shown to the caller")


def test_a_not_authorised_error_is_403_forbidden() -> None:
    got = http_error(NotAuthorisedError(_LEAKY))
    assert (got.status_code, got.detail) == (403, "Forbidden")


def test_an_invalid_graph_keeps_its_structured_errors_and_not_the_joined_message() -> None:
    got = http_error(GraphInvalid(["step a has no lane", "edge b is dangling"]))
    assert got.status_code == 422
    assert got.detail == {"errors": ["step a has no lane", "edge b is dangling"]}


def test_an_unknown_exception_is_raised_not_mapped() -> None:
    with pytest.raises(RuntimeError):
        http_error(RuntimeError(_LEAKY))
