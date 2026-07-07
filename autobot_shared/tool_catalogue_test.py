# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Parity tests for the canonical tool catalogue (GH#11206).

Proves the composed catalogues reproduce the pre-consolidation literals EXACTLY,
so the SSOT refactor is behaviour-preserving (no tool silently gained/lost
governance).
"""

from autobot_shared.tool_catalogue import (
    APPROVAL_CATEGORY_TOOLS,
    INFRA_AND_SHELL_TOOLS,
    SENSITIVE_TOOLS,
)

# --- frozen snapshots of the original literals (pre-#11206) -----------------

_ORIG_INFRA_AND_SHELL = {
    "bash",
    "shell",
    "execute_command",
    "run_command",
    "system_exec",
    "deploy",
    "ansible",
    "docker",
    "kubectl",
    "helm",
    "terraform",
}

_ORIG_SENSITIVE = {
    "write_file",
    "edit_file",
    "delete_file",
    "move_file",
    "copy_file",
    "create_directory",
    "remove_directory",
    "bash",
    "shell",
    "execute_command",
    "run_command",
    "terminal",
    "system_exec",
    "deploy",
    "ansible",
    "docker",
    "kubectl",
    "helm",
    "terraform",
    "git_push",
    "git_commit",
    "git_merge",
    "git_rebase",
    "git_reset",
    "git_force_push",
    "http_post",
    "http_put",
    "http_patch",
    "http_delete",
    "send_request",
    "code_interpreter",
}

_ORIG_APPROVAL = {
    "pushing commits": {"git_push", "git_commit", "git_merge", "git_rebase", "git_force_push"},
    "publishing": {"deploy", "publish", "content_reach"},
    "destructive operations": {
        "delete_file",
        "remove_directory",
        "bash",
        "shell",
        "execute_command",
        "run_command",
        "docker",
        "kubectl",
        "terraform",
    },
    "rotating credentials": {"rotate_credentials", "rotate_key", "vault_rotate"},
}


def test_infra_and_shell_parity():
    assert set(INFRA_AND_SHELL_TOOLS) == _ORIG_INFRA_AND_SHELL
    assert len(INFRA_AND_SHELL_TOOLS) == len(set(INFRA_AND_SHELL_TOOLS))  # no dupes


def test_sensitive_tools_parity():
    assert set(SENSITIVE_TOOLS) == _ORIG_SENSITIVE


def test_approval_categories_parity():
    assert set(APPROVAL_CATEGORY_TOOLS) == set(_ORIG_APPROVAL)
    for category, tools in _ORIG_APPROVAL.items():
        assert set(APPROVAL_CATEGORY_TOOLS[category]) == tools, category


def test_consumers_reexport_the_catalogue():
    # The three modules must derive from the SSOT, not re-declare literals.
    from agent_loop.loop import SENSITIVE_TOOLS as loop_sensitive
    from chat_workflow.tool_handler import _APPROVAL_CATEGORY_TOOLS as handler_approval
    from orchestration.agent_registry import _INFRA_AND_SHELL_TOOLS as reg_infra

    assert set(loop_sensitive) == _ORIG_SENSITIVE
    assert set(reg_infra) == _ORIG_INFRA_AND_SHELL
    assert handler_approval is APPROVAL_CATEGORY_TOOLS
