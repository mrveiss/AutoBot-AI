# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shared command-line plumbing for the GitHub drift/backfill scripts (#18158).

``scope_box_artefact_drift``, ``umbrella_label_drift`` and
``backfill_relationships`` each carried their own copy of the ``--repo`` /
``--json`` parser head, the ``GH_TOKEN or GITHUB_TOKEN`` lookup, its usage
error text and the stderr logging setup. Each script still owns its
``GitHubApi`` construction and ``EXIT_*`` codes; only the identical plumbing
lives here.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Optional

logger = logging.getLogger(__name__)

MISSING_CREDENTIALS_MESSAGE = "GH_TOKEN and --repo (or GITHUB_REPOSITORY) are required"


def base_parser(description: Optional[str], with_json: bool = True) -> argparse.ArgumentParser:
    """Parser carrying ``--repo`` (default ``GITHUB_REPOSITORY``) and, optionally, ``--json``."""
    parser = argparse.ArgumentParser(description=(description or "").splitlines()[0] if description else None)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    if with_json:
        parser.add_argument("--json", action="store_true", help="emit machine-readable output instead of a report")
    return parser


def configure_cli_logging() -> None:
    """Send bare-message INFO logging to stderr, as every drift script reports."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)


def resolve_credentials(repo: str) -> Optional[str]:
    """Return the GitHub token, or None (after logging why) when token or repo is missing."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token or not repo:
        logger.error(MISSING_CREDENTIALS_MESSAGE)
        return None
    return token
