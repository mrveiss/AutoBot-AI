# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contrast half of the frontend/service-only path guard (#13365).

``frontend_service_only_path_guard_test.py`` runs the detector against the
live ``EXEMPT_PATHS``/``SERVICE_ONLY_PATHS`` lists and the real frontend call
set, which is green today -- and a detector shown only a green tree has proved
nothing; it could return an empty set unconditionally and that test would
still pass. This file feeds it a synthetic table reproducing the exact shape
of the #13365 defect (one of three siblings left off ``EXEMPT_PATHS``), plus
the cases that must NOT trip it.
"""

from __future__ import annotations

from repo_tests.frontend_service_only_path_guard_test import rejected_frontend_calls

__all__: list[str] = []

_EXEMPT = ["/api/npu/workers", "/api/npu/load-balancing"]
_SERVICE_ONLY = ["/api/npu/status", "/api/npu/results"]


def test_a_service_only_path_the_frontend_calls_with_no_exempt_entry_is_a_finding() -> None:
    """The #13365 shape: one of three siblings never made it into EXEMPT_PATHS."""
    assert rejected_frontend_calls({"/api/npu/status"}, _EXEMPT, _SERVICE_ONLY) == {"/api/npu/status"}


def test_a_frontend_call_matching_both_lists_is_saved_by_the_exempt_entry() -> None:
    """An EXEMPT_PATHS entry saves a call even where a SERVICE_ONLY_PATHS entry also
    matches it -- the shape the real fix leaves behind is clean (npu/status was moved
    out of SERVICE_ONLY_PATHS entirely), but the detector must not depend on that."""
    assert rejected_frontend_calls({"/api/npu/workers"}, _EXEMPT, ["/api/npu/workers", *_SERVICE_ONLY]) == set()


def test_a_frontend_call_matching_neither_list_is_never_a_finding() -> None:
    """An ordinary frontend path must not trip the guard."""
    assert rejected_frontend_calls({"/api/chats"}, _EXEMPT, _SERVICE_ONLY) == set()
