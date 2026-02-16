# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for Input Validator - Issue #712."""


from backend.security.input_validator import (
    WebResearchInputValidator,
    get_input_validator,
    sanitize_web_content,
    validate_research_query,
    validate_url,
)


class TestQueryValidation:
    """Tests for research query validation."""

    def test_valid_query(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query("python programming tutorial")
        assert result["safe"] is True
        assert result["risk_level"] == "low"

    def test_empty_query(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query("")
        assert result["safe"] is False
        assert "EMPTY_QUERY" in result["threats_detected"]

    def test_query_too_long(self):
        validator = WebResearchInputValidator()
        long_query = "a" * 600
        result = validator.validate_research_query(long_query, max_length=500)
        assert len(result["warnings"]) > 0

    def test_dangerous_script_pattern(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query("<script>alert('xss')</script>")
        assert result["safe"] is False
        assert "DANGEROUS_PATTERNS" in result["threats_detected"]

    def test_sql_injection_pattern(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query("'; DROP TABLE users; --")
        assert result["safe"] is False

    def test_command_injection_pattern(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query("test; rm -rf /")
        assert result["safe"] is False

    def test_path_traversal_pattern(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query("../../../etc/passwd")
        assert result["safe"] is False

    def test_suspicious_keywords_single(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query(
            "learn about sql injection prevention"
        )
        assert result["risk_level"] in ["medium", "low"]

    def test_suspicious_keywords_multiple(self):
        validator = WebResearchInputValidator()
        result = validator.validate_research_query(
            "exploit vulnerability backdoor malware"
        )
        assert result["safe"] is False
        assert result["risk_level"] == "high"


class TestURLValidation:
    """Tests for URL validation."""

    def test_valid_https_url(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("https://example.com/page")
        assert result["safe"] is True

    def test_valid_http_url(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("http://example.com")
        assert result["safe"] is True

    def test_empty_url(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("")
        assert result["safe"] is False
        assert "EMPTY_URL" in result["threats_detected"]

    def test_javascript_scheme(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("javascript:alert(1)")
        assert result["safe"] is False

    def test_data_scheme(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("data:text/html,<script>alert(1)</script>")
        assert result["safe"] is False

    def test_file_scheme(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("file:///etc/passwd")
        assert result["safe"] is False

    def test_ftp_scheme(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("ftp://ftp.example.com/file")
        assert result["safe"] is False

    def test_missing_hostname(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("https:///path")
        assert result["safe"] is False

    def test_very_long_url(self):
        validator = WebResearchInputValidator()
        long_url = "https://example.com/" + "a" * 2500
        result = validator.validate_url(long_url)
        assert len(result["warnings"]) > 0

    def test_ip_address_url(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("http://192.168.1.1/admin")
        assert len(result["warnings"]) > 0

    def test_localhost_url(self):
        validator = WebResearchInputValidator()
        result = validator.validate_url("http://localhost:8080/")
        assert len(result["warnings"]) > 0


class TestContentSanitization:
    """Tests for web content sanitization."""

    def test_clean_content(self):
        validator = WebResearchInputValidator()
        result = validator.sanitize_web_content("<p>Hello World</p>")
        assert result["safe"] is True

    def test_empty_content(self):
        validator = WebResearchInputValidator()
        result = validator.sanitize_web_content("")
        assert result["safe"] is True

    def test_script_tag_removal(self):
        validator = WebResearchInputValidator()
        html = "<p>Hello</p><script>alert('xss')</script><p>World</p>"
        result = validator.sanitize_web_content(html)
        assert "<script>" not in result["sanitized_content"]
        assert "SCRIPT_TAGS_REMOVED" in result["threats_detected"]

    def test_event_handler_removal(self):
        validator = WebResearchInputValidator()
        html = '<img src="x" onerror="alert(1)">'
        result = validator.sanitize_web_content(html)
        assert "onerror" not in result["sanitized_content"]

    def test_dangerous_link_removal(self):
        validator = WebResearchInputValidator()
        html = '<a href="javascript:alert(1)">Click</a>'
        result = validator.sanitize_web_content(html)
        assert "javascript:" not in result["sanitized_content"]

    def test_content_truncation(self):
        validator = WebResearchInputValidator()
        large_content = "x" * 2_000_000
        result = validator.sanitize_web_content(large_content)
        assert len(result["sanitized_content"]) <= 1_000_000

    def test_unsafe_content_type(self):
        validator = WebResearchInputValidator()
        result = validator.sanitize_web_content(
            "<p>test</p>", "application/octet-stream"
        )
        assert len(result["warnings"]) > 0


class TestValidatorSingleton:
    """Tests for thread-safe singleton."""

    def test_singleton_returns_same_instance(self):
        v1 = get_input_validator()
        v2 = get_input_validator()
        assert v1 is v2


class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_validate_research_query_func(self):
        result = validate_research_query("test query")
        assert "safe" in result

    def test_validate_url_func(self):
        result = validate_url("https://example.com")
        assert "safe" in result

    def test_sanitize_web_content_func(self):
        result = sanitize_web_content("<p>test</p>")
        assert "sanitized_content" in result


class TestValidatorStats:
    """Tests for validation statistics."""

    def test_get_validation_stats(self):
        validator = WebResearchInputValidator()
        stats = validator.get_validation_stats()
        assert "dangerous_patterns" in stats
        assert "suspicious_keywords" in stats
        assert stats["dangerous_patterns"] > 0

    def test_validate_content_type(self):
        validator = WebResearchInputValidator()
        assert validator.validate_content_type("text/html") is True
        assert validator.validate_content_type("application/json") is True
        assert validator.validate_content_type("application/octet-stream") is False
        assert validator.validate_content_type("") is False
