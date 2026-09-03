# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Deployed-directory resolvers, split by READ vs WRITE intent (#13539 B2).

Extracted out of ``services/drift_checker.py`` rather than grown in place —
that module is grandfathered against the file-size ratchet (#14236) and this
split is new code, not a fix to anything already there.

``drift_checker.get_default_deployed_dir`` had ~70 call sites that all asked
the same question — "where does component X live?" — but meant two different
things: a READER asking where code is CURRENTLY served from (a status check,
a drift comparison, a health probe), and a WRITER asking where newly-deployed
code must be PUT (an rsync destination, a build output directory, a deploy
marker). Today both get the same answer, so the distinction was invisible.
Under #13539's release scheme they diverge: a reader must resolve through the
live ``current`` pointer, a writer must target a staging release and must
NEVER touch the live serving tree. #15092's containment guard — the test that
a deploy destination never resolves inside the live tree — has nothing to
assert on until the two are distinguishable in code, not just in a docstring
promise. That is why this split exists, and why it exists before any writer
call site changes (#13539 §15, blocker B2).

On today's flat layout both forms return the exact same value — see
``deployed_dir_resolver_test.py``'s agreement tests, the "unchanged today"
proof the split requires. The split is vocabulary now; it becomes behaviour
once #13539's release scheme lands.
"""

from __future__ import annotations

import os
from pathlib import Path

from services.drift_checker import _NONSTANDARD_COMPONENT_PATHS


def _resolve_deployed_dir(component: str = "autobot-slm-backend") -> str:
    """Shared path arithmetic behind both public resolvers below.

    Reads ``SLM_DEPLOYED_ROOT`` from the environment so the path is
    configurable without hardcoding. Components listed in
    ``_NONSTANDARD_COMPONENT_PATHS`` (#12450, owned by ``drift_checker``) use
    their verified override sub-path instead of the standard
    ``<root>/<component>`` convention.

    Private: callers must go through :func:`get_live_dir` (readers) or
    :func:`get_release_component_dir` (writers) — never this directly — so
    the read/write distinction stays enforced at the one place both funnel
    through, even though today (flat layout) they compute the same value.
    """
    deployed_root = os.environ.get("SLM_DEPLOYED_ROOT", "/opt/autobot")
    override = _NONSTANDARD_COMPONENT_PATHS.get(component)
    rel_path = override[1] if override else component
    return str(Path(deployed_root) / rel_path)


def get_live_dir(component: str = "autobot-slm-backend") -> str:
    """Return where *component*'s code is CURRENTLY being served from (a READ).

    For status checks, drift comparisons, health probes and anything else
    that asks "what is live right now?" Under #13539's release scheme this
    resolves through the live ``current`` pointer; on today's flat layout it
    is identical to :func:`get_release_component_dir`.

    Never use this to pick an rsync destination, a build output directory or
    any other write target — that is :func:`get_release_component_dir`. A
    reader given a writer's answer would silently start reading the wrong
    tree once the two diverge.

    Args:
        component: Sub-directory name under the deployed root.

    Returns:
        Absolute path string for the currently-served component directory.
    """
    return _resolve_deployed_dir(component)


def get_release_component_dir(component: str = "autobot-slm-backend") -> str:
    """Return where code being deployed for *component* must be WRITTEN.

    For rsync destinations, build/publish output directories, and deploy
    markers — anything that asks "where do I put code I am deploying?".
    Under #13539's release scheme this must resolve to a staging release and
    must NEVER resolve inside the live serving tree (#15092's containment
    guard); on today's flat layout it is identical to :func:`get_live_dir`.

    Never use this to check what is currently serving — that is
    :func:`get_live_dir`. A writer routed to the reader's answer is exactly
    the defect #15092 exists to catch.

    Args:
        component: Sub-directory name under the deployed root.

    Returns:
        Absolute path string for the deploy destination directory.
    """
    return _resolve_deployed_dir(component)
