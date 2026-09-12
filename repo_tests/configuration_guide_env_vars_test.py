# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every AUTOBOT_* name docs/guides/CONFIGURATION_GUIDE.md documents must be real (#15151).

`AUTOBOT_PLAYWRIGHT_HOST` and `AUTOBOT_PLAYWRIGHT_API_PORT` were documented as
configurable knobs with nothing behind them anywhere in the tree: not
registered in `env_registry.py`, not read by any Python/TypeScript/shell code,
not present in any tracked `.env*` file. Setting either had no effect
anywhere. The same investigation found seven more names in the same shape
(`AUTOBOT_CHROME_DEBUG_PORT`, `AUTOBOT_LM_STUDIO_HOST`/`PORT`,
`AUTOBOT_LOG_VIEWER_HOST`/`PORT`, `AUTOBOT_PLAYWRIGHT_VNC_PORT`,
`AUTOBOT_REDIS_PROTOCOL`, `AUTOBOT_WS_PROTOCOL`) and removed them too, plus one
that was real but misnamed (`AUTOBOT_PLAYWRIGHT_VNC_PORT` -> the actual
`AUTOBOT_VNC_PORT`, same 6080 default).

WHY _KNOWN_UNREGISTERED_BUT_REAL EXISTS
----------------------------------------
A separate class of name is real (read by actual code) but still absent from
`env_registry.REGISTRY` -- a registry-completeness gap, not a dead knob. Filed
as #16439 rather than fixed here: registering each properly means picking its
component and validating its default/type, which is that issue's job, not a
doc-accuracy fix's. Shrinks only, as each gets registered.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_GUIDE_PATH = repo_root() / "docs" / "guides" / "CONFIGURATION_GUIDE.md"

_AUTOBOT_NAME_RE = re.compile(r"\bAUTOBOT_[A-Z0-9_]+\b")

#: Documented, real (something reads it), but not yet in env_registry.REGISTRY.
#: Tracked by #16439. Remove a name here only when it is registered there.
_KNOWN_UNREGISTERED_BUT_REAL = frozenset(
    {
        "AUTOBOT_AI_STACK_HOST",
        "AUTOBOT_AI_STACK_PORT",
        "AUTOBOT_API_BASE_URL",
        "AUTOBOT_FLUENTD_PORT",
        "AUTOBOT_FRONTEND_HOST",
        "AUTOBOT_FRONTEND_PORT",
        "AUTOBOT_HTTP_PROTOCOL",
        "AUTOBOT_NPU_WORKER_HOST",
        "AUTOBOT_NPU_WORKER_PORT",
        "AUTOBOT_OLLAMA_HOST",
        "AUTOBOT_OLLAMA_PORT",
        # Registered in ssot_config.py's MiscConfig (default 6080), not in
        # env_registry.REGISTRY -- a different config system than this test
        # checks against. Real, just not registered where AC1 asked for.
        "AUTOBOT_VNC_PORT",
    }
)


def _documented_names() -> set[str]:
    text = _GUIDE_PATH.read_text(encoding="utf-8")
    return set(_AUTOBOT_NAME_RE.findall(text))


def test_the_guide_exists() -> None:
    assert _GUIDE_PATH.is_file(), f"{_GUIDE_PATH} not found -- did it move?"


def test_the_extraction_found_names() -> None:
    """An empty extraction would make every assertion below pass vacuously."""
    assert _documented_names(), "no AUTOBOT_* name found in the configuration guide -- regex or guide drifted"


def test_every_documented_name_is_registered_or_explicitly_tracked_as_a_gap() -> None:
    from autobot_shared.env_registry import REGISTRY

    documented = _documented_names()
    unaccounted = sorted(documented - set(REGISTRY) - _KNOWN_UNREGISTERED_BUT_REAL)
    assert not unaccounted, (
        f"{unaccounted} are documented in {_GUIDE_PATH} but neither registered in "
        "env_registry.REGISTRY nor listed in _KNOWN_UNREGISTERED_BUT_REAL above. "
        "Register it, or if it is a genuine gap like #16439's, add it to the "
        "allowlist with a tracking issue -- never leave a documented name "
        "unaccounted for silently."
    )


def test_the_known_gap_allowlist_has_not_gone_stale() -> None:
    """The other direction: an allowlisted name that got registered must be
    dropped, or the list stops meaning "still a gap" and starts meaning
    nothing (#16439 tracks each one's removal)."""
    from autobot_shared.env_registry import REGISTRY

    now_registered = sorted(_KNOWN_UNREGISTERED_BUT_REAL & set(REGISTRY))
    assert not now_registered, (
        f"{now_registered} are now registered -- remove them from "
        "_KNOWN_UNREGISTERED_BUT_REAL, the list only shrinks"
    )


def test_the_known_gap_allowlist_has_no_dead_names() -> None:
    """The allowlist is for real-but-unregistered names, not a place a
    removed/renamed name can hide instead of being deleted from the guide."""
    documented = _documented_names()
    stale = sorted(_KNOWN_UNREGISTERED_BUT_REAL - documented)
    assert not stale, f"{stale} are in _KNOWN_UNREGISTERED_BUT_REAL but no longer documented -- drop them"
