# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shared LLC refusal helpers answer with a fixed text or `public_detail`, never `str(exc)` (#21579)."""

import logging

import pytest

from llc.api import _common
from llc.services.work_item_hierarchy import HierarchyViolation

_MARKER = "hunter2leak"
_LEAKY = f"driver failed password={_MARKER}"


class _Public(ValueError):
    public_detail = "Shown to the caller"


@pytest.mark.parametrize(
    ("helper", "code", "fixed"),
    [
        (_common.bad_request, 400, "Invalid request"),
        (_common.forbidden, 403, "Forbidden"),
        (_common.registry_unavailable, 503, "Service unavailable"),
        (_common.refused_transition, 409, "Conflict"),
        (_common.write_refusal, 400, "Invalid request"),
    ],
    ids=["bad_request", "forbidden", "registry_unavailable", "refused_transition", "write_refusal"],
)
def test_an_exception_without_public_detail_gets_the_fixed_text(helper, code, fixed, caplog) -> None:
    with caplog.at_level(logging.WARNING):
        got = helper(ValueError(_LEAKY))
    assert (got.status_code, got.detail) == (code, fixed)
    assert _MARKER not in str(got.detail)
    assert "ValueError" in caplog.text
    assert _MARKER not in caplog.text


@pytest.mark.parametrize(
    ("helper", "code"),
    [
        (_common.bad_request, 400),
        (_common.forbidden, 403),
        (_common.registry_unavailable, 503),
        (_common.refused_transition, 409),
        (_common.write_refusal, 400),
    ],
    ids=["bad_request", "forbidden", "registry_unavailable", "refused_transition", "write_refusal"],
)
def test_an_exception_with_public_detail_gets_exactly_that_text(helper, code) -> None:
    got = helper(_Public(_LEAKY))
    assert (got.status_code, got.detail) == (code, "Shown to the caller")


def test_write_refusal_maps_a_hierarchy_violation_to_422(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        got = _common.write_refusal(HierarchyViolation(_LEAKY))
    assert (got.status_code, got.detail) == (422, "Unprocessable request")
    assert _MARKER not in str(got.detail)
    assert "HierarchyViolation" in caplog.text
    assert _MARKER not in caplog.text


def test_a_public_exception_is_not_logged_as_a_refusal(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        _common.bad_request(_Public(_LEAKY))
    assert "Refused" not in caplog.text


def test_a_status_without_a_table_entry_gets_the_default_text() -> None:
    got = _common.http_refusal(418, ValueError(_LEAKY), scope="test.scope")
    assert (got.status_code, got.detail) == (418, "Request refused")


def test_a_non_string_public_detail_is_ignored() -> None:
    exc = ValueError(_LEAKY)
    exc.public_detail = 5  # type: ignore[attr-defined]
    assert _common.http_refusal(400, exc, scope="test.scope").detail == "Invalid request"


class _Redacted(ValueError):
    @property
    def public_detail(self) -> str:
        return "Cannot run"


def test_a_public_exception_whose_detail_differs_from_its_message_logs_the_message_at_info(caplog) -> None:
    with caplog.at_level(logging.INFO):
        got = _common.http_refusal(409, _Redacted(f"agent a-42 cannot run: {_LEAKY}"), scope="tests.redacted")
    assert got.detail == "Cannot run"
    assert "_Redacted" in caplog.text
    assert "agent a-42 cannot run" in caplog.text
    assert _MARKER not in caplog.text
    assert [r.levelno for r in caplog.records] == [logging.INFO]
