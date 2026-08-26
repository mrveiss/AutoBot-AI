#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provision the access control enforcement mode (#14866).

The enforcement posture is read from a single Redis key. Nothing that runs at
install time has ever written it, so every install has been sitting at the
*unset* default -- which resolves to ``disabled`` and short-circuits every
gated ownership check before the lookup. This entry point is what makes the
posture a value the install was **given** rather than one it fell back to.

It does not change what an unset key or ``log_only`` mean: it stops *unset*
from being the production state.

Idempotent by construction: the write is ``SET NX``, so a re-provision leaves
an operator's deliberate value exactly as it found it.

Usage:
    python scripts/security/seed_enforcement_mode.py [options]

Options:
    --mode MODE   Posture to seed: disabled, log_only or enforced.
                  Defaults to ACCESS_CONTROL_ENFORCEMENT_MODE, then to the
                  value recorded in services.feature_flags.
    --dry-run     Report what would happen without writing anything.

Exit codes (the provisioning role keys its ``changed`` state off these):
    0  a value was already present and was left untouched
    1  provisioning failed
    2  the key was absent and this run seeded it
"""

import argparse
import asyncio
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_DIR = _REPO_ROOT / "autobot-backend"
for _entry in (str(_REPO_ROOT), str(_BACKEND_DIR)):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

from autobot_shared.logging_manager import get_logger  # noqa: E402
from services.feature_flags import (  # noqa: E402
    EnforcementMode,
    FeatureFlags,
    resolve_provisioned_enforcement_mode,
)

logger = get_logger(__name__)

EXIT_UNCHANGED = 0
EXIT_FAILED = 1
EXIT_SEEDED = 2


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the operator arguments for this entry point."""
    parser = argparse.ArgumentParser(description="Provision the access control enforcement mode")
    parser.add_argument(
        "--mode",
        default=None,
        help="Posture to seed: " + ", ".join(mode.value for mode in EnforcementMode),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report the outcome without writing the flag",
    )
    return parser.parse_args(argv)


async def _seed(target: EnforcementMode, dry_run: bool) -> tuple[bool, EnforcementMode]:
    """Run the seeding call against the flag store."""
    return await FeatureFlags().seed_enforcement_mode(target, dry_run=dry_run)


def main(argv: list[str] | None = None) -> int:
    """Seed the enforcement mode, reporting the outcome through the exit code."""
    args = _parse_args(sys.argv[1:] if argv is None else argv)

    try:
        target = resolve_provisioned_enforcement_mode(args.mode)
        written, effective = asyncio.run(_seed(target, args.dry_run))
    except Exception as exc:  # noqa: BLE001 - an operator entry point reports, it does not raise
        logger.error("Could not provision the access control enforcement mode: %s", exc)
        return EXIT_FAILED

    prefix = "dry run: would " if args.dry_run else ""
    if written:
        logger.info("%sseed access control enforcement mode as %s", prefix, effective.value)
        return EXIT_SEEDED

    logger.info("%sleave access control enforcement mode at %s (already provisioned)", prefix, effective.value)
    return EXIT_UNCHANGED


if __name__ == "__main__":
    sys.exit(main())
