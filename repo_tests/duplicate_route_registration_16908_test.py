# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nothing registers the same (method, path) twice on the backend (#16908).

FastAPI matches routes in registration order: the first module to claim a
``(method, path)`` pair serves it, and every later registration at the same
pair is dead code that reads as a live endpoint. #16908 found four such pairs
by hand (``core_routers.py``/``feature_routers.py`` parsed for both
registration-tuple forms) and fixed them; this guard is what stops a fifth.

## Population and its cross-check

Uses ``api/codebase_analytics/api_endpoint_scanner.py::BackendEndpointScanner``
— the same scanner ``scripts/audit_api_wiring.py``'s STATIC mode and the
``api-wiring`` blocking CI gate already trust — rather than a fifth private
router-prefix parser (``repo_tests/router_prefix_convergence_test.py``, #12985,
exists specifically to stop that pattern from repeating). #16908's own
inventory, parsing only the two registration-tuple forms by hand, reached 71%
coverage (249 of 347 router-bearing modules) and reported 4 duplicates; this
scanner resolves every ``@router.<verb>`` decorator against its module's
registered prefix, including external/registry-mounted routers, and reports 8.

Cross-checked once, per ``RATCHET_BASELINES.md`` rule 3 (derive the
population a second way before trusting a detector's own count): a raw
``grep -rE "@(router|app)\\.(get|post|put|delete|patch|websocket)\\("`` across
``autobot-backend`` (excluding test files) finds 2413 decorator occurrences
against the scanner's ~2296 resolved endpoints -- 95% agreement, not 71%.

## Scope boundary

Covers everything ``api/codebase_analytics/api_endpoint_scanner.py`` resolves
under ``autobot-backend/api/`` plus its ``_external_router_prefixes`` (LLC and
other registry-mounted routers outside ``api/``). It does **not** claim
completeness beyond what that scanner resolves -- #16913 (the follow-up this
guard's baseline references) found one pair (``llc/api/agent_api.py`` vs
``llc/api/context.py``) that #16908's own by-hand precedence tracing had not
yet placed under a registration mechanism, so "this guard passes" means "no
NEW duplicate beyond the known baseline", not "every router in the codebase is
provably collision-free".
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import pytest
from repo_tests._paths import repo_root

_BACKEND = repo_root() / "autobot-backend"

# #16913: four duplicates the scanner already finds, not yet resolved -- each
# needs the same registration-order tracing #16908's body did for its own four
# rows before it can be fixed, not a guess here. Shrinks by one entry per pair
# #16913 resolves, down to empty; test_the_baseline_has_no_stale_entries below
# fails the moment one stops being a real duplicate, so a fix that forgets to
# remove its baseline line is caught rather than silently over-exempted.
KNOWN_DUPLICATE_BASELINE: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/cache/stats"),
        ("GET", "/api/llc/agent/context/{item_id}"),
        ("GET", "/api/mcp/tools"),
        ("POST", "/api/voice/realtime/tools/call"),
    }
)


def _scan_duplicates() -> dict[tuple[str, str], list[str]]:
    """{(method, path): [file_path, ...]} for every pair served by >1 module."""
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from api.codebase_analytics.api_endpoint_scanner import BackendEndpointScanner

    endpoints = BackendEndpointScanner().scan_all_endpoints()
    assert len(endpoints) > 2000, (
        f"only {len(endpoints)} endpoints scanned -- the scanner's own population "
        "collapsed (a broken import, an empty tree); a guard silently sweeping "
        "nothing is worse than not running (see MEASUREMENT_DISCIPLINE.md)"
    )

    by_path: dict[tuple[str, str], list[str]] = defaultdict(list)
    for endpoint in endpoints:
        by_path[(endpoint.method, endpoint.path)].append(endpoint.file_path)

    return {key: files for key, files in by_path.items() if len(set(files)) > 1}


def test_no_new_duplicate_route_registration():
    duplicates = _scan_duplicates()
    unbaselined = {key: files for key, files in duplicates.items() if key not in KNOWN_DUPLICATE_BASELINE}

    assert not unbaselined, (
        "these (method, path) pairs are registered by more than one module. "
        "FastAPI matches in registration order, so only the first is reachable "
        "and every later one is dead code that reads as a live endpoint "
        "(#16908):\n"
        + "\n".join(
            f"  {method} {path}: {sorted(set(files))}" for (method, path), files in sorted(unbaselined.items())
        )
    )


def test_the_baseline_has_no_stale_entries():
    """A baseline entry that stops matching a real duplicate must be removed,
    not left to quietly exempt whatever future pair happens to reuse its
    (method, path) -- the exact blind spot RATCHET_BASELINES.md rule 1 warns
    freezing a detector's own baseline can hide.
    """
    duplicates = _scan_duplicates()
    stale = KNOWN_DUPLICATE_BASELINE - duplicates.keys()

    assert not stale, (
        "these baseline entries no longer match a real duplicate -- remove them "
        f"from KNOWN_DUPLICATE_BASELINE (#16913 progress): {sorted(stale)}"
    )


def test_a_deliberate_duplicate_is_caught_naming_both_modules():
    """Mutation proof (#16908 AC4): fabricate one collision and confirm the
    detector reports it, naming both sides -- not just that *some* assertion
    fails.
    """
    if str(_BACKEND) not in sys.path:
        sys.path.insert(0, str(_BACKEND))
    from api.codebase_analytics.api_endpoint_scanner import BackendEndpointScanner
    from api.codebase_analytics.models import APIEndpointItem

    real_endpoints = BackendEndpointScanner().scan_all_endpoints()
    planted = APIEndpointItem(
        method="GET",
        path="/api/admin/schedulers",
        file_path="autobot-backend/api/_test_planted_duplicate.py",
        line_number=1,
        function_name="_planted",
    )

    with patch.object(BackendEndpointScanner, "scan_all_endpoints", return_value=[*real_endpoints, planted]):
        duplicates = _scan_duplicates()

    key = ("GET", "/api/admin/schedulers")
    assert key in duplicates, "the planted duplicate was not detected"
    assert "autobot-backend/api/_test_planted_duplicate.py" in duplicates[key]
    assert any(
        f.endswith("scheduler_toggles.py") for f in duplicates[key]
    ), f"expected the real scheduler_toggles.py registration alongside the plant, got {duplicates[key]}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
