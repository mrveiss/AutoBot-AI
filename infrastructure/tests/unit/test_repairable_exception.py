# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for Issue #655 - RepairableException for Soft Error Recovery.

Tests verify:
1. RepairableException class works correctly
2. Error classification identifies repairable vs critical errors
3. LLM context formatting is appropriate
4. Integration with tool handler works
"""

import pytest

from src.utils.errors import (
    REPAIRABLE_EXCEPTIONS,
    CriticalException,
    RepairableException,
    is_repairable,
    wrap_as_repairable,
)


class TestRepairableException:
    """Test RepairableException class functionality."""

    def test_basic_creation(self):
        """Test basic exception creation."""
        exc = RepairableException("Something went wrong")
        assert exc.message == "Something went wrong"
        assert exc.suggestion == "Try a different approach."  # Default
        assert exc.recoverable is True

    def test_custom_suggestion(self):
        """Test exception with custom suggestion."""
        exc = RepairableException("File not found", suggestion="Create the file first")
        assert exc.message == "File not found"
        assert exc.suggestion == "Create the file first"

    def test_with_original_exception(self):
        """Test wrapping an original exception."""
        original = FileNotFoundError("config.txt")
        exc = RepairableException(
            "Config file missing",
            suggestion="Create config.txt with defaults",
            original_exception=original,
        )
        assert exc.original_exception is original
        assert isinstance(exc.original_exception, FileNotFoundError)

    def test_str_format(self):
        """Test string representation includes suggestion."""
        exc = RepairableException("Permission denied", suggestion="Use sudo")
        result = str(exc)
        assert "Permission denied" in result
        assert "Use sudo" in result

    def test_to_llm_context(self):
        """Test LLM context formatting."""
        exc = RepairableException(
            "Command timed out", suggestion="Break into smaller steps"
        )
        context = exc.to_llm_context()
        assert "Tool Error (Recoverable)" in context
        assert "Command timed out" in context
        assert "Break into smaller steps" in context
        assert "try a different approach" in context.lower()


class TestCriticalException:
    """Test CriticalException class functionality."""

    def test_basic_creation(self):
        """Test basic critical exception creation."""
        exc = CriticalException("System failure")
        assert exc.message == "System failure"
        assert exc.recoverable is False
        assert exc.error_code is None

    def test_with_error_code(self):
        """Test critical exception with error code."""
        exc = CriticalException("Unauthorized access", error_code="AUTH_DENIED")
        assert exc.error_code == "AUTH_DENIED"
        assert "[AUTH_DENIED]" in str(exc)

    def test_with_original_exception(self):
        """Test wrapping an original exception."""
        original = MemoryError("out of memory")
        exc = CriticalException("Memory exhausted", original_exception=original)
        assert exc.original_exception is original


class TestWrapAsRepairable:
    """Test wrap_as_repairable function."""

    def test_wrap_file_not_found(self):
        """FileNotFoundError should be wrapped as repairable."""
        original = FileNotFoundError("missing.txt")
        result = wrap_as_repairable(original, context="Reading config")
        assert isinstance(result, RepairableException)
        assert "Reading config" in result.message
        assert result.original_exception is original

    def test_wrap_permission_error(self):
        """PermissionError should be wrapped as repairable."""
        original = PermissionError("Access denied")
        result = wrap_as_repairable(original)
        assert isinstance(result, RepairableException)
        assert (
            "sudo" in result.suggestion.lower()
            or "directory" in result.suggestion.lower()
        )

    def test_wrap_timeout_error(self):
        """TimeoutError should be wrapped as repairable."""
        original = TimeoutError("Operation timed out")
        result = wrap_as_repairable(original)
        assert isinstance(result, RepairableException)
        assert (
            "timeout" in result.suggestion.lower()
            or "smaller" in result.suggestion.lower()
        )

    def test_memory_error_not_repairable(self):
        """MemoryError should NOT be repairable - should re-raise."""
        original = MemoryError("out of memory")
        with pytest.raises(MemoryError):
            wrap_as_repairable(original)

    def test_unknown_exception_defaults_repairable(self):
        """Unknown exceptions default to repairable."""

        class CustomError(Exception):
            pass

        original = CustomError("something custom")
        result = wrap_as_repairable(original)
        assert isinstance(result, RepairableException)


class TestIsRepairable:
    """Test is_repairable function."""

    def test_repairable_exception_is_repairable(self):
        """RepairableException should return True."""
        exc = RepairableException("test")
        assert is_repairable(exc) is True

    def test_critical_exception_not_repairable(self):
        """CriticalException should return False."""
        exc = CriticalException("test")
        assert is_repairable(exc) is False

    def test_file_not_found_is_repairable(self):
        """FileNotFoundError should be repairable."""
        exc = FileNotFoundError("missing.txt")
        assert is_repairable(exc) is True

    def test_memory_error_not_repairable(self):
        """MemoryError should NOT be repairable."""
        exc = MemoryError("out of memory")
        assert is_repairable(exc) is False

    def test_unknown_exception_defaults_true(self):
        """Unknown exceptions default to repairable."""

        class UnknownError(Exception):
            pass

        exc = UnknownError("unknown")
        assert is_repairable(exc) is True


class TestErrorClassification:
    """Test error classification in tool handler."""

    def test_classify_file_not_found(self):
        """File not found errors should be repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="cat /missing/file.txt",
            error="cat: /missing/file.txt: No such file or directory",
            stderr="",
        )
        assert result is not None
        assert isinstance(result, RepairableException)
        assert "file" in result.message.lower() or "not found" in result.message.lower()

    def test_classify_permission_denied(self):
        """Permission denied errors should be repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="rm /etc/passwd",
            error="Permission denied",
            stderr="rm: cannot remove '/etc/passwd': Permission denied",
        )
        assert result is not None
        assert isinstance(result, RepairableException)
        assert (
            "sudo" in result.suggestion.lower()
            or "permission" in result.suggestion.lower()
        )

    def test_classify_command_not_found(self):
        """Command not found errors should be repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="unknowncmd --help",
            error="unknowncmd: command not found",
            stderr="",
        )
        assert result is not None
        assert isinstance(result, RepairableException)
        assert (
            "install" in result.suggestion.lower()
            or "alternative" in result.suggestion.lower()
        )

    def test_classify_timeout(self):
        """Timeout errors should be repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="ping 10.0.0.1", error="Operation timed out", stderr=""
        )
        assert result is not None
        assert isinstance(result, RepairableException)
        assert (
            "timeout" in result.suggestion.lower()
            or "smaller" in result.suggestion.lower()
        )

    def test_classify_connection_error(self):
        """Connection errors should be repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="curl http://localhost:9999", error="Connection refused", stderr=""
        )
        assert result is not None
        assert isinstance(result, RepairableException)
        assert (
            "network" in result.suggestion.lower()
            or "connectivity" in result.suggestion.lower()
        )

    def test_classify_out_of_memory(self):
        """Out of memory errors should NOT be repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="python huge_script.py", error="Out of memory", stderr=""
        )
        assert result is None  # Critical error

    def test_classify_generic_error_is_repairable(self):
        """Unknown errors should default to repairable."""
        from src.chat_workflow.tool_handler import ToolHandlerMixin

        handler = ToolHandlerMixin()
        result = handler._classify_command_error(
            command="some_cmd", error="Some random error occurred", stderr=""
        )
        assert result is not None
        assert isinstance(result, RepairableException)


class TestRepairableExceptionMapping:
    """Test the REPAIRABLE_EXCEPTIONS mapping."""

    def test_all_repairable_have_suggestions(self):
        """All repairable exceptions should have suggestions."""
        for exc_type, mapping in REPAIRABLE_EXCEPTIONS.items():
            if mapping["repairable"]:
                assert (
                    mapping["suggestion"] is not None
                ), f"{exc_type.__name__} is repairable but has no suggestion"

    def test_critical_exceptions_no_suggestion(self):
        """Critical exceptions should not have suggestions."""
        for exc_type, mapping in REPAIRABLE_EXCEPTIONS.items():
            if not mapping["repairable"]:
                assert (
                    mapping["suggestion"] is None
                ), f"{exc_type.__name__} is critical but has a suggestion"

    def test_expected_repairable_types(self):
        """Verify expected exception types are marked repairable."""
        repairable_types = [
            FileNotFoundError,
            PermissionError,
            TimeoutError,
            ConnectionError,
            ValueError,
            KeyError,
        ]
        for exc_type in repairable_types:
            assert exc_type in REPAIRABLE_EXCEPTIONS
            assert REPAIRABLE_EXCEPTIONS[exc_type]["repairable"] is True

    def test_expected_critical_types(self):
        """Verify expected exception types are marked critical."""
        critical_types = [
            MemoryError,
            SystemExit,
            KeyboardInterrupt,
        ]
        for exc_type in critical_types:
            assert exc_type in REPAIRABLE_EXCEPTIONS
            assert REPAIRABLE_EXCEPTIONS[exc_type]["repairable"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
