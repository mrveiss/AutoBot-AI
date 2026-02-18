# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for PermissionMatcher - Claude Code style permission system."""

from unittest.mock import patch

import pytest
from backend.services.permission_matcher import (
    MatchResult,
    PermissionMatcher,
    PermissionRule,
    get_permission_matcher,
)

from autobot_shared.ssot_config import PermissionAction, PermissionMode

# =============================================================================
# PermissionRule Tests
# =============================================================================


class TestPermissionRule:
    """Tests for PermissionRule.matches()."""

    def test_exact_match(self):
        """Exact command match with no wildcards."""
        rule = PermissionRule(tool="Bash", pattern="pwd", action=PermissionAction.ALLOW)
        assert rule.matches("Bash", "pwd") is True

    def test_glob_wildcard(self):
        """Glob-style * wildcard matches any characters."""
        rule = PermissionRule(
            tool="Bash", pattern="ls *", action=PermissionAction.ALLOW
        )
        assert rule.matches("Bash", "ls -la") is True
        assert rule.matches("Bash", "ls /home/user") is True

    def test_no_match_different_command(self):
        """Non-matching command returns False."""
        rule = PermissionRule(
            tool="Bash", pattern="ls *", action=PermissionAction.ALLOW
        )
        assert rule.matches("Bash", "cat file.txt") is False

    def test_tool_case_insensitive(self):
        """Tool matching is case-insensitive."""
        rule = PermissionRule(
            tool="Bash", pattern="ls *", action=PermissionAction.ALLOW
        )
        assert rule.matches("bash", "ls -la") is True
        assert rule.matches("BASH", "ls -la") is True

    def test_tool_mismatch(self):
        """Different tool returns False."""
        rule = PermissionRule(
            tool="Bash", pattern="ls *", action=PermissionAction.ALLOW
        )
        assert rule.matches("Read", "ls -la") is False

    def test_question_mark_wildcard(self):
        """? wildcard matches single character."""
        rule = PermissionRule(
            tool="Bash", pattern="cat ?.txt", action=PermissionAction.ALLOW
        )
        assert rule.matches("Bash", "cat a.txt") is True
        assert rule.matches("Bash", "cat ab.txt") is False

    def test_pattern_no_wildcard_exact(self):
        """Pattern without wildcard requires exact match."""
        rule = PermissionRule(tool="Bash", pattern="pwd", action=PermissionAction.ALLOW)
        assert rule.matches("Bash", "pwd") is True
        assert rule.matches("Bash", "pwd -L") is False


# =============================================================================
# PermissionMatcher Tests
# =============================================================================


class TestPermissionMatcherPrecedence:
    """Tests for match precedence: DENY > ASK > ALLOW > DEFAULT."""

    @pytest.fixture
    def matcher(self):
        """Create matcher with no file loading."""
        with patch.object(PermissionMatcher, "_load_rules"):
            m = PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=False)
        return m

    def test_deny_over_allow(self, matcher):
        """DENY takes precedence over ALLOW."""
        matcher.allow_rules = [
            PermissionRule(tool="Bash", pattern="rm *", action=PermissionAction.ALLOW)
        ]
        matcher.deny_rules = [
            PermissionRule(tool="Bash", pattern="rm *", action=PermissionAction.DENY)
        ]
        result, rule = matcher.match("Bash", "rm -rf /")
        assert result == MatchResult.DENY

    def test_deny_over_ask(self, matcher):
        """DENY takes precedence over ASK."""
        matcher.ask_rules = [
            PermissionRule(tool="Bash", pattern="rm *", action=PermissionAction.ASK)
        ]
        matcher.deny_rules = [
            PermissionRule(tool="Bash", pattern="rm *", action=PermissionAction.DENY)
        ]
        result, rule = matcher.match("Bash", "rm -rf /tmp/test")
        assert result == MatchResult.DENY

    def test_ask_over_allow(self, matcher):
        """ASK takes precedence over ALLOW."""
        matcher.allow_rules = [
            PermissionRule(tool="Bash", pattern="git *", action=PermissionAction.ALLOW)
        ]
        matcher.ask_rules = [
            PermissionRule(tool="Bash", pattern="git *", action=PermissionAction.ASK)
        ]
        result, rule = matcher.match("Bash", "git push origin main")
        assert result == MatchResult.ASK

    def test_allow_returns_allow(self, matcher):
        """ALLOW rule returns ALLOW when no higher-precedence match."""
        matcher.allow_rules = [
            PermissionRule(tool="Bash", pattern="ls *", action=PermissionAction.ALLOW)
        ]
        result, rule = matcher.match("Bash", "ls -la")
        assert result == MatchResult.ALLOW
        assert rule is not None
        assert rule.pattern == "ls *"

    def test_no_match_returns_default(self, matcher):
        """No matching rule returns DEFAULT."""
        result, rule = matcher.match("Bash", "some-custom-command")
        assert result == MatchResult.DEFAULT
        assert rule is None

    def test_matched_rule_returned(self, matcher):
        """Matching rule is returned as second element."""
        deny_rule = PermissionRule(
            tool="Bash",
            pattern="rm -rf /*",
            action=PermissionAction.DENY,
            description="Recursive root deletion",
        )
        matcher.deny_rules = [deny_rule]
        result, rule = matcher.match("Bash", "rm -rf /home")
        assert result == MatchResult.DENY
        assert rule is deny_rule


class TestPermissionMatcherModeOverrides:
    """Tests for mode-based overrides."""

    @pytest.fixture
    def admin_matcher(self):
        """Create admin matcher with no file loading."""
        with patch.object(PermissionMatcher, "_load_rules"):
            m = PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=True)
        return m

    @pytest.fixture
    def user_matcher(self):
        """Create non-admin matcher with no file loading."""
        with patch.object(PermissionMatcher, "_load_rules"):
            m = PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=False)
        return m

    def test_bypass_mode_admin_allows_all(self, admin_matcher):
        """BYPASS mode auto-allows everything for admin."""
        admin_matcher.mode = PermissionMode.BYPASS
        result, rule = admin_matcher.match("Bash", "rm -rf /")
        assert result == MatchResult.ALLOW
        assert rule is None

    def test_bypass_mode_non_admin_falls_through(self, user_matcher):
        """BYPASS mode falls through to rules for non-admin."""
        user_matcher.mode = PermissionMode.BYPASS
        result, rule = user_matcher.match("Bash", "ls -la")
        # No rules loaded, so DEFAULT
        assert result == MatchResult.DEFAULT

    def test_dont_ask_mode_admin_allows(self, admin_matcher):
        """DONT_ASK mode auto-allows for admin."""
        admin_matcher.mode = PermissionMode.DONT_ASK
        result, rule = admin_matcher.match("Bash", "npm install lodash")
        assert result == MatchResult.ALLOW

    def test_dont_ask_mode_still_denies(self, admin_matcher):
        """DONT_ASK mode still enforces DENY rules for admin."""
        admin_matcher.mode = PermissionMode.DONT_ASK
        admin_matcher.deny_rules = [
            PermissionRule(
                tool="Bash", pattern="rm -rf /*", action=PermissionAction.DENY
            )
        ]
        result, rule = admin_matcher.match("Bash", "rm -rf /home")
        assert result == MatchResult.DENY

    def test_dont_ask_mode_non_admin_falls_through(self, user_matcher):
        """DONT_ASK mode falls through for non-admin."""
        user_matcher.mode = PermissionMode.DONT_ASK
        result, rule = user_matcher.match("Bash", "ls -la")
        assert result == MatchResult.DEFAULT

    def test_plan_mode_falls_through(self, admin_matcher):
        """PLAN mode falls through to normal rules."""
        admin_matcher.mode = PermissionMode.PLAN
        admin_matcher.allow_rules = [
            PermissionRule(tool="Bash", pattern="ls *", action=PermissionAction.ALLOW)
        ]
        result, rule = admin_matcher.match("Bash", "ls -la")
        assert result == MatchResult.ALLOW

    def test_accept_edits_mode_falls_through(self, admin_matcher):
        """ACCEPT_EDITS mode falls through to normal rules."""
        admin_matcher.mode = PermissionMode.ACCEPT_EDITS
        result, rule = admin_matcher.match("Bash", "cat file.txt")
        assert result == MatchResult.DEFAULT

    def test_default_mode_uses_rules(self, admin_matcher):
        """DEFAULT mode uses normal rule matching."""
        admin_matcher.allow_rules = [
            PermissionRule(tool="Bash", pattern="ls *", action=PermissionAction.ALLOW)
        ]
        result, rule = admin_matcher.match("Bash", "ls -la")
        assert result == MatchResult.ALLOW


class TestPermissionMatcherRuleCRUD:
    """Tests for add_rule and remove_rule."""

    @pytest.fixture
    def matcher(self):
        """Create matcher with no file loading."""
        with patch.object(PermissionMatcher, "_load_rules"):
            m = PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=True)
        return m

    @pytest.fixture
    def user_matcher(self):
        """Create non-admin matcher."""
        with patch.object(PermissionMatcher, "_load_rules"):
            m = PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=False)
        return m

    def test_add_allow_rule_admin(self, matcher):
        """Admin can add ALLOW rules."""
        result = matcher.add_rule(
            "Bash", "echo *", PermissionAction.ALLOW, "Echo commands"
        )
        assert result is True
        assert len(matcher.allow_rules) == 1
        assert matcher.allow_rules[0].pattern == "echo *"

    def test_add_allow_rule_non_admin_denied(self, user_matcher):
        """Non-admin cannot add ALLOW rules."""
        result = user_matcher.add_rule("Bash", "rm *", PermissionAction.ALLOW)
        assert result is False
        assert len(user_matcher.allow_rules) == 0

    def test_add_ask_rule_non_admin(self, user_matcher):
        """Non-admin can add ASK rules."""
        result = user_matcher.add_rule("Bash", "curl *", PermissionAction.ASK)
        assert result is True
        assert len(user_matcher.ask_rules) == 1

    def test_add_deny_rule_non_admin(self, user_matcher):
        """Non-admin can add DENY rules."""
        result = user_matcher.add_rule("Bash", "rm -rf *", PermissionAction.DENY)
        assert result is True
        assert len(user_matcher.deny_rules) == 1

    def test_remove_existing_rule(self, matcher):
        """Remove an existing rule."""
        matcher.add_rule("Bash", "echo *", PermissionAction.ALLOW)
        result = matcher.remove_rule("Bash", "echo *")
        assert result is True
        assert len(matcher.allow_rules) == 0

    def test_remove_nonexistent_rule(self, matcher):
        """Removing nonexistent rule returns False."""
        result = matcher.remove_rule("Bash", "nonexistent *")
        assert result is False

    def test_remove_rule_case_insensitive_tool(self, matcher):
        """Remove works with case-insensitive tool match."""
        matcher.add_rule("Bash", "echo *", PermissionAction.ALLOW)
        result = matcher.remove_rule("bash", "echo *")
        assert result is True


class TestPermissionMatcherGetAllRules:
    """Tests for get_all_rules."""

    @pytest.fixture
    def matcher(self):
        """Create matcher with pre-loaded rules."""
        with patch.object(PermissionMatcher, "_load_rules"):
            m = PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=True)
        m.allow_rules = [
            PermissionRule(
                tool="Bash",
                pattern="ls *",
                action=PermissionAction.ALLOW,
                description="List files",
            ),
        ]
        m.ask_rules = [
            PermissionRule(
                tool="Bash",
                pattern="curl *",
                action=PermissionAction.ASK,
                description="HTTP requests",
            ),
        ]
        m.deny_rules = [
            PermissionRule(
                tool="Bash",
                pattern="rm -rf /*",
                action=PermissionAction.DENY,
                description="Root delete",
            ),
        ]
        return m

    def test_get_all_rules_structure(self, matcher):
        """get_all_rules returns dict with allow/ask/deny keys."""
        rules = matcher.get_all_rules()
        assert "allow" in rules
        assert "ask" in rules
        assert "deny" in rules

    def test_get_all_rules_content(self, matcher):
        """get_all_rules returns correct rule data."""
        rules = matcher.get_all_rules()
        assert len(rules["allow"]) == 1
        assert rules["allow"][0]["pattern"] == "ls *"
        assert rules["ask"][0]["tool"] == "Bash"
        assert rules["deny"][0]["description"] == "Root delete"


class TestPermissionMatcherModeManagement:
    """Tests for set_mode and get_mode."""

    @pytest.fixture
    def admin_matcher(self):
        """Create admin matcher."""
        with patch.object(PermissionMatcher, "_load_rules"):
            return PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=True)

    @pytest.fixture
    def user_matcher(self):
        """Create non-admin matcher."""
        with patch.object(PermissionMatcher, "_load_rules"):
            return PermissionMatcher(mode=PermissionMode.DEFAULT, is_admin=False)

    def test_get_mode(self, admin_matcher):
        """get_mode returns current mode."""
        assert admin_matcher.get_mode() == PermissionMode.DEFAULT

    def test_set_mode_admin_can_set_bypass(self, admin_matcher):
        """Admin can set BYPASS mode."""
        result = admin_matcher.set_mode(PermissionMode.BYPASS)
        assert result is True
        assert admin_matcher.get_mode() == PermissionMode.BYPASS

    def test_set_mode_admin_can_set_dont_ask(self, admin_matcher):
        """Admin can set DONT_ASK mode."""
        result = admin_matcher.set_mode(PermissionMode.DONT_ASK)
        assert result is True
        assert admin_matcher.get_mode() == PermissionMode.DONT_ASK

    def test_set_mode_non_admin_cannot_set_bypass(self, user_matcher):
        """Non-admin cannot set BYPASS mode."""
        result = user_matcher.set_mode(PermissionMode.BYPASS)
        assert result is False
        assert user_matcher.get_mode() == PermissionMode.DEFAULT

    def test_set_mode_non_admin_cannot_set_dont_ask(self, user_matcher):
        """Non-admin cannot set DONT_ASK mode."""
        result = user_matcher.set_mode(PermissionMode.DONT_ASK)
        assert result is False

    def test_set_mode_non_admin_can_set_plan(self, user_matcher):
        """Non-admin can set PLAN mode."""
        result = user_matcher.set_mode(PermissionMode.PLAN)
        assert result is True
        assert user_matcher.get_mode() == PermissionMode.PLAN

    def test_set_mode_non_admin_can_set_accept_edits(self, user_matcher):
        """Non-admin can set ACCEPT_EDITS mode."""
        result = user_matcher.set_mode(PermissionMode.ACCEPT_EDITS)
        assert result is True

    def test_get_allowed_modes_admin(self, admin_matcher):
        """Admin gets all modes."""
        modes = admin_matcher.get_allowed_modes()
        assert len(modes) == len(PermissionMode)

    def test_get_allowed_modes_user(self, user_matcher):
        """Non-admin gets subset of modes."""
        modes = user_matcher.get_allowed_modes()
        assert PermissionMode.BYPASS not in modes
        assert PermissionMode.DONT_ASK not in modes
        assert PermissionMode.DEFAULT in modes
        assert PermissionMode.PLAN in modes


class TestPermissionMatcherLoadRules:
    """Tests for _load_rules from YAML."""

    def test_load_from_valid_yaml(self, tmp_path):
        """Load rules from a valid YAML file."""
        rules_yaml = tmp_path / "rules.yaml"
        rules_yaml.write_text(
            """
default_rules:
  allow:
    - tool: Bash
      pattern: "ls *"
      description: "List files"
  ask:
    - tool: Bash
      pattern: "curl *"
      description: "HTTP requests"
  deny:
    - tool: Bash
      pattern: "rm -rf /*"
      description: "Root delete"
""",
            encoding="utf-8",
        )

        with patch("services.permission_matcher.config") as mock_config:
            mock_config.permission.mode = PermissionMode.DEFAULT
            mock_config.permission.rules_file = str(rules_yaml)
            mock_config.permission.is_admin_only_mode.return_value = False

            matcher = PermissionMatcher(
                rules_file=str(rules_yaml), mode=PermissionMode.DEFAULT
            )

        assert len(matcher.allow_rules) == 1
        assert len(matcher.ask_rules) == 1
        assert len(matcher.deny_rules) == 1
        assert matcher.allow_rules[0].pattern == "ls *"

    def test_load_from_missing_file(self, tmp_path):
        """Missing rules file is handled gracefully."""
        with patch("services.permission_matcher.config") as mock_config:
            mock_config.permission.mode = PermissionMode.DEFAULT
            mock_config.permission.rules_file = str(tmp_path / "nonexistent.yaml")
            mock_config.permission.is_admin_only_mode.return_value = False

            matcher = PermissionMatcher(
                rules_file=str(tmp_path / "nonexistent.yaml"),
                mode=PermissionMode.DEFAULT,
            )

        assert len(matcher.allow_rules) == 0
        assert len(matcher.ask_rules) == 0
        assert len(matcher.deny_rules) == 0

    def test_load_from_empty_file(self, tmp_path):
        """Empty YAML file is handled gracefully."""
        rules_yaml = tmp_path / "empty.yaml"
        rules_yaml.write_text("", encoding="utf-8")

        with patch("services.permission_matcher.config") as mock_config:
            mock_config.permission.mode = PermissionMode.DEFAULT
            mock_config.permission.rules_file = str(rules_yaml)
            mock_config.permission.is_admin_only_mode.return_value = False

            matcher = PermissionMatcher(
                rules_file=str(rules_yaml), mode=PermissionMode.DEFAULT
            )

        assert len(matcher.allow_rules) == 0


class TestGetPermissionMatcherSingleton:
    """Tests for the get_permission_matcher factory function."""

    def test_returns_instance(self):
        """Factory returns a PermissionMatcher instance."""
        with patch.object(PermissionMatcher, "_load_rules"):
            with patch("services.permission_matcher.config") as mock_config:
                mock_config.permission.mode = PermissionMode.DEFAULT
                mock_config.permission.rules_file = "/nonexistent"
                mock_config.permission.is_admin_only_mode.return_value = False
                # Reset the global singleton
                import services.permission_matcher as pm_module

                pm_module._matcher_instance = None
                instance = get_permission_matcher(is_admin=False, reload=True)
                assert isinstance(instance, PermissionMatcher)
                # Cleanup
                pm_module._matcher_instance = None

    def test_reload_creates_new_instance(self):
        """reload=True creates a fresh instance."""
        with patch.object(PermissionMatcher, "_load_rules"):
            with patch("services.permission_matcher.config") as mock_config:
                mock_config.permission.mode = PermissionMode.DEFAULT
                mock_config.permission.rules_file = "/nonexistent"
                mock_config.permission.is_admin_only_mode.return_value = False
                import services.permission_matcher as pm_module

                pm_module._matcher_instance = None

                first = get_permission_matcher(reload=True)
                second = get_permission_matcher(reload=True)
                assert first is not second
                pm_module._matcher_instance = None
