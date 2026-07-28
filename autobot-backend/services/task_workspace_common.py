# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared primitives for the task-workspace managers (GH#11699).

Canonical home for the path-traversal ``task_id`` validator that the
git-worktree workspace manager (``services.task_workspace``) and the
docker-container workspace manager (``services.docker_task_workspace``) both
depend on.  Previously each module defined its own ``_validate_task_id`` and
``_SAFE_TASK_ID_RE`` copy (GH#6471 blocker 2), inviting drift.

This module intentionally has no dependencies beyond ``re`` so both managers
(and ``api.task_workspace``) can import it without any circular-import risk.
"""

import re

# task_id must be a safe identifier: alnum + underscore + hyphen, max 128 chars.
# Rejects path-traversal payloads like "../../etc/passwd" (GH#6471 blocker 2).
SAFE_TASK_ID_RE = re.compile(r"^[0-9a-zA-Z_\-]{1,128}$")


def validate_task_id(task_id: str) -> None:
    """Reject task_ids that could be used for path traversal (GH#6471 blocker 2)."""
    if not SAFE_TASK_ID_RE.match(task_id):
        raise ValueError(f"Invalid task_id {task_id!r}: must match [0-9a-zA-Z_-]{{1,128}}")
