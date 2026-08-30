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


def _orig_sensitive(name):
    name = name.lower()
    if name in SENSITIVE_TOOLS:
        return name
    for s in SENSITIVE_TOOLS:
        if name.startswith(s):
            return s
    return None


def test_match_tool_name_parity_with_original_matchers():
    from agent_loop.loop import AgentLoop
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
        assert AgentLoop._sensitive_tool_name({"tool_name": n}) == _orig_sensitive(n), n


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
    # The extraction snapshot is a floor, not a ceiling (#14067). What this
    # guards is *drift*: every category that existed at extraction time must
    # still carry exactly its original tools, so a consolidation edit cannot
    # quietly widen or narrow one. A category added since is an addition, not
    # drift, and is asserted on its own terms in
    # TestOutboundIsReachableThroughACategory below.
    assert set(_ORIG_APPROVAL) <= set(APPROVAL_CATEGORY_TOOLS), "a category present at extraction time was removed"
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


class TestOutboundIsReachableThroughACategory:
    """#14067: the one action class that leaves the machine had no category.

    `HTTP_WRITE_TOOLS` sat in `SENSITIVE_TOOLS` — so the agent-loop plane gated
    it — while `APPROVAL_CATEGORY_TOOLS` named none of it, so a work item's
    `requires_approval_before` could not express "ask me before you send
    anything outward" at all.
    """

    def test_every_http_write_tool_is_reachable_through_some_category(self):
        from autobot_shared.tool_catalogue import (
            APPROVAL_CATEGORY_TOOLS,
            HTTP_WRITE_TOOLS,
            match_tool_name,
        )

        for tool in HTTP_WRITE_TOOLS:
            assert any(
                match_tool_name(tool, patterns, word_boundary=True) for patterns in APPROVAL_CATEGORY_TOOLS.values()
            ), f"{tool!r} is sensitive but no approval category can gate it"

    def test_the_new_category_is_in_the_controlled_vocabulary(self):
        """A category absent from the enum "matches no tools at the seam and
        silently disables the gate" — per ApprovalCategory's own docstring."""
        from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS, valid_approval_categories

        assert set(APPROVAL_CATEGORY_TOOLS) <= valid_approval_categories()

    def test_a_gateway_send_is_deliberately_not_a_tool_name_here(self):
        """Guards against a future edit inventing tool names for the Gateway.

        Gateway egress is governed at its own seam because a channel send is not
        a tool call; adding a fictional tool name here would create an allowlist
        entry that matches nothing and exempts nothing, silently.
        """
        from autobot_shared.tool_catalogue import APPROVAL_CATEGORY_TOOLS

        assert APPROVAL_CATEGORY_TOOLS["sending externally"] == (
            "http_post",
            "http_put",
            "http_patch",
            "http_delete",
            "send_request",
        )
class TestEverySensitiveToolIsReachableThroughACategory:
    """#14903: assert the property, not the list.

    The #14067 class below this file's earlier one checks HTTP_WRITE_TOOLS
    specifically. That shape only ever catches the gap someone already found:
    eleven other members of ``SENSITIVE_TOOLS`` -- including every file write --
    were reachable through no category at the time this was written, and no test
    said so. This enumerates the whole set instead, so the next atom added to
    ``SENSITIVE_TOOLS`` without a category fails here on the commit that adds it.

    The two planes are allowed to differ, but only on purpose: an entry in
    ``UNCOVERABLE_BY_DESIGN`` states why. It is empty, and an empty allowlist is
    the point -- the gap this issue is about was never a decision, it was drift
    that read as a decision because nothing distinguished the two.
    """

    # Tool -> the reason no approval category can express it. Empty at merge
    # (#14903). Adding an entry is a deliberate, reviewable act; leaving a tool
    # uncovered without one is not possible without failing the test below.
    UNCOVERABLE_BY_DESIGN: "dict[str, str]" = {}

    def test_every_sensitive_tool_is_gateable(self):
        from autobot_shared.tool_catalogue import (
            APPROVAL_CATEGORY_TOOLS,
            SENSITIVE_TOOLS,
            match_tool_name,
        )

        uncoverable = sorted(
            tool
            for tool in SENSITIVE_TOOLS
            if not any(
                match_tool_name(tool, patterns, word_boundary=True) for patterns in APPROVAL_CATEGORY_TOOLS.values()
            )
        )
        unexplained = [tool for tool in uncoverable if tool not in self.UNCOVERABLE_BY_DESIGN]
        assert not unexplained, (
            f"{unexplained} are in SENSITIVE_TOOLS -- so the agent-loop plane gates them -- but no "
            f"approval category can express them, so a work item's requires_approval_before cannot "
            f"ask for them. Add them to a category, or to UNCOVERABLE_BY_DESIGN with the reason."
        )

    def test_the_allowlist_names_only_tools_that_are_actually_uncovered(self):
        """A stale exemption is worse than none: it reads as a considered
        decision while exempting nothing, and outlives the thing that justified it."""
        from autobot_shared.tool_catalogue import (
            APPROVAL_CATEGORY_TOOLS,
            SENSITIVE_TOOLS,
            match_tool_name,
        )

        for tool, reason in self.UNCOVERABLE_BY_DESIGN.items():
            assert reason.strip(), f"{tool!r} is allowlisted with no reason"
            assert tool in SENSITIVE_TOOLS, f"{tool!r} is allowlisted but is not in SENSITIVE_TOOLS"
            covered = any(
                match_tool_name(tool, patterns, word_boundary=True) for patterns in APPROVAL_CATEGORY_TOOLS.values()
            )
            assert not covered, (
                f"{tool!r} is allowlisted as uncoverable but a category now covers it; "
                f"remove the allowlist entry"
            )

    def test_the_check_actually_enumerates_something(self):
        """Reach: if SENSITIVE_TOOLS were empty or unimportable, the assertion
        above would pass by examining nothing."""
        from autobot_shared.tool_catalogue import FILE_WRITE_TOOLS, SENSITIVE_TOOLS

        assert len(SENSITIVE_TOOLS) >= 20, f"only {len(SENSITIVE_TOOLS)} sensitive tools; the set looks truncated"
        assert set(FILE_WRITE_TOOLS) <= set(SENSITIVE_TOOLS), "file writes left the sensitive set"

    def test_file_writes_are_gateable_by_a_declared_category(self):
        """The specific gap #14903 was filed for, pinned so it cannot silently return."""
        from autobot_shared.tool_catalogue import (
            APPROVAL_CATEGORY_TOOLS,
            FILE_WRITE_TOOLS,
            match_tool_name,
            valid_approval_categories,
        )

        for tool in FILE_WRITE_TOOLS:
            gating = [
                category
                for category, patterns in APPROVAL_CATEGORY_TOOLS.items()
                if match_tool_name(tool, patterns, word_boundary=True)
            ]
            assert gating, f"{tool!r} is a file write that no approval category gates"
            assert set(gating) <= valid_approval_categories(), (
                f"{tool!r} is gated only by {gating}, which is outside the controlled vocabulary -- "
                f"a category absent from the enum matches no tools at the seam and silently disables the gate"
            )
