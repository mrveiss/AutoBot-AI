# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A mounted `*_mcp` router cannot silently skip governance (#14586).

`manual_mcp` reached production excluded from `mcp_bridge_scan.bridge_files()`
by a bare `if p.stem != "manual_mcp"` — no comment, no test pinning the
choice, no coverage. `EXCLUDED_BRIDGE_STEMS` replaces that inline check with
an auditable table; this module is what makes the table load-bearing rather
than decorative.

Two things are checked, statically (no FastAPI app import — the router
registry modules pull in the full dependency tree of every bridge, which is
unnecessary weight for a source-text cross-check):

1. `EXCLUDED_BRIDGE_STEMS` cannot silently grow: every entry needs a real
   reason string, and it must not name a bridge already governed.
2. Every `*_mcp` router actually mounted in `core_routers.py` /
   `mcp_routers.py` is either governed (`bridge_files()` finds its source)
   or named in `EXCLUDED_BRIDGE_STEMS`. A new bridge added to the router
   registry without either lands here as a hard failure, not a silent gap.
"""

from __future__ import annotations

import pathlib
import re

from autobot_shared.auth.mcp_bridge_scan import (
    BRIDGE_DIR,
    EXCLUDED_BRIDGE_STEMS,
    bridge_files,
    bridge_name,
)

_ROUTER_REGISTRY_DIR = pathlib.Path(__file__).resolve().parents[2] / "autobot-backend" / "initialization" / "router_registry"
_CORE_ROUTERS = _ROUTER_REGISTRY_DIR / "core_routers.py"
_MCP_ROUTERS = _ROUTER_REGISTRY_DIR / "mcp_routers.py"

# `"api.manual_mcp"` (a dynamic import string) or `manual_mcp_router` (a
# module-level import alias) — the two shapes the registry uses to mount a
# bridge. Candidates are then intersected with real `*_mcp.py`/`*_mcp/`
# sources so an unrelated identifier merely ending in `_mcp` (e.g.
# `autobot_mcp_router.py`, which is not a bridge glob matches at all) cannot
# false-positive.
_MODULE_REF = re.compile(r'"api\.([a-z][a-z0-9_]*_mcp)"')
_VAR_REF = re.compile(r"\b([a-z][a-z0-9_]*_mcp)_router\b")


def _mounted_bridge_stems(path: pathlib.Path) -> set[str]:
    """Bridge stems referenced as a mount target in *path*'s source text."""
    src = path.read_text(encoding="utf-8")
    return set(_MODULE_REF.findall(src)) | set(_VAR_REF.findall(src))


def _real_bridge_stems() -> set[str]:
    """Every `*_mcp.py`/`*_mcp/` stem on disk, before any exclusion applies."""
    modules = {p.stem for p in BRIDGE_DIR.glob("*_mcp.py")}
    packages = {p.name for p in BRIDGE_DIR.glob("*_mcp") if p.is_dir()}
    return modules | packages


def test_excluded_bridge_stems_cannot_grow_silently():
    """Pins today's state (empty) and shapes any future entry (#14586).

    manual_mcp was the one bridge here; it is governed now, so the table is
    empty. A future exclusion is legitimate — but it has to carry a reason,
    and it cannot name a bridge `bridge_files()` already governs (that would
    be a silent no-op exclusion, indistinguishable from a typo).
    """
    assert EXCLUDED_BRIDGE_STEMS == {}, (
        "a bridge was added to EXCLUDED_BRIDGE_STEMS — update this pin once the "
        "exclusion is reviewed and intentional"
    )
    governed = {bridge_name(p) for p in bridge_files()}
    for stem, reason in EXCLUDED_BRIDGE_STEMS.items():
        assert reason.strip(), f"{stem} is excluded with no reason"
        assert stem not in governed, f"{stem} is both governed and excluded — pick one"


def test_every_mounted_mcp_router_is_governed_or_excluded():
    """A router mounted in the app must be reachable by exactly one path."""
    real_stems = _real_bridge_stems()
    mounted = (_mounted_bridge_stems(_CORE_ROUTERS) | _mounted_bridge_stems(_MCP_ROUTERS)) & real_stems
    governed = {bridge_name(p) for p in bridge_files()}

    ungoverned = mounted - governed - set(EXCLUDED_BRIDGE_STEMS)
    assert not ungoverned, (
        f"*_mcp router(s) mounted with neither a bridge_scan declaration nor an "
        f"EXCLUDED_BRIDGE_STEMS entry: {sorted(ungoverned)} — see "
        "autobot_shared/auth/mcp_bridge_scan.py"
    )


def test_manual_mcp_is_governed_not_excluded():
    """#14586: pins the actual decision this issue made, not just its shape."""
    assert "manual_mcp" not in EXCLUDED_BRIDGE_STEMS
    assert "manual_mcp" in {bridge_name(p) for p in bridge_files()}
