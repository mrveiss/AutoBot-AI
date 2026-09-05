# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every path the frontend calls survives service-auth enforcement (#13365).

``/api/npu/status`` sat in ``SERVICE_ONLY_PATHS``
(``middleware/service_auth_enforcement.py``) with no ``EXEMPT_PATHS`` entry to
save it, while its two siblings (``/api/npu/workers``,
``/api/npu/load-balancing`` -- same ``check_admin_permission`` dependency, same
browser-facing debug panel) were exempt. Service-auth enforcement 401s that
call in production; nothing cross-referenced the frontend's own API surface
against these two lists, so the third sibling drifted unnoticed.

Every guard here is two pieces (#15671): a pure detector taking the frontend
call set and the two path lists as arguments, and a test that hands it the
live tree. ``frontend_service_only_path_guard_contrast_test.py`` supplies a
fixture that SHOULD trip the detector and one that must not; this file
supplies the live half.

The floor below is bound to the sweep's REACH -- the number of frontend calls
discovered -- never to the count of findings. A floor bound to findings passes
in silence the moment the scanner starts returning nothing.
"""

from __future__ import annotations

from typing import Iterable

from middleware.service_auth_enforcement import EXEMPT_PATHS, SERVICE_ONLY_PATHS
from scripts.audit_api_wiring import frontend_calls

__all__: list[str] = []

#: #13365 measured 740 real frontend /api/ calls; set well below that so an
#: unrelated frontend refactor cannot trip this on call-count churn alone.
_MIN_FRONTEND_CALLS = 500


def _reached(measured: int, minimum: int, what: str) -> None:
    """State the sweep's reach before comparing findings against it.

    Bound to entries discovered, never to findings -- see module docstring.
    """
    assert measured >= minimum, f"the sweep reached only {measured} {what} (floor {minimum}) — it has stopped reading"


def rejected_frontend_calls(
    frontend_paths: Iterable[str],
    exempt_paths: Iterable[str],
    service_only_paths: Iterable[str],
) -> set[str]:
    """Frontend-called paths service-auth enforcement would 401 (#13365).

    Mirrors ``is_path_exempt()``/``requires_service_auth()`` in
    ``middleware/service_auth_enforcement.py`` -- prefix match, not equality --
    so a caller can feed it either the real lists or a synthetic table.
    """

    def _matches(path: str, patterns: Iterable[str]) -> bool:
        return any(path.startswith(pattern) for pattern in patterns)

    return {
        path
        for path in frontend_paths
        if _matches(path, service_only_paths) and not _matches(path, exempt_paths)
    }


def test_every_frontend_call_is_exempt_or_absent_from_service_only_paths() -> None:
    """A frontend call service-auth enforcement would reject is a finding."""
    calls = frontend_calls()
    _reached(len(calls), _MIN_FRONTEND_CALLS, "frontend /api/ calls")
    rejected = rejected_frontend_calls(set(calls), EXEMPT_PATHS, SERVICE_ONLY_PATHS)
    assert not rejected, (
        "These frontend-called paths match SERVICE_ONLY_PATHS with no EXEMPT_PATHS "
        "entry to save them -- service-auth enforcement 401s them in production. "
        "Either add the path to EXEMPT_PATHS (middleware/service_auth_enforcement.py) "
        "if it is genuinely browser-facing, or stop calling it from the frontend if it "
        "is genuinely service-only (#13365):\n  "
        + "\n  ".join(f"{path} ({', '.join(sorted(calls[path]))})" for path in sorted(rejected))
    )
