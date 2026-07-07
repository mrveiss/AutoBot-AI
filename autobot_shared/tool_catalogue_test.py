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
    ApprovalCategory,
    match_tool_name,
    valid_approval_categories,
)

# --- match_tool_name (canonical matcher) -----------------------------------


def test_match_tool_name_exact_and_case_insensitive():
    assert match_tool_name("bash", ("bash", "deploy")) == "bash"
    assert match_tool_name("BASH", ("bash",)) == "bash"


def test_match_tool_name_plain_prefix():
    assert match_tool_name("bash_run", ("bash",)) == "bash"
    assert match_tool_name("deployment", ("deploy",)) == "deploy"  # plain prefix matches


def test_match_tool_name_word_boundary():
    assert match_tool_name("deploy_service", ("deploy",), word_boundary=True) == "deploy"
    assert match_tool_name("deployment", ("deploy",), word_boundary=True) is None


def test_match_tool_name_no_match_and_empty():
    assert match_tool_name("web_search", ("bash", "deploy")) is None
    assert match_tool_name("bash", ()) is None


def _orig_forbidden(name, forbidden):
    if not forbidden:
        return None
    name = name.lower()
    if name in forbidden:
        return name
    for pattern in forbidden:
        if name.startswith(pattern):
            return pattern
    return None


def _orig_approval(name, declared):
    name = name.lower()
    for category in declared:
        for gated in APPROVAL_CATEGORY_TOOLS.get(category, ()):
            if name == gated or name.startswith(gated + "_"):
                return category
    return None


def test_match_tool_name_parity_with_original_matchers():
    from chat_workflow.tool_handler import _approval_category_for
    from orchestration.agent_registry import match_forbidden_tool

    forbidden = frozenset(INFRA_AND_SHELL_TOOLS)
    cats = list(APPROVAL_CATEGORY_TOOLS)
    names = [
        "bash",
        "BASH",
        "bash_run",
        "deploy",
        "deployment",
        "deploy_service",
        "git_push",
        "git_pusher",
        "web_search",
        "docker_compose",
        "unknown_tool",
        "",
    ]
    for n in names:
        assert match_forbidden_tool(n, forbidden) == _orig_forbidden(n, forbidden), n
        assert _approval_category_for(n, cats) == _orig_approval(n, cats), n


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


def test_approval_category_enum_matches_catalogue_keys():
    # The controlled vocabulary must stay in sync with the tool catalogue keys,
    # else a valid category could match no tools (silent gate bypass).
    assert valid_approval_categories() == set(APPROVAL_CATEGORY_TOOLS)
    assert {c.value for c in ApprovalCategory} == set(APPROVAL_CATEGORY_TOOLS)


def test_consumers_reexport_the_catalogue():
    # The three modules must derive from the SSOT, not re-declare literals.
    from agent_loop.loop import SENSITIVE_TOOLS as loop_sensitive
    from chat_workflow.tool_handler import _APPROVAL_CATEGORY_TOOLS as handler_approval
    from orchestration.agent_registry import _INFRA_AND_SHELL_TOOLS as reg_infra

    assert set(loop_sensitive) == _ORIG_SENSITIVE
    assert set(reg_infra) == _ORIG_INFRA_AND_SHELL
    assert handler_approval is APPROVAL_CATEGORY_TOOLS
