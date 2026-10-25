# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A test run never dials a live install unless it says it targets one (#19479).

``integration`` tests drive whatever service listens at the configured URL. On a machine that
also runs an install that is the user's live system, and some of them write to it
(``chat_knowledge_system_e2e_test.py`` posts ``add_to_kb`` decisions). A push from such a machine
ran one against the live backend: it timed out and blocked the push, and a faster backend would
have let it write. The probe those tests call requires an explicit opt-in on top of a listener;
the behaviour is tested in ``autobot_shared/live_service_probe_test.py``, the ordering here.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

from tools.lint._scan_helpers import tracked_paths

_PROBE = repo_root() / "autobot_shared" / "live_service_probe.py"


def test_the_probe_checks_the_opt_in_before_dialling() -> None:
    source = _PROBE.read_text(encoding="utf-8")
    body = source[source.index("def require_live_endpoint") :]
    assert body.index("env_flag(LIVE_TESTS_ENV)") < body.index("endpoint_is_listening(")


#: The ungated helper's call, assembled so this file's own source never contains it.
_UNGATED = "get_test_backend_url" + "()"
#: A test that opens a connection: requests, aiohttp, httpx or websockets.
_DIALS = re.compile(
    r"\brequests\.(?:get|post|put|patch|delete)\(|aiohttp\.ClientSession\(|httpx\.|websockets\.connect\("
)


def _ungated_dialer(source: str) -> bool:
    """A file that dials and takes its backend URL from the ungated helper (trainmaster, #19508)."""
    return bool(_DIALS.search(source)) and _UNGATED in source


def test_no_dialing_test_takes_the_backend_url_ungated() -> None:
    files = tracked_paths(repo_root(), "*_test.py", "test_*.py")
    assert len(files) > 1000, f"only {len(files)} test files enumerated"
    offenders = [f for f in files if _ungated_dialer((repo_root() / f).read_text(encoding="utf-8", errors="replace"))]
    assert not offenders, f"these dial the configured backend without live_backend_url(): {offenders}"


def test_contrast_the_detector() -> None:
    assert _ungated_dialer(f'requests.get({_UNGATED} + "/x")')
    assert _ungated_dialer(f"async with aiohttp.ClientSession() as s:\n    u = {_UNGATED}")
    assert not _ungated_dialer('requests.get(live_backend_url() + "/x")')
    assert not _ungated_dialer(f'ENDPOINT = {_UNGATED} + "/mcp"  # a string handed to a mock')
