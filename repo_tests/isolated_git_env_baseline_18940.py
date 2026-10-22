# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Frozen list of test files that still build git repos without `autobot_shared.isolated_git` (#18940).

The list may only SHRINK. A new offender fails `isolated_git_env_guard_18940_test.py`; an entry
that was migrated (or left the tree) fails it too until the line is deleted. `FROZEN_TOTAL` caps
the length, so adding a line also means raising a number a reviewer sees.

Why each file is still here is the value; none is exempt from the goal.
"""

from __future__ import annotations

_CONTRACT = (
    "CONTRACT: the test asserts on the scrub/config behaviour itself, so it builds its own environment on purpose"
)
_PENDING = "PENDING: hand-rolled scrub only; migrate to isolated_git_env()/make_repo() (#18940 follow-up)"

ALLOWLIST: dict[str, str] = {
    "autobot-backend/api/git_mcp_env_scrub_15991_test.py": _CONTRACT,
    "autobot-backend/api/sandbox_files_delete_guard_15777_test.py": _PENDING,
    "autobot_shared/git_probe_test.py": _CONTRACT,
    "autobot_shared/paths_test.py": _CONTRACT,
    "repo_tests/git_repo_root_scrub_test.py": _CONTRACT,
    "repo_tests/hooks_path_override_15961_test.py": _CONTRACT,
    "repo_tests/one_git_enumeration_15926_test.py": _CONTRACT,
    "repo_tests/one_static_data_copy_18556_test.py": _CONTRACT,
}

#: Caps the length of ALLOWLIST; lower it when an entry goes, never raise it.
FROZEN_TOTAL = 8
