# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every AUTOBOT_* name CONFIGURATION_GUIDE.md documents is real (#15151).

#15151 found three names (AUTOBOT_PLAYWRIGHT_HOST, AUTOBOT_PLAYWRIGHT_API_PORT,
AUTOBOT_PLAYWRIGHT_VNC_PORT) that the guide documented but nothing read --
"referenced is not the same as working." A name here is either registered in
autobot_shared.env_registry.REGISTRY, or listed in _KNOWN_GAPS naming the
issue tracking it -- never silently both undocumented AND unchecked.
"""

from __future__ import annotations

import re

import autobot_shared.env_registry  # noqa: F401 -- side-effecting import populates REGISTRY
from autobot_shared.env_registry import REGISTRY
from autobot_shared.paths import project_root

GUIDE_PATH = "docs/guides/CONFIGURATION_GUIDE.md"

#: Names #15151 traced and found unregistered, but did not resolve -- tracked
#: by #16554, which each needs the same per-name trace #15151 did for its
#: three (a name here may turn out registered under a different name, dead,
#: or a shape env_registry.py's plain str/int/bool/float spec doesn't fit).
_KNOWN_GAPS = {
    "AUTOBOT_AI_STACK_HOST": "#16554",
    "AUTOBOT_AI_STACK_PORT": "#16554",
    "AUTOBOT_API_BASE_URL": "#16554",
    "AUTOBOT_CHROME_DEBUG_PORT": "#16554",
    "AUTOBOT_FLUENTD_PORT": "#16554",
    "AUTOBOT_FRONTEND_HOST": "#16554",
    "AUTOBOT_FRONTEND_PORT": "#16554",
    "AUTOBOT_HTTP_PROTOCOL": "#16554",
    "AUTOBOT_LM_STUDIO_HOST": "#16554",
    "AUTOBOT_LM_STUDIO_PORT": "#16554",
    "AUTOBOT_LOG_VIEWER_HOST": "#16554",
    "AUTOBOT_LOG_VIEWER_PORT": "#16554",
    "AUTOBOT_NPU_WORKER_HOST": "#16554",
    "AUTOBOT_NPU_WORKER_PORT": "#16554",
    "AUTOBOT_OLLAMA_HOST": "#16554",
    "AUTOBOT_OLLAMA_PORT": "#16554",
    "AUTOBOT_REDIS_PROTOCOL": "#16554",
    "AUTOBOT_WS_PROTOCOL": "#16554",
}


def _guide_names() -> set[str]:
    text = (project_root() / GUIDE_PATH).read_text(encoding="utf-8")
    return set(re.findall(r"\bAUTOBOT_[A-Z0-9_]+\b", text))


def test_the_guide_documents_at_least_one_name() -> None:
    assert _guide_names(), f"{GUIDE_PATH} documents no AUTOBOT_* names -- nothing for this guard to check"


def test_every_documented_name_is_registered_or_a_tracked_gap() -> None:
    names = _guide_names()
    unaccounted = names - set(REGISTRY) - set(_KNOWN_GAPS)
    assert not unaccounted, (
        f"{sorted(unaccounted)} are documented in {GUIDE_PATH} but neither registered nor a tracked "
        "gap in this file's _KNOWN_GAPS -- trace each to its real reader (or lack of one) before adding "
        "it to either set"
    )


def test_no_known_gap_has_quietly_become_registered() -> None:
    """A gap that got fixed without shrinking this list would hide the fix, not just the bug."""
    newly_registered = set(_KNOWN_GAPS) & set(REGISTRY)
    assert not newly_registered, (
        f"{sorted(newly_registered)} are now registered -- remove them from _KNOWN_GAPS as a "
        "consequence of that fix landing"
    )
