# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Pytest tests for voice-context toolset bundles (#7344)."""

from api.redis_mcp.rbac import (
    TOOL_ACCESS_MATRIX,
    filter_tools_for_bundle,
)

ALL_TOOLS = list(TOOL_ACCESS_MATRIX.keys())


class TestBundleToolCounts:
    def test_voice_safe_is_subset_of_extended(self):
        safe = set(filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False))
        extended = set(filter_tools_for_bundle(ALL_TOOLS, "voice_extended", is_admin=False))
        assert safe.issubset(extended)

    def test_voice_extended_is_subset_of_admin(self):
        extended = set(filter_tools_for_bundle(ALL_TOOLS, "voice_extended", is_admin=True))
        admin = set(filter_tools_for_bundle(ALL_TOOLS, "voice_admin", is_admin=True))
        assert extended.issubset(admin)

    def test_voice_safe_contains_only_read_tools(self):
        from api.redis_mcp.rbac import ToolAccess, get_tool_access

        safe = filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False)
        for tool in safe:
            access = get_tool_access(tool, is_admin=False)
            assert access == ToolAccess.READ, f"{tool} is not READ-only in voice_safe"

    def test_voice_safe_excludes_blocked_tools(self):
        safe = set(filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False))
        assert "redis_client_list" not in safe
        assert "redis_slowlog" not in safe

    def test_voice_safe_has_expected_minimum_count(self):
        safe = filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False)
        assert len(safe) >= 5  # at least the read tools

    def test_voice_admin_includes_all_non_blocked(self):
        from api.redis_mcp.rbac import ToolAccess, get_tool_access

        admin = set(filter_tools_for_bundle(ALL_TOOLS, "voice_admin", is_admin=True))
        for tool in ALL_TOOLS:
            access = get_tool_access(tool, is_admin=True)
            if access != ToolAccess.BLOCKED:
                assert tool in admin, f"{tool} should be in voice_admin"


class TestDenylist:
    def test_denylist_removes_tool_from_bundle(self):
        all_without = filter_tools_for_bundle(ALL_TOOLS, "voice_admin", is_admin=True)
        all_with_deny = filter_tools_for_bundle(ALL_TOOLS, "voice_admin", is_admin=True, disabled_tools=["redis_get"])
        assert "redis_get" not in all_with_deny
        assert len(all_with_deny) == len(all_without) - 1

    def test_denylist_has_no_effect_if_tool_already_excluded(self):
        # redis_slowlog is already blocked in voice_safe
        without = filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False)
        with_deny = filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False, disabled_tools=["redis_slowlog"])
        assert without == with_deny

    def test_empty_denylist_is_no_op(self):
        a = filter_tools_for_bundle(ALL_TOOLS, "voice_extended", is_admin=False)
        b = filter_tools_for_bundle(ALL_TOOLS, "voice_extended", is_admin=False, disabled_tools=[])
        assert a == b


class TestRoleXBundle:
    def test_admin_sees_more_in_extended_than_user(self):
        user_tools = set(filter_tools_for_bundle(ALL_TOOLS, "voice_extended", is_admin=False))
        admin_tools = set(filter_tools_for_bundle(ALL_TOOLS, "voice_extended", is_admin=True))
        # admin should see at least as many tools (approval-required become visible)
        assert admin_tools.issuperset(user_tools)

    def test_unknown_bundle_falls_back_to_voice_safe(self):
        safe = set(filter_tools_for_bundle(ALL_TOOLS, "voice_safe", is_admin=False))
        unknown = set(filter_tools_for_bundle(ALL_TOOLS, "nonexistent_bundle", is_admin=False))
        assert safe == unknown
