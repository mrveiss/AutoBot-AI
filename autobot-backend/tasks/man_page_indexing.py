# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Running the man-page indexer and reading its output (#15853).

Extracted from ``knowledge_tasks`` rather than added to it. That module sits at
its recorded file-size ceiling (#14236), and the exemption freezes the size the
file was granted -- it does not license more. Fixing the indexer path made the
module grow, so the fix and its two helpers moved here instead, and the ceiling
came down.

The two functions belong together in any case: one runs the indexer, the other
reads the numbers back out of its stdout. Neither has another caller.
"""

import subprocess  # nosec B404  # used for internal script execution only
import sys

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_constants import PATH

logger = get_logger(__name__)

#: The man-page indexer, anchored to the repository root.
#:
#: This was addressed relative to the process working directory, which is not
#: the repo root under Celery, systemd or a test runner -- and no such directory
#: exists at the root under any cwd. The script is real; only the path was not.
#: So the refresh returned its failed dict on every run.
MAN_PAGE_INDEXER = (
    PATH.PROJECT_ROOT / "autobot-infrastructure" / "shared" / "scripts" / "utilities" / "index_all_man_pages.py"
)


def parse_indexing_output(output: str) -> tuple:
    """Parse indexing script output for statistics (Issue #315: extracted helper).

    Args:
        output: Raw stdout from indexing script

    Returns:
        Tuple of (indexed_count, total_facts)
    """
    indexed_count = 0
    total_facts = 0
    for line in output.split("\n"):
        if "Successfully indexed:" in line:
            indexed_count = int(line.split(":")[1].strip())
        elif "Total facts in KB:" in line:
            total_facts = int(line.split(":")[1].strip())
    return indexed_count, total_facts


def run_indexing_subprocess() -> dict:
    """Run the man-page indexer and return a result dict. Ref: #1088.

    On a missing indexer or a non-zero exit returns a ``failed`` dict; on
    success returns a ``success`` dict with commands_indexed and total_facts.
    """
    if not MAN_PAGE_INDEXER.is_file():
        # Name the path. The previous failure mode truncated the subprocess's
        # stderr into a generic message, so "the indexer is not where we looked"
        # was indistinguishable from "the indexer ran and failed".
        message = f"man-page indexer not found at {MAN_PAGE_INDEXER}"
        logger.error("System knowledge refresh cannot run: %s", message)
        return {"status": "failed", "error": message, "message": "Knowledge refresh failed"}

    result = subprocess.run(  # nosec B603  # uses sys.executable with fixed internal script path
        [sys.executable, str(MAN_PAGE_INDEXER)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        error_msg = result.stderr[:500] if result.stderr else "Unknown error"
        logger.error("System knowledge refresh failed: %s", error_msg)
        return {"status": "failed", "error": error_msg, "message": "Knowledge refresh failed"}

    indexed_count, total_facts = parse_indexing_output(result.stdout)
    logger.info("System knowledge refresh complete: %d commands indexed, %d total facts", indexed_count, total_facts)
    return {
        "status": "success",
        "commands_indexed": indexed_count,
        "total_facts": total_facts,
        "message": "System knowledge refreshed successfully",
    }
