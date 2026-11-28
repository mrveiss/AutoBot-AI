# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A PR carries the milestone and phase label of the issue it serves (#20516).

The rules are ``issue_structure``'s, so what counts as a goal milestone and a matching phase has one
home. A merge train only carries PRs that have their own, an ``automation/`` head is opened by its own
job with a personal token, and an outside contributor cannot set either.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent))
import issue_structure  # noqa: E402
from branch_sync_core import EXCLUDED_PREFIXES  # noqa: E402

#: Who can set a milestone and a label on this repository.
MAINTAINER_ASSOCIATIONS = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})


def excluded(head_ref: str, association: str, is_bot: bool) -> bool:
    return head_ref.startswith(EXCLUDED_PREFIXES) or is_bot or association not in MAINTAINER_ASSOCIATIONS


def problems(milestone: Optional[str], labels: Sequence[str]) -> List[str]:
    """What is missing or mismatched; empty when the PR has a goal milestone and its phase label."""
    found = (issue_structure.milestone_item(milestone), issue_structure.phase_item(milestone, labels))
    return [item for item in found if item]


def check(pull: Dict[str, Any]) -> List[str]:
    user = pull.get("user") or {}
    if excluded((pull.get("head") or {}).get("ref", ""), pull.get("author_association", ""), user.get("type") == "Bot"):
        return []
    milestone = (pull.get("milestone") or {}).get("title")
    return problems(milestone, [label["name"] for label in pull.get("labels") or []])


def main() -> int:
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    missing = check(event["pull_request"])
    for item in missing:
        sys.stdout.write(f"::error::{item}\n")
    if missing:
        sys.stdout.write("Set the milestone and phase label of the issue this PR serves.\n")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
