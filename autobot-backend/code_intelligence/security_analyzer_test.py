# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Security Pattern Analyzer

Tests the detection of security vulnerabilities including:
- SQL injection patterns
- Hardcoded secrets
- Weak cryptography
- Command injection
- Insecure deserialization
- Input validation gaps

Part of Issue #219 - Security Pattern Analyzer
"""

import tempfile
import textwrap

import pytest
from code_intelligence.security_analyzer import (
    SecurityAnalyzer,
    SecuritySeverity,
    VulnerabilityType,
    analyze_security,
    get_vulnerability_types,
)


class TestSecurityAnalyzer:
    """Test security vulnerability detection."""

    def test_detect_sql_injection_format(self):
        """Test detection of SQL injection via string formatting."""
        code = textwrap.dedent(
            """
            def get_user(cursor, user_id):
                cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
                return cursor.fetchone()
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            sql_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.SQL_INJECTION
            ]

            # Should detect SQL injection pattern
            assert len(sql_results) >= 1
            assert sql_results[0].severity == SecuritySeverity.CRITICAL
            assert "CWE-89" in (sql_results[0].cwe_id or "")

    def test_detect_command_injection_eval(self):
        """Test detection of command injection via eval()."""
        code = textwrap.dedent(
            """
            def process_input(user_input):
                result = eval(user_input)
                return result
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            cmd_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.COMMAND_INJECTION
            ]

            assert len(cmd_results) >= 1
            assert cmd_results[0].severity == SecuritySeverity.CRITICAL

    def test_detect_subprocess_shell_true(self):
        """Test detection of subprocess with shell=True."""
        code = textwrap.dedent(
            """
            import subprocess

            def run_command(cmd):
                return subprocess.run(cmd, shell=True)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            cmd_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.COMMAND_INJECTION
            ]

            assert len(cmd_results) >= 1
            assert "shell" in cmd_results[0].description.lower()

    def test_detect_hardcoded_password(self):
        """Test detection of hardcoded password."""
        code = textwrap.dedent(
            """
            DATABASE_PASSWORD = "super_secret_password123"

            def connect():
                return db.connect(password=DATABASE_PASSWORD)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            secret_results = [
                r
                for r in results
                if r.vulnerability_type
                in (
                    VulnerabilityType.HARDCODED_PASSWORD,
                    VulnerabilityType.HARDCODED_SECRET,
                )
            ]

            assert len(secret_results) >= 1
            assert secret_results[0].severity == SecuritySeverity.HIGH

    def test_detect_hardcoded_api_key(self):
        """Test detection of hardcoded API key."""
        code = textwrap.dedent(
            """
            API_KEY = "sk-1234567890abcdef1234567890abcdef"

            def call_api():
                return requests.get(url, headers={"Authorization": API_KEY})
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            api_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.HARDCODED_API_KEY
            ]

            assert len(api_results) >= 1

    def test_detect_weak_hash_md5(self):
        """Test detection of weak MD5 hash usage."""
        code = textwrap.dedent(
            """
            import hashlib

            def hash_password(password):
                return hashlib.md5(password.encode()).hexdigest()
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            hash_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.WEAK_HASH_ALGORITHM
            ]

            assert len(hash_results) >= 1
            assert "md5" in hash_results[0].description.lower()

    def test_detect_insecure_random(self):
        """Test detection of insecure random usage."""
        code = textwrap.dedent(
            """
            import random

            def generate_token():
                return random.randint(0, 1000000)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            random_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.INSECURE_RANDOM
            ]

            assert len(random_results) >= 1
            assert "secrets" in random_results[0].recommendation.lower()

    def test_detect_pickle_usage(self):
        """Test detection of insecure pickle usage."""
        code = textwrap.dedent(
            """
            import pickle

            def load_data(data):
                return pickle.loads(data)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            pickle_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.PICKLE_USAGE
            ]

            assert len(pickle_results) >= 1
            assert pickle_results[0].severity == SecuritySeverity.HIGH

    def test_detect_yaml_unsafe_load(self):
        """Test detection of unsafe yaml.load usage."""
        code = textwrap.dedent(
            """
            import yaml

            def load_config(data):
                return yaml.load(data)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            yaml_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.YAML_LOAD_UNSAFE
            ]

            assert len(yaml_results) >= 1
            assert "safe_load" in yaml_results[0].recommendation.lower()

    def test_detect_debug_mode_enabled(self):
        """Test detection of debug mode enabled."""
        code = textwrap.dedent(
            """
            DEBUG = True

            app = Flask(__name__)
            app.run(debug=DEBUG)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            debug_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.DEBUG_MODE_ENABLED
            ]

            assert len(debug_results) >= 1

    def test_no_false_positives_for_env_vars(self):
        """Test that environment variable usage doesn't trigger false positives."""
        code = textwrap.dedent(
            """
            import os

            API_KEY = os.getenv("API_KEY")
            PASSWORD = os.environ.get("DATABASE_PASSWORD")

            def connect():
                return db.connect(password=PASSWORD)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            # Should not detect hardcoded secrets when using env vars
            secret_results = [
                r
                for r in results
                if r.vulnerability_type
                in (
                    VulnerabilityType.HARDCODED_PASSWORD,
                    VulnerabilityType.HARDCODED_API_KEY,
                )
            ]

            assert len(secret_results) == 0

    def test_no_false_positives_for_safe_yaml(self):
        """Test that safe yaml usage doesn't trigger warnings."""
        code = textwrap.dedent(
            """
            import yaml

            def load_config(data):
                return yaml.safe_load(data)

            def load_with_loader(data):
                return yaml.load(data, Loader=yaml.SafeLoader)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            yaml_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.YAML_LOAD_UNSAFE
            ]

            assert len(yaml_results) == 0

    def test_analyze_directory(self, tmp_path):
        """Test directory-wide security analysis."""
        # Create test files
        (tmp_path / "safe.py").write_text(
            textwrap.dedent(
                """
            import os

            def get_config():
                return os.getenv("CONFIG")
        """
            )
        )

        (tmp_path / "vulnerable.py").write_text(
            textwrap.dedent(
                """
            import pickle

            def load(data):
                return pickle.loads(data)
        """
            )
        )

        analyzer = SecurityAnalyzer(project_root=str(tmp_path))
        results = analyzer.analyze_directory()

        # Should find issues in vulnerable.py
        assert len(results) >= 1
        assert any("vulnerable.py" in r.file_path for r in results)

    def test_get_summary(self):
        """Test summary generation."""
        code = textwrap.dedent(
            """
            import pickle
            import hashlib

            PASSWORD = "hardcoded123"

            def process(data):
                obj = pickle.loads(data)
                return hashlib.md5(PASSWORD.encode()).hexdigest()
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)
            analyzer.results = results
            summary = analyzer.get_summary()

            assert "total_findings" in summary
            assert "by_severity" in summary
            assert "security_score" in summary
            assert "risk_level" in summary
            assert summary["total_findings"] >= 1

    def test_owasp_mapping(self):
        """Test OWASP Top 10 mapping for findings."""
        code = textwrap.dedent(
            """
            def execute_query(cursor, user_input):
                cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            for result in results:
                # Every finding should have OWASP mapping
                assert result.owasp_category is not None
                assert "OWASP" in result.owasp_category or "A0" in result.owasp_category


class TestVulnerabilityTypes:
    """Test vulnerability type enumeration."""

    def test_get_vulnerability_types(self):
        """Test getting all vulnerability types."""
        types = get_vulnerability_types()

        assert len(types) > 0
        for vt in types:
            assert "type" in vt
            assert "owasp" in vt


class TestSecuritySeverity:
    """Test severity level assignments."""

    def test_critical_severity_for_injection(self):
        """Injection vulnerabilities should be CRITICAL."""
        code = textwrap.dedent(
            """
            def dangerous(user_input):
                eval(user_input)
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            injection_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.COMMAND_INJECTION
            ]

            if injection_results:
                assert injection_results[0].severity == SecuritySeverity.CRITICAL

    def test_high_severity_for_secrets(self):
        """Hardcoded secrets should be HIGH severity."""
        code = textwrap.dedent(
            """
            SECRET_KEY = "my_super_secret_key_12345678"
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            results = analyzer.analyze_file(f.name)

            secret_results = [
                r
                for r in results
                if r.vulnerability_type == VulnerabilityType.HARDCODED_SECRET
            ]

            if secret_results:
                assert secret_results[0].severity == SecuritySeverity.HIGH


class TestSecurityConvenienceFunction:
    """Test the analyze_security convenience function."""

    def test_analyze_security_function(self, tmp_path):
        """Test the convenience function."""
        (tmp_path / "test.py").write_text(
            textwrap.dedent(
                """
            def test():
                eval("1+1")
        """
            )
        )

        result = analyze_security(str(tmp_path))

        assert "results" in result
        assert "summary" in result
        assert "report" in result


class TestSecurityReport:
    """Test security report generation."""

    def test_json_report_format(self):
        """Test JSON report generation."""
        code = textwrap.dedent(
            """
            PASSWORD = "test123"
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            analyzer.analyze_file(f.name)
            report = analyzer.generate_report(format="json")

            import json

            parsed = json.loads(report)
            assert "summary" in parsed
            assert "findings" in parsed

    def test_markdown_report_format(self):
        """Test Markdown report generation."""
        code = textwrap.dedent(
            """
            PASSWORD = "test123"
        """
        )

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False, mode="w") as f:
            f.write(code)
            f.flush()

            analyzer = SecurityAnalyzer()
            analyzer.analyze_file(f.name)
            report = analyzer.generate_report(format="markdown")

            assert "# Security Analysis Report" in report
            assert "## Summary" in report


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
