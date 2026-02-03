# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Pre-commit Hook Analyzer

Tests the detection of pre-commit issues including:
- Security issues (hardcoded credentials, API keys)
- Debug statements (console.log, print, debugger)
- Code quality issues (empty except blocks)
- Style issues (trailing whitespace)
- Documentation issues (missing docstrings)

Part of Issue #223 - Git Pre-commit Hook Analyzer
Parent Epic: #217 - Advanced Code Intelligence
"""

import textwrap

import pytest

from src.code_intelligence.precommit_analyzer import (
    CheckCategory,
    CheckDefinition,
    CheckSeverity,
    PrecommitAnalyzer,
    get_check_categories,
    get_precommit_checks,
)


class TestSecurityChecks:
    """Test security-related pre-commit checks."""

    def test_detect_hardcoded_password(self):
        """Test detection of hardcoded passwords."""
        code = textwrap.dedent(
            '''
            DATABASE_PASSWORD = "super_secret_123"

            def connect():
                return db.connect(password=DATABASE_PASSWORD)
        '''
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "config.py")

        password_results = [
            r for r in results if r.check_id == "SEC001" and not r.passed
        ]

        assert len(password_results) >= 1
        assert password_results[0].severity == CheckSeverity.BLOCK

    def test_detect_api_key(self):
        """Test detection of exposed API keys."""
        code = textwrap.dedent(
            '''
            API_KEY = "sk-1234567890abcdef1234567890abcdef"
            SECRET_KEY = "abcdef1234567890abcdef1234567890"
        '''
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "config.py")

        api_results = [r for r in results if r.check_id == "SEC002" and not r.passed]

        assert len(api_results) >= 1
        assert api_results[0].severity == CheckSeverity.BLOCK

    def test_detect_private_key(self):
        """Test detection of private keys in code."""
        code = textwrap.dedent(
            """
            PRIVATE_KEY = '''-----BEGIN RSA PRIVATE KEY-----
            MIIEpAIBAAKCAQEA0Z...
            -----END RSA PRIVATE KEY-----'''
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "keys.py")

        key_results = [r for r in results if r.check_id == "SEC003" and not r.passed]

        assert len(key_results) >= 1
        assert key_results[0].severity == CheckSeverity.BLOCK

    def test_detect_hardcoded_ip(self):
        """Test detection of hardcoded IP addresses."""
        code = textwrap.dedent(
            """
            SERVER_IP = "192.168.1.100"

            def connect():
                return socket.connect(SERVER_IP, 8080)
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "network.py")

        ip_results = [r for r in results if r.check_id == "SEC004" and not r.passed]

        assert len(ip_results) >= 1
        assert ip_results[0].severity == CheckSeverity.WARN

    def test_detect_aws_key(self):
        """Test detection of AWS access keys."""
        code = textwrap.dedent(
            """
            AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "aws.py")

        aws_results = [r for r in results if r.check_id == "SEC005" and not r.passed]

        assert len(aws_results) >= 1
        assert aws_results[0].severity == CheckSeverity.BLOCK

    def test_detect_jwt_token(self):
        """Test detection of JWT tokens in code."""
        # JWT token split across lines for readability
        jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        jwt += ".eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ"
        jwt += ".SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        code = f'TOKEN = "{jwt}"'

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "auth.py")

        jwt_results = [r for r in results if r.check_id == "SEC006" and not r.passed]

        assert len(jwt_results) >= 1
        assert jwt_results[0].severity == CheckSeverity.BLOCK


class TestDebugChecks:
    """Test debug statement detection."""

    def test_detect_console_log(self):
        """Test detection of console.log statements."""
        code = textwrap.dedent(
            """
            function processData(data) {
                console.log("Processing:", data);
                console.debug("Debug info");
                return data;
            }
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "app.js")

        console_results = [
            r for r in results if r.check_id == "DBG001" and not r.passed
        ]

        assert len(console_results) >= 2

    def test_detect_print_statement(self):
        """Test detection of print statements in Python."""
        code = textwrap.dedent(
            """
            def process_data(items):
                for item in items:
                    print(f"Processing: {item}")
                return items
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "process.py")

        print_results = [r for r in results if r.check_id == "DBG002" and not r.passed]

        assert len(print_results) >= 1
        assert print_results[0].severity == CheckSeverity.WARN

    def test_detect_debugger_statement(self):
        """Test detection of debugger statements."""
        code = textwrap.dedent(
            """
            import pdb

            def buggy_function(x):
                pdb.set_trace()
                return x * 2
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "debug.py")

        debugger_results = [
            r for r in results if r.check_id == "DBG003" and not r.passed
        ]

        assert len(debugger_results) >= 1
        assert debugger_results[0].severity == CheckSeverity.BLOCK

    def test_detect_breakpoint(self):
        """Test detection of breakpoint() call."""
        code = textwrap.dedent(
            """
            def test_function(x):
                breakpoint()
                return x
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "test.py")

        debugger_results = [
            r for r in results if r.check_id == "DBG003" and not r.passed
        ]

        assert len(debugger_results) >= 1

    def test_detect_todo_comment(self):
        """Test detection of TODO/FIXME comments."""
        code = textwrap.dedent(
            """
            def incomplete_function():
                # TODO: Implement this properly
                # FIXME: This is broken
                pass
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "wip.py")

        todo_results = [r for r in results if r.check_id == "DBG004" and not r.passed]

        assert len(todo_results) >= 2
        assert todo_results[0].severity == CheckSeverity.INFO


class TestQualityChecks:
    """Test code quality checks."""

    def test_detect_empty_except(self):
        """Test detection of empty except blocks."""
        code = textwrap.dedent(
            """
            def risky_operation():
                try:
                    do_something()
                except:
                    pass
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "handler.py")

        except_results = [
            r for r in results if r.check_id in ("QUA001", "QUA002") and not r.passed
        ]

        assert len(except_results) >= 1

    def test_detect_bare_except(self):
        """Test detection of bare except clauses."""
        code = textwrap.dedent(
            """
            try:
                result = process()
            except:
                log_error()
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "handler.py")

        bare_except_results = [
            r for r in results if r.check_id == "QUA002" and not r.passed
        ]

        assert len(bare_except_results) >= 1

    def test_detect_hardcoded_port(self):
        """Test detection of hardcoded port numbers."""
        code = textwrap.dedent(
            """
            port = 8080
            server_port = 3000
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "config.py")

        port_results = [r for r in results if r.check_id == "QUA004" and not r.passed]

        assert len(port_results) >= 1


class TestStyleChecks:
    """Test style-related checks."""

    def test_detect_trailing_whitespace(self):
        """Test detection of trailing whitespace."""
        # Note: The code has intentional trailing spaces
        code = "def func():   \n    pass\n"

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "style.py")

        whitespace_results = [
            r for r in results if r.check_id == "STY001" and not r.passed
        ]

        assert len(whitespace_results) >= 1
        assert whitespace_results[0].severity == CheckSeverity.INFO

    def test_detect_mixed_tabs_spaces(self):
        """Test detection of mixed tabs and spaces."""
        code = "\t def func():\n\t     pass\n"

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "mixed.py")

        mixed_results = [r for r in results if r.check_id == "STY002" and not r.passed]

        assert len(mixed_results) >= 1


class TestFastMode:
    """Test fast mode functionality."""

    def test_fast_mode_skips_expensive_checks(self):
        """Test that fast mode skips expensive checks."""
        code = textwrap.dedent(
            """
            def function_without_docstring():
                return 42
        """
        )

        # Normal mode should include DOC001
        analyzer_normal = PrecommitAnalyzer(fast_mode=False)
        results_normal = analyzer_normal.analyze_content(code, "test.py")

        # Fast mode should skip DOC001
        analyzer_fast = PrecommitAnalyzer(fast_mode=True)
        results_fast = analyzer_fast.analyze_content(code, "test.py")

        doc_normal = [r for r in results_normal if r.check_id == "DOC001"]
        doc_fast = [r for r in results_fast if r.check_id == "DOC001"]

        # Fast mode should have fewer or no DOC001 results
        assert len(doc_fast) <= len(doc_normal)


class TestFilePatternMatching:
    """Test file pattern matching for checks."""

    def test_python_only_checks(self):
        """Test that Python-specific checks only apply to .py files."""
        code = "print('hello')"

        analyzer = PrecommitAnalyzer()

        # Should match for .py
        py_results = analyzer.analyze_content(code, "test.py")
        py_print = [r for r in py_results if r.check_id == "DBG002"]

        # Should not match for .js
        js_results = analyzer.analyze_content(code, "test.js")
        js_print = [r for r in js_results if r.check_id == "DBG002"]

        assert len(py_print) >= 1
        assert len(js_print) == 0

    def test_javascript_only_checks(self):
        """Test that JavaScript-specific checks only apply to .js files."""
        code = "console.log('hello');"

        analyzer = PrecommitAnalyzer()

        # Should match for .js
        js_results = analyzer.analyze_content(code, "test.js")
        js_console = [r for r in js_results if r.check_id == "DBG001"]

        # Should not match for .py
        py_results = analyzer.analyze_content(code, "test.py")
        py_console = [r for r in py_results if r.check_id == "DBG001"]

        assert len(js_console) >= 1
        assert len(py_console) == 0


class TestCheckManagement:
    """Test check enable/disable functionality."""

    def test_disable_check(self):
        """Test disabling a specific check."""
        code = 'PASSWORD = "secret123"'

        analyzer = PrecommitAnalyzer()

        # First check with enabled
        results_enabled = analyzer.analyze_content(code, "test.py")
        sec001_enabled = [r for r in results_enabled if r.check_id == "SEC001"]

        # Disable and check again
        analyzer.disable_check("SEC001")
        results_disabled = analyzer.analyze_content(code, "test.py")
        sec001_disabled = [r for r in results_disabled if r.check_id == "SEC001"]

        assert len(sec001_enabled) >= 1
        assert len(sec001_disabled) == 0

    def test_enable_check(self):
        """Test enabling a previously disabled check."""
        analyzer = PrecommitAnalyzer()

        analyzer.disable_check("SEC001")
        assert not analyzer.checks["SEC001"].enabled

        analyzer.enable_check("SEC001")
        assert analyzer.checks["SEC001"].enabled

    def test_add_custom_check(self):
        """Test adding a custom check."""
        custom_check = CheckDefinition(
            id="CUSTOM001",
            name="Custom Pattern",
            category=CheckCategory.QUALITY,
            severity=CheckSeverity.WARN,
            pattern=r"FORBIDDEN_PATTERN",
            description="Custom forbidden pattern detected",
            suggestion="Remove the forbidden pattern",
        )

        analyzer = PrecommitAnalyzer()
        analyzer.add_custom_check(custom_check)

        code = "x = FORBIDDEN_PATTERN"
        results = analyzer.analyze_content(code, "test.py")

        custom_results = [r for r in results if r.check_id == "CUSTOM001"]
        assert len(custom_results) >= 1


class TestAnalyzeFiles:
    """Test file analysis functionality."""

    def test_analyze_file(self, tmp_path):
        """Test analyzing a single file."""
        test_file = tmp_path / "test.py"
        test_file.write_text('PASSWORD = "secret123"\n')

        analyzer = PrecommitAnalyzer(project_root=str(tmp_path))
        results = analyzer.analyze_file(str(test_file))

        assert len(results) >= 1
        assert any(r.check_id == "SEC001" for r in results)

    def test_analyze_multiple_files(self, tmp_path):
        """Test analyzing multiple files."""
        (tmp_path / "file1.py").write_text('PASSWORD = "secret"\n')
        (tmp_path / "file2.js").write_text("console.log('test');\n")

        analyzer = PrecommitAnalyzer(project_root=str(tmp_path))
        result = analyzer.analyze_files(
            [str(tmp_path / "file1.py"), str(tmp_path / "file2.js")]
        )

        assert result.files_checked == [
            str(tmp_path / "file1.py"),
            str(tmp_path / "file2.js"),
        ]
        assert result.failed_checks >= 2

    def test_analyze_files_parallel(self, tmp_path):
        """Test parallel file analysis."""
        for i in range(5):
            (tmp_path / f"file{i}.py").write_text('PASSWORD = "secret"\n')

        files = [str(tmp_path / f"file{i}.py") for i in range(5)]

        analyzer = PrecommitAnalyzer(project_root=str(tmp_path), parallel=True)
        result = analyzer.analyze_files(files)

        assert len(result.files_checked) == 5
        assert result.failed_checks >= 5


class TestCommitCheckResult:
    """Test CommitCheckResult functionality."""

    def test_blocking_result(self):
        """Test that BLOCK severity issues block commit."""
        # Use a private key which is definitely BLOCK severity
        code = '-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBg...\n-----END PRIVATE KEY-----'

        analyzer = PrecommitAnalyzer()

        # Manually analyze content
        results = analyzer.analyze_content(code, "test.py")
        analyzer.results = results

        # Check blocking
        has_block = any(
            r.severity == CheckSeverity.BLOCK and not r.passed for r in results
        )
        assert has_block

    def test_warning_result(self):
        """Test that WARN severity issues show warnings."""
        code = 'SERVER_IP = "192.168.1.1"'

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "test.py")

        warnings = [
            r for r in results if r.severity == CheckSeverity.WARN and not r.passed
        ]
        assert len(warnings) >= 1

    def test_to_dict_serialization(self):
        """Test result serialization."""
        analyzer = PrecommitAnalyzer()
        result = analyzer.analyze_files([])
        result_dict = result.to_dict()

        assert "passed" in result_dict
        assert "blocked" in result_dict
        assert "duration_ms" in result_dict
        assert "results" in result_dict


class TestSummary:
    """Test summary generation."""

    def test_get_summary(self):
        """Test summary generation."""
        code = textwrap.dedent(
            '''
            PASSWORD = "secret123"
            print("debug")
            # TODO: Fix this
        '''
        )

        analyzer = PrecommitAnalyzer()
        analyzer.results = analyzer.analyze_content(code, "test.py")
        summary = analyzer.get_summary()

        assert "total_issues" in summary
        assert "by_severity" in summary
        assert "by_category" in summary
        assert summary["total_issues"] >= 1


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_get_precommit_checks(self):
        """Test getting all checks."""
        checks = get_precommit_checks()

        assert len(checks) > 0
        for check in checks:
            assert "id" in check
            assert "name" in check
            assert "category" in check
            assert "severity" in check

    def test_get_check_categories(self):
        """Test getting check categories."""
        categories = get_check_categories()

        assert len(categories) > 0
        for cat in categories:
            assert "category" in cat
            assert "enabled" in cat
            assert "total" in cat


class TestSnippetGeneration:
    """Test code snippet generation."""

    def test_snippet_with_context(self):
        """Test that snippets include context lines."""
        code = textwrap.dedent(
            """
            def function1():
                pass

            PASSWORD = "secret123"

            def function2():
                pass
        """
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "test.py")

        password_results = [r for r in results if r.check_id == "SEC001"]

        if password_results:
            snippet = password_results[0].snippet
            # Snippet should have multiple lines
            assert "\n" in snippet
            # Snippet should have line numbers
            assert ":" in snippet


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_content(self):
        """Test analysis of empty content."""
        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content("", "test.py")

        assert len(results) == 0

    def test_no_issues(self):
        """Test clean code with no issues."""
        code = textwrap.dedent(
            '''
            """Clean module."""
            import os

            def get_password():
                """Get password from environment."""
                return os.getenv("PASSWORD")
        '''
        )

        analyzer = PrecommitAnalyzer()
        results = analyzer.analyze_content(code, "clean.py")

        # Filter out INFO level issues
        blocking_or_warning = [
            r
            for r in results
            if r.severity in (CheckSeverity.BLOCK, CheckSeverity.WARN) and not r.passed
        ]

        assert len(blocking_or_warning) == 0

    def test_nonexistent_file(self):
        """Test handling of nonexistent file."""
        analyzer = PrecommitAnalyzer()
        content = analyzer.get_file_content("/nonexistent/path/file.py")

        assert content is None


class TestGetCheck:
    """Test getting individual checks."""

    def test_get_existing_check(self):
        """Test getting an existing check."""
        analyzer = PrecommitAnalyzer()
        check = analyzer.get_check("SEC001")

        assert check is not None
        assert check.id == "SEC001"
        assert check.name == "Hardcoded Password"

    def test_get_nonexistent_check(self):
        """Test getting a nonexistent check."""
        analyzer = PrecommitAnalyzer()
        check = analyzer.get_check("NONEXISTENT")

        assert check is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
