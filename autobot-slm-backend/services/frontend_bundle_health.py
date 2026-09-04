# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Is the frontend this node serves actually servable? (#15462)

Written after an outage in which `/slm/` returned 403 for hours while every
service reported healthy. nginx serves that path from the frontend's build
output directory; the directory existed and held one file — a favicon — with no
`index.html` and no `assets/`. There was nothing to serve and autoindex is off,
so nginx answered 403 and no probe anywhere disagreed.

The cause was a deploy gap (#15464 fixed it), but the reason it ran for hours is
this: *every existing health signal was about a process*. The SLM backend was
up, Postgres answered, Redis answered, so `status` read `healthy`. Liveness and
readiness both passed. None of them looks at the artifact users actually load,
so the one thing that was broken was the one thing nothing measured.

Deliberately a filesystem check and not an HTTP fetch of the served page. The
backend would have to know its own external URL and TLS posture to fetch itself,
and a probe that depends on the proxy it is diagnosing reports "unhealthy" for
reasons that have nothing to do with the bundle. What is checked is exactly what
nginx needs: a directory containing an `index.html` with content in it.
"""

from __future__ import annotations

# stdlib logging, not autobot_shared.logging_manager: this package's test
# harness mocks the config that LoggingManager reads at import time, so the
# managed logger raises during collection. Same reason api/health.py next door
# uses stdlib, and the exception CLAUDE.md records for config-mocking harnesses.
import logging
from pathlib import Path
from typing import Optional

from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

# The build output nginx aliases for this node's UI. Relative to the SSOT
# base_dir, never a literal path (#15462 review: an absolute default here would
# be the third place the install location is written down).
#
# #15610: nginx serves `current`, a symlink the publish flips onto a per-build
# directory with one rename(2) — it replaced `dist`, which was renamed twice
# per publish and so did not exist in between. This probe follows the served
# path, because the outage it detects is "what nginx opens has no index.html".
_BUNDLE_DIR = "autobot-slm-frontend/current"

# The pre-#15610 served directory. A node that has not published since the
# migration still serves this one, and reporting `not_applicable` for it would
# silently stop probing exactly the hosts most likely to be mid-migration.
# Retired once every node has published under the new layout (#15648).
_LEGACY_BUNDLE_DIR = "autobot-slm-frontend/dist"
_ENTRY_POINT = "index.html"


def bundle_dir() -> Path:
    """The directory nginx serves, preferring the #15610 pointer."""
    current = config.path.resolve(_BUNDLE_DIR)
    if current.exists():
        return current
    legacy = config.path.resolve(_LEGACY_BUNDLE_DIR)
    return legacy if legacy.is_dir() else current


def frontend_bundle_status(directory: Optional[Path] = None) -> str:
    """``healthy`` when the bundle is servable, otherwise why it is not.

    ``not_applicable`` when this node serves no frontend at all, which must not
    drag the overall status down — see the branch comment below.

    The string is the value of ``HealthResponse.frontend`` and follows the shape
    ``_check_redis_health`` established: ``healthy``, or ``unhealthy: <reason>``
    where the reason is actionable without being a filesystem tour. Paths are
    not included — this response is public.
    """
    root = bundle_dir() if directory is None else directory
    try:
        if not root.is_dir():
            # Not "unhealthy": no build output directory at all means this node
            # does not serve the UI — a backend-only node, or a checkout. A
            # probe that is degraded by default on every such install is a probe
            # nobody reads, and this one exists precisely because the existing
            # signals had stopped being informative. The outage shape is the
            # NEXT branch, where the directory exists and holds no entry point.
            return "not_applicable: no build output directory on this node"

        entry = root / _ENTRY_POINT
        if not entry.is_file():
            # The exact shape of the outage: a directory that exists, so every
            # "is it deployed" check passes, holding no entry point.
            return "unhealthy: build output has no index.html — a build failed or was never published"

        if entry.stat().st_size == 0:
            return "unhealthy: index.html is empty — the build published a truncated bundle"
    except OSError as exc:
        logger.warning("Frontend bundle health check failed: %s", exc)
        return f"unhealthy: build output unreadable ({type(exc).__name__})"

    return "healthy"
