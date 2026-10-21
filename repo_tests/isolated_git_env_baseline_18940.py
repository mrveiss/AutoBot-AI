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
_AUTHOR = "AUTHOR: asserts on the author a fixture configures; needs identity=False and a read of the assertions"
_BRANCH = (
    "BRANCH: depends on the default branch name (master today) or branch-guard behaviour; audit before it takes main"
)
_PENDING = "PENDING: hand-rolled scrub only; migrate to isolated_git_env()/make_repo() (#18940 follow-up)"

ALLOWLIST: dict[str, str] = {
    "autobot-backend/api/git_mcp_env_scrub_15991_test.py": _CONTRACT,
    "autobot-backend/api/sandbox_files_delete_guard_15777_test.py": _PENDING,
    "autobot-backend/code_intelligence/co_change_test.py": _AUTHOR,
    "autobot-backend/code_intelligence/git_history_crawler_test.py": _AUTHOR,
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-branch-guard_test.py": _BRANCH,
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-no-tag-pinned-action_test.py": _BRANCH,
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-record-branch_test.py": _BRANCH,
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-target-branch-guard_test.py": _BRANCH,
    "autobot-infrastructure/shared/scripts/hooks/pre-commit-worktree-branch-guard_test.py": _BRANCH,
    "autobot-slm-backend/scripts/sync_deletion_planner_test.py": _BRANCH,
    "autobot-slm-backend/tests/services/full_tree_drift_test.py": _BRANCH,
    "autobot-slm-backend/tests/services/git_subprocess_test.py": _BRANCH,
    "autobot-slm-backend/tests/services/sync_deletions_shallow_bootstrap_test.py": _BRANCH,
    "autobot-slm-backend/tests/services/sync_deletions_test.py": _BRANCH,
    "autobot_shared/git_probe_test.py": _CONTRACT,
    "autobot_shared/paths_test.py": _CONTRACT,
    "pipeline-scripts/check_baseline_no_growth_test.py": _BRANCH,
    "repo_tests/commit_msg_hook_17029_test.py": _PENDING,
    "repo_tests/doc_index_worktree_contamination_16934_test.py": _PENDING,
    "repo_tests/git_hooks_formatter_dispatch_16923_test.py": _PENDING,
    "repo_tests/git_hooks_installer_test.py": _PENDING,
    "repo_tests/git_hooks_post_checkout_precommit_sync_16923_test.py": _PENDING,
    "repo_tests/git_repo_root_scrub_test.py": _CONTRACT,
    "repo_tests/hook_self_sync_atomic_test.py": _PENDING,
    "repo_tests/hooks_path_override_15961_test.py": _CONTRACT,
    "repo_tests/node_modules_link_traversable_17573_test.py": _PENDING,
    "repo_tests/one_git_enumeration_15926_test.py": _CONTRACT,
    "repo_tests/one_static_data_copy_18556_test.py": _CONTRACT,
    "repo_tests/pre_push_open_pr_cap_17006_test.py": _PENDING,
    "repo_tests/prepush_budget_18578_test.py": _PENDING,
    "repo_tests/prepush_hook_sync_17578_test.py": _PENDING,
    "repo_tests/release_range_test.py": _PENDING,
    "repo_tests/scan_helpers_vacuity_migrated_test.py": _PENDING,
    "repo_tests/scan_helpers_vacuity_test.py": _PENDING,
    "repo_tests/stylelint_changed_files_skip_deletions_17571_test.py": _PENDING,
    "scripts/lint_conventions_test.py": _PENDING,
    "scripts/verify_done_test.py": _PENDING,
}

#: Caps the length of ALLOWLIST; lower it when an entry goes, never raise it.
FROZEN_TOTAL = 37
