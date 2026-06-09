# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for DomainSecurityManager._compile_patterns() wildcard-to-regex conversion.

Covers the fix introduced in PR #3204 (issue #3164) that replaced the broken
double-escaping logic with a split-on-wildcard + re.escape approach.

Test matrix:
- Simple leading wildcard  : *.example.com
- Simple trailing wildcard : example.*
- Both ends wildcard       : *.example.*
- Multiple wildcards       : *.foo.*.com
- Wildcard mid-string      : pre*fix.example.com
- No wildcard (literal)    : example.com
- Regex special chars      : example+test.com, example[1].com
- Adjacent wildcards       : **.example.com
- Empty string pattern
- Case-insensitivity
"""

from unittest.mock import MagicMock, patch

from autobot_shared.logging_manager import get_logger
from security.domain_security import DomainSecurityConfig, DomainSecurityManager

logger = get_logger(__name__)


def _make_manager(blacklist: list, whitelist: list) -> DomainSecurityManager:
    """Build a DomainSecurityManager with explicit blacklist/whitelist, no I/O."""
    cfg = DomainSecurityConfig.__new__(DomainSecurityConfig)
    cfg.config_path = ""
    cfg.config = {
        "domain_security": {
            "enabled": True,
            "default_action": "block",
            "whitelist_mode": False,
            "cache_duration": 3600,
            "reputation_threshold": 0.7,
            "blacklist": blacklist,
            "whitelist": whitelist,
            "reputation_services": {},
            "threat_feeds": [],
            "network_validation": {
                "block_private_ips": False,
                "block_local_ips": False,
                "block_cloud_metadata": False,
                "allowed_ports": [80, 443],
                "blocked_ip_ranges": [],
            },
        }
    }

    with patch("security.domain_security.get_http_client", return_value=MagicMock()):
        mgr = DomainSecurityManager.__new__(DomainSecurityManager)
        mgr.config = cfg
        mgr.domain_cache = {}
        mgr.threat_intelligence = set()
        mgr.last_threat_update = 0
        mgr._http_client = MagicMock()
        mgr._threat_intel_service = None
        mgr._compile_patterns()

    return mgr


class TestCompilePatternsLeadingWildcard:
    """*.example.com — wildcard replaces subdomain only."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["*.example.com"],
            whitelist=["*.trusted.org"],
        )

    def test_blacklist_subdomain_matches(self):
        result = self.mgr._check_blacklist("foo.example.com")
        assert result["blocked"] is True

    def test_blacklist_bare_domain_does_not_match(self):
        """*.example.com must not match example.com (no dot before example)."""
        result = self.mgr._check_blacklist("example.com")
        assert result["blocked"] is False

    def test_blacklist_different_domain_does_not_match(self):
        result = self.mgr._check_blacklist("foo.other.com")
        assert result["blocked"] is False

    def test_blacklist_partial_suffix_does_not_match(self):
        """exampleXcom must not match *.example.com (dots are escaped)."""
        result = self.mgr._check_blacklist("foo.exampleXcom")
        assert result["blocked"] is False

    def test_whitelist_subdomain_matches(self):
        assert self.mgr._is_whitelisted("docs.trusted.org") is True

    def test_whitelist_bare_domain_does_not_match(self):
        assert self.mgr._is_whitelisted("trusted.org") is False


class TestCompilePatternsTrailingWildcard:
    """example.* — wildcard replaces TLD only."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["example.*"],
            whitelist=[],
        )

    def test_matches_dotcom(self):
        assert self.mgr._check_blacklist("example.com")["blocked"] is True

    def test_matches_dotnet(self):
        assert self.mgr._check_blacklist("example.net")["blocked"] is True

    def test_does_not_match_subdomain(self):
        """foo.example.com has content before 'example' — should not match."""
        assert self.mgr._check_blacklist("foo.example.com")["blocked"] is False

    def test_does_not_match_unrelated(self):
        assert self.mgr._check_blacklist("notexample.com")["blocked"] is False


class TestCompilePatternsDoubleWildcard:
    """*.example.* — wildcard on both ends."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["*.example.*"],
            whitelist=[],
        )

    def test_matches_subdomain_with_tld(self):
        assert self.mgr._check_blacklist("foo.example.com")["blocked"] is True

    def test_matches_different_tld(self):
        assert self.mgr._check_blacklist("bar.example.net")["blocked"] is True

    def test_bare_domain_does_not_match(self):
        assert self.mgr._check_blacklist("example.com")["blocked"] is False

    def test_unrelated_domain_does_not_match(self):
        assert self.mgr._check_blacklist("foo.other.com")["blocked"] is False


class TestCompilePatternsMultipleWildcards:
    """*.foo.*.com — wildcards at positions 0 and 2."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["*.foo.*.com"],
            whitelist=[],
        )

    def test_matches_expected_structure(self):
        assert self.mgr._check_blacklist("a.foo.b.com")["blocked"] is True

    def test_matches_longer_middle_segment(self):
        assert self.mgr._check_blacklist("x.foo.longer-part.com")["blocked"] is True

    def test_missing_middle_segment_does_not_match(self):
        assert self.mgr._check_blacklist("a.foo.com")["blocked"] is False


class TestCompilePatternsMidStringWildcard:
    """pre*fix.example.com — wildcard in middle of label."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["pre*fix.example.com"],
            whitelist=[],
        )

    def test_matches_with_content_between(self):
        assert self.mgr._check_blacklist("pre-anything-fix.example.com")["blocked"] is True

    def test_matches_when_wildcard_is_empty(self):
        assert self.mgr._check_blacklist("prefix.example.com")["blocked"] is True

    def test_does_not_match_wrong_suffix(self):
        assert self.mgr._check_blacklist("prefix.example.org")["blocked"] is False


class TestCompilePatternsNoWildcard:
    """Literal pattern — no wildcards, must match exactly."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["exact.example.com"],
            whitelist=["github.com"],
        )

    def test_exact_blacklist_match(self):
        assert self.mgr._check_blacklist("exact.example.com")["blocked"] is True

    def test_blacklist_subdomain_does_not_match(self):
        assert self.mgr._check_blacklist("sub.exact.example.com")["blocked"] is False

    def test_blacklist_dot_is_not_any_char(self):
        """exampleXcom must not match example.com — dots must be escaped."""
        assert self.mgr._check_blacklist("exactXexample.com")["blocked"] is False

    def test_exact_whitelist_match(self):
        assert self.mgr._is_whitelisted("github.com") is True

    def test_whitelist_subdomain_does_not_match(self):
        assert self.mgr._is_whitelisted("api.github.com") is False


class TestCompilePatternsRegexSpecialChars:
    """Patterns containing regex metacharacters must be treated as literals."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["example+test.com", "example[1].com", "example(one).com"],
            whitelist=[],
        )

    def test_plus_sign_treated_as_literal(self):
        assert self.mgr._check_blacklist("example+test.com")["blocked"] is True

    def test_plus_does_not_act_as_quantifier(self):
        """Without escaping, 'e+' would match 'eee' — verify that does not happen."""
        assert self.mgr._check_blacklist("exampletest.com")["blocked"] is False

    def test_brackets_treated_as_literal(self):
        assert self.mgr._check_blacklist("example[1].com")["blocked"] is True

    def test_brackets_do_not_act_as_char_class(self):
        """Without escaping, [1] would match the digit 1 — exact bracket required."""
        assert self.mgr._check_blacklist("example1.com")["blocked"] is False

    def test_parens_treated_as_literal(self):
        assert self.mgr._check_blacklist("example(one).com")["blocked"] is True


class TestCompilePatternsAdjacentWildcards:
    """** is equivalent to .* in the compiled regex (two wildcards side by side)."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["**.example.com"],
            whitelist=[],
        )

    def test_matches_single_subdomain(self):
        assert self.mgr._check_blacklist("foo.example.com")["blocked"] is True

    def test_matches_nested_subdomains(self):
        assert self.mgr._check_blacklist("a.b.example.com")["blocked"] is True


class TestCompilePatternsEmptyString:
    """An empty-string pattern compiles to ^$ and must only match empty input."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=[""],
            whitelist=[""],
        )

    def test_empty_pattern_does_not_match_real_domain(self):
        assert self.mgr._check_blacklist("example.com")["blocked"] is False

    def test_empty_pattern_does_not_whitelist_real_domain(self):
        assert self.mgr._is_whitelisted("example.com") is False


class TestCompilePatternsCaseInsensitivity:
    """Compiled patterns use re.IGNORECASE."""

    def setup_method(self):
        self.mgr = _make_manager(
            blacklist=["*.EVIL.com"],
            whitelist=["SAFE.org"],
        )

    def test_blacklist_lower_matches_upper_pattern(self):
        assert self.mgr._check_blacklist("sub.evil.com")["blocked"] is True

    def test_blacklist_mixed_case_matches(self):
        assert self.mgr._check_blacklist("sub.Evil.COM")["blocked"] is True

    def test_whitelist_lower_matches_upper_pattern(self):
        assert self.mgr._is_whitelisted("safe.org") is True

    def test_whitelist_mixed_case_matches(self):
        assert self.mgr._is_whitelisted("SAFE.ORG") is True


class TestCompilePatternsDefaultConfig:
    """Verify default config patterns compile and behave correctly."""

    def setup_method(self):
        cfg = DomainSecurityConfig.__new__(DomainSecurityConfig)
        cfg.config_path = ""
        cfg.config = cfg._get_default_config()
        with patch("security.domain_security.get_http_client", return_value=MagicMock()):
            mgr = DomainSecurityManager.__new__(DomainSecurityManager)
            mgr.config = cfg
            mgr.domain_cache = {}
            mgr.threat_intelligence = set()
            mgr.last_threat_update = 0
            mgr._http_client = MagicMock()
            mgr._threat_intel_service = None
            mgr._compile_patterns()
        self.mgr = mgr

    def test_default_whitelist_wikipedia_subdomain(self):
        assert self.mgr._is_whitelisted("en.wikipedia.org") is True

    def test_default_whitelist_bare_wikipedia_is_whitelisted(self):
        """wikipedia.org is a literal entry in the default whitelist."""
        assert self.mgr._is_whitelisted("wikipedia.org") is True

    def test_default_blacklist_malware_subdomain(self):
        assert self.mgr._check_blacklist("bad.malware.com")["blocked"] is True

    def test_default_blacklist_bare_malware_domain_not_matched_by_star(self):
        """*.malware.com must not match malware.com itself."""
        assert self.mgr._check_blacklist("malware.com")["blocked"] is False

    def test_default_blacklist_adult_keyword_mid_domain(self):
        """*adult* matches any domain containing 'adult'."""
        assert self.mgr._check_blacklist("someadultsite.com")["blocked"] is True
