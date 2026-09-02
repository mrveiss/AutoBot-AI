# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every SLM REST caller goes through one prefix decision (#13584, #14039).

Two failures are pinned here, and only the second one is cheap to see.

* The **behaviour**: behind nginx the SLM lives under ``/slm``, so a call site
  that hardcodes ``/api`` 404s on exactly the deployments an operator is least
  able to debug. A test that only exercised the direct-uvicorn form would pass
  before and after the fix, because that form never carried the bug — the
  proxy-form assertions are the ones that pin it.
* The **spread**: #13584 fixed the six call sites inside ``slm_client.py`` and
  left seven more in five other files, because the decision was private to a
  module they could not import. Fixing the seven without a sweep would leave
  the eighth free to reappear. So the sweep below reads the tree, not a list.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from autobot_shared.slm_rest_url import is_direct_uvicorn_url, rest_url

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Directories a hardcoded ``{slm_url}/api/`` could hide in.
_SWEPT_TREES = ("autobot-backend", "scripts")

#: Floor for the sweep's own population. A glob that silently matches nothing
#: reports "no hardcoded prefixes" in exactly the same words as a clean tree.
_MIN_SWEPT_FILES = 500

#: The f-string shapes #13584 and #14039 were reported as. Each one is a REST
#: URL glued together by hand instead of asked for.
_HARDCODED_SHAPES = (
    'f"{slm_url}/api/',
    'f"{self.slm_url}/api/',
    'f"{client.slm_url}/api/',
)

#: One call site per file that #14039 named, with the token that now carries it.
#: ``slm_policy`` holds a live client, so it uses the instance method (AC3);
#: the rest hold a bare URL string and use the module-level helper.
_MIGRATED_CALL_SITES = {
    "autobot-backend/llc/services/slm_policy.py": 'client._rest_url(f"/api/settings/',
    "autobot-backend/orchestration/dag_executor.py": 'rest_url(slm_url, f"/api/nodes/',
    "autobot-backend/services/redis_service_manager.py": 'rest_url(self.slm_url, f"/api/nodes/',
    "autobot-backend/services/skill_management/skill_proposer.py": 'rest_url(slm_url, "/api/skills/propose")',
    "scripts/daily_health_check.py": 'rest_url(self.slm_url, "/api/health")',
}

#: A representative path per migrated file, proxy form and direct form.
_PER_FILE_PATHS = {
    "autobot-backend/llc/services/slm_policy.py": "/api/settings/disposal_policy",
    "autobot-backend/orchestration/dag_executor.py": "/api/nodes/node-1/execute",
    "autobot-backend/services/redis_service_manager.py": "/api/nodes/node-1/services",
    "autobot-backend/services/skill_management/skill_proposer.py": "/api/skills/propose",
    "scripts/daily_health_check.py": "/api/health",
}


def _swept_python_files() -> list[Path]:
    """Every ``*.py`` under the trees a hardcoded prefix could hide in."""
    found: list[Path] = []
    for tree in _SWEPT_TREES:
        found.extend(
            path
            for path in (_REPO_ROOT / tree).rglob("*.py")
            if "__pycache__" not in path.parts and "node_modules" not in path.parts
        )
    return found


# ---------------------------------------------------------------------------
# The decision itself
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel,path", sorted(_PER_FILE_PATHS.items()))
def test_a_proxy_form_url_gets_the_slm_prefix(rel: str, path: str) -> None:
    """The regression case: before #13584/#14039 this returned /api/... and 404'd."""
    assert rest_url("https://slm.internal:443", path) == f"https://slm.internal:443/slm{path}", (
        f"{rel}: behind nginx this endpoint must be requested under /slm — "
        "the un-prefixed form is served by the USER backend, not the SLM"
    )


@pytest.mark.parametrize("rel,path", sorted(_PER_FILE_PATHS.items()))
def test_a_direct_uvicorn_url_keeps_the_bare_prefix(rel: str, path: str) -> None:
    """uvicorn has no /slm route at all, so the prefix must not be added blindly."""
    assert rest_url("http://autobot-slm:8000", path) == f"http://autobot-slm:8000{path}", f"{rel}: #10459"


def test_a_trailing_slash_does_not_double_up() -> None:
    assert rest_url("https://slm.internal:443/", "/api/health") == "https://slm.internal:443/slm/api/health"


def test_a_path_without_a_leading_slash_is_still_joined_cleanly() -> None:
    assert rest_url("http://autobot-slm:8000", "api/health") == "http://autobot-slm:8000/api/health"


def test_the_nginx_port_still_beats_the_loopback_heuristic() -> None:
    """#12781 in one assertion — a co-located nginx on loopback:443 is not uvicorn."""
    assert is_direct_uvicorn_url("https://127.0.0.1:443") is False
    assert is_direct_uvicorn_url("http://127.0.0.1:8000") is True


# ---------------------------------------------------------------------------
# The spread
# ---------------------------------------------------------------------------


def test_no_rest_url_is_still_built_by_hand() -> None:
    """The sweep #13584 stopped short of, run over the tree rather than a list."""
    swept = _swept_python_files()
    assert len(swept) >= _MIN_SWEPT_FILES, (
        f"FIX THE SWEEP: only {len(swept)} Python files reached under {_SWEPT_TREES} — "
        f"expected at least {_MIN_SWEPT_FILES}. A collapsed walk reports a clean "
        "tree in the same words as a clean tree."
    )

    offenders: dict[str, list[str]] = {}
    for path in swept:
        if path.name.endswith("_test.py"):
            continue  # the shapes are quoted in this file and in slm_client_test.py
        source = path.read_text(encoding="utf-8", errors="replace")
        hits = [shape for shape in _HARDCODED_SHAPES if shape in source]
        if hits:
            offenders[str(path.relative_to(_REPO_ROOT))] = hits

    assert offenders == {}, (
        f"REST URLs built by hand instead of through rest_url(): {offenders}. "
        "Behind nginx every one of them 404s — #13584, #14039."
    )


@pytest.mark.parametrize("rel,token", sorted(_MIGRATED_CALL_SITES.items()))
def test_each_named_call_site_routes_through_the_helper(rel: str, token: str) -> None:
    """Pin the seven sites #14039 named, so a revert is a red test and not a 404."""
    path = _REPO_ROOT / rel
    assert path.is_file(), f"FIX THE SWEEP: {rel} moved or was deleted — re-point this guard"
    source = path.read_text(encoding="utf-8")
    assert token in source, f"{rel}: expected the migrated call site {token!r} — #14039"


def test_the_client_still_re_exports_the_helper() -> None:
    """``from services.slm_client import rest_url`` is #14039 AC1's named path."""
    source = (_REPO_ROOT / "autobot-backend" / "services" / "slm_client.py").read_text(encoding="utf-8")
    assert "from autobot_shared.slm_rest_url import rest_url" in source
    assert "return rest_url(self.slm_url, path)" in source, "_rest_url must delegate, not re-decide"
