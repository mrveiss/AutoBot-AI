#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: autobot-backend must keep ``websockets<16`` while langgraph caps it (#11030).

``autobot-backend`` pulls ``langgraph`` -> ``langgraph-sdk 0.4.2`` which requires
``websockets>=14,<16``. Dependabot #10997 bypassed the ``<16`` ignore rule in
``dependabot.yml`` and bumped ``autobot-backend/requirements.txt`` to
``websockets>=16,<17``, making the graph unresolvable -> ``ResolutionImpossible``
in the backend Docker build -> smoke-test red on *every* open PR (reverted #11029).

This guard fails FAST with a clear message instead of the opaque, multi-minute
ResolutionImpossible — the durable protection requested in #11030 (option 2). It
does NOT touch the shared constraint (option 1 would break ``autobot-slm-backend``,
which legitimately pins ``websockets>=16,<17`` and does not use the shared
constraint). When ``langgraph`` is ever dropped from the backend the cap is no
longer required, so the guard auto-relaxes.

Run from the repo root:  python3 scripts/check_websockets_cap.py
Exit 0 = compliant; exit 1 = the cap is violated (or the file/pin is missing).

Security: reads repo files only; no network, no untrusted-input interpolation.
"""

from __future__ import annotations

import pathlib
import re
import sys

from packaging.requirements import Requirement

_BACKEND_REQ = pathlib.Path("autobot-backend/requirements.txt")
# The version that must remain excluded while the langgraph cap holds.
_FORBIDDEN_VERSION = "16.0"
_CAP_PKG = "websockets"
_CAP_TRIGGER_PKG = "langgraph"  # cap is only needed while this backend dep is present


def _requirement_for(pkg: str, path: pathlib.Path) -> Requirement | None:
    """Return the parsed Requirement for ``pkg`` in ``path`` (bare name match), or None."""
    if not path.exists():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        # Match a top-level requirement whose project name is exactly pkg.
        if not re.match(rf"^{re.escape(pkg)}(\[|[<>=!~ ]|$)", line, re.IGNORECASE):
            continue
        try:
            req = Requirement(line)
        except Exception:
            continue
        if req.name.lower().replace("_", "-") == pkg.lower().replace("_", "-"):
            return req
    return None


def main() -> int:
    if not _BACKEND_REQ.exists():
        print(f"ERROR: {_BACKEND_REQ} not found — run from the repo root.", file=sys.stderr)
        return 1

    langgraph = _requirement_for(_CAP_TRIGGER_PKG, _BACKEND_REQ)
    if langgraph is None:
        print(f"OK: {_CAP_TRIGGER_PKG} not present in {_BACKEND_REQ} — websockets cap no longer required.")
        return 0

    ws = _requirement_for(_CAP_PKG, _BACKEND_REQ)
    if ws is None:
        print(
            f"ERROR: {_BACKEND_REQ} declares '{_CAP_TRIGGER_PKG}' but no explicit '{_CAP_PKG}' pin.\n"
            f"       {_CAP_PKG} must be pinned '<16' (langgraph-sdk 0.4.2 requires <16). See #11030.",
            file=sys.stderr,
        )
        return 1

    if ws.specifier.contains(_FORBIDDEN_VERSION, prereleases=True):
        print(
            f"ERROR: {_BACKEND_REQ} allows {_CAP_PKG} {ws.specifier} — this permits >={_FORBIDDEN_VERSION},\n"
            f"       but {_CAP_TRIGGER_PKG} -> langgraph-sdk 0.4.2 requires websockets<16. Bumping past <16\n"
            f"       makes the backend dependency graph unresolvable (ResolutionImpossible) and breaks the\n"
            f"       Docker build on every PR (this happened via dependabot #10997; reverted #11029).\n"
            f"       Keep '{_CAP_PKG}>=15.0,<16' until langgraph-sdk widens its cap. See #11030 / #10386.",
            file=sys.stderr,
        )
        return 1

    print(
        f"OK: {_CAP_PKG} {ws.specifier} in {_BACKEND_REQ} correctly excludes >={_FORBIDDEN_VERSION} (langgraph cap held)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
