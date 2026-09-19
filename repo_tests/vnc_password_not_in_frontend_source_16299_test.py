# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No VNC password reaches the frontend bundle (#16299).

Vite compiles every ``import.meta.env.VITE_*`` reference into the built
bundle regardless of whether the surrounding code path is reachable at
runtime, so a `VITE_*_VNC_PASSWORD` reference anywhere in the frontend
source is a guaranteed leak the moment it's built -- checked at the source
level rather than by grepping a built ``dist/`` directory, since a source
reference is a strictly necessary precondition for it ever reaching build
output, and this guard runs reliably without a build step (this environment
has no ``node_modules`` to run one).

The backend now authenticates to the real VNC server itself and offers the
browser security-type "None" (``api/vnc_handshake_bridge.py``) -- the
browser never needs a password, so no source file should reference one.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root
from repo_tests._reach import declare

from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

REPO_ROOT = repo_root()

#: Every VITE_ env var name #16299's own issue table named as leaking a VNC
#: credential to the browser bundle.
FORBIDDEN_PATTERN = re.compile(r"VITE_(?:DESKTOP|TERMINAL|PLAYWRIGHT)_VNC_PASSWORD")


def _frontend_source_files(root) -> list[str]:
    try:
        tracked = tracked_paths(root, "autobot-frontend/src/*.vue")
        tracked += tracked_paths(root, "autobot-frontend/src/*.ts")
        tracked += tracked_paths(root, "autobot-frontend/src/*.js")
    except EmptyEnumeration:
        return []
    return sorted(set(tracked))


#: Bound at the 1,411 .vue/.ts/.js files measured under autobot-frontend/src/
#: when this guard was introduced (#16299).
REACH = declare(
    "vnc-password-not-in-frontend-source",
    discover=_frontend_source_files,
    floor=1411,
    growth=150,
    skips=0,
    what="frontend .vue/.ts/.js source files",
)


def test_no_frontend_source_file_references_a_vnc_password_env_var() -> None:
    files = REACH.examined(REPO_ROOT)
    offenders: list[str] = []
    for rel in files:
        text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        if FORBIDDEN_PATTERN.search(text):
            offenders.append(rel)
    REACH.completed(len(files))

    assert not offenders, (
        "these frontend source files still reference a VITE_*_VNC_PASSWORD env var, which Vite "
        "compiles into the built bundle regardless of whether the surrounding code path is "
        "reachable -- the backend now authenticates server-side (#16299), so the browser never "
        "needs one:\n  " + "\n  ".join(offenders)
    )


def test_negative_control_the_pattern_actually_matches() -> None:
    """Proves the regex can fire, not just always pass on the real tree."""
    assert FORBIDDEN_PATTERN.search("import.meta.env.VITE_DESKTOP_VNC_PASSWORD")
    assert FORBIDDEN_PATTERN.search("getEnv('VITE_TERMINAL_VNC_PASSWORD', 'autobot')")
    assert FORBIDDEN_PATTERN.search("VITE_PLAYWRIGHT_VNC_PASSWORD")
    assert not FORBIDDEN_PATTERN.search("VITE_DESKTOP_VNC_HOST")
    assert not FORBIDDEN_PATTERN.search("VITE_DESKTOP_VNC_PORT")
