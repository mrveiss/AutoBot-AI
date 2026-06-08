# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for the code_interpreter tool (#4520).

Covers:
- Successful code execution and stdout/stderr capture
- Exit code propagation
- Output truncation at MAX_OUTPUT_BYTES (10 KB)
- Timeout handling
- Runtime error / exception handling
- Temp file cleanup on success, timeout, and error
- Schema structure validation
"""

import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from tools.code_interpreter import CODE_INTERPRETER_SCHEMA, MAX_OUTPUT_BYTES, execute_code

# ---------------------------------------------------------------------------
# Happy-path execution
# ---------------------------------------------------------------------------


class TestExecuteCodeSuccess:
    """Tests for successful code execution paths."""

    def test_simple_print_captured_in_stdout(self):
        result = execute_code('print("hello world")')
        assert result["stdout"].strip() == "hello world"
        assert result["stderr"] == ""
        assert result["exit_code"] == 0
        assert result["truncated"] is False

    def test_stderr_captured(self):
        result = execute_code("import sys; sys.stderr.write('err line\\n')")
        assert "err line" in result["stderr"]
        assert result["exit_code"] == 0
        assert result["truncated"] is False

    def test_exit_code_nonzero_on_sys_exit(self):
        result = execute_code("import sys; sys.exit(42)")
        assert result["exit_code"] == 42

    def test_both_streams_captured(self):
        code = "import sys; print('out'); sys.stderr.write('err')"
        result = execute_code(code)
        assert "out" in result["stdout"]
        assert "err" in result["stderr"]
        assert result["exit_code"] == 0

    def test_multiline_output(self):
        code = "\n".join(f"print({i})" for i in range(5))
        result = execute_code(code)
        for i in range(5):
            assert str(i) in result["stdout"]

    def test_unicode_output(self):
        result = execute_code('print("\\u4e2d\\u6587")')  # Chinese characters
        assert result["exit_code"] == 0
        assert result["stdout"] != ""

    def test_empty_code_runs_without_error(self):
        result = execute_code("")
        assert result["exit_code"] == 0
        assert result["stdout"] == ""
        assert result["stderr"] == ""
        assert result["truncated"] is False


# ---------------------------------------------------------------------------
# Runtime errors
# ---------------------------------------------------------------------------


class TestExecuteCodeRuntimeErrors:
    """Tests for code that raises exceptions or syntax errors."""

    def test_runtime_exception_captured_in_stderr(self):
        result = execute_code("raise ValueError('bad value')")
        assert result["exit_code"] != 0
        assert "ValueError" in result["stderr"]
        assert result["stdout"] == ""

    def test_syntax_error_captured_in_stderr(self):
        result = execute_code("def broken(:")
        assert result["exit_code"] != 0
        assert result["stderr"] != ""

    def test_import_error_captured_in_stderr(self):
        result = execute_code("import nonexistent_module_xyz")
        assert result["exit_code"] != 0
        assert "nonexistent_module_xyz" in result["stderr"]

    def test_division_by_zero_captured(self):
        result = execute_code("x = 1 / 0")
        assert result["exit_code"] != 0
        assert "ZeroDivisionError" in result["stderr"]


# ---------------------------------------------------------------------------
# Output truncation
# ---------------------------------------------------------------------------


class TestOutputTruncation:
    """Tests for MAX_OUTPUT_BYTES truncation logic."""

    def test_truncated_flag_false_when_within_limit(self):
        result = execute_code('print("x" * 100)')
        assert result["truncated"] is False

    def test_stdout_truncated_at_max_bytes(self):
        # Generate slightly more than MAX_OUTPUT_BYTES of output
        oversize = MAX_OUTPUT_BYTES + 100
        code = f"print('A' * {oversize})"
        result = execute_code(code)
        assert result["truncated"] is True
        assert len(result["stdout"]) <= MAX_OUTPUT_BYTES

    def test_stderr_truncated_at_max_bytes(self):
        oversize = MAX_OUTPUT_BYTES + 100
        code = f"import sys; sys.stderr.write('B' * {oversize})"
        result = execute_code(code)
        assert result["truncated"] is True
        assert len(result["stderr"]) <= MAX_OUTPUT_BYTES

    def test_truncated_flag_true_when_stdout_exceeds_limit(self):
        """truncated must be True even if stderr is within limit."""
        oversize = MAX_OUTPUT_BYTES + 50
        code = f"print('X' * {oversize})"
        result = execute_code(code)
        assert result["truncated"] is True


# ---------------------------------------------------------------------------
# Timeout handling
# ---------------------------------------------------------------------------


class TestTimeout:
    """Tests for subprocess.TimeoutExpired handling."""

    def test_timeout_returns_error_dict(self):
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["python"], timeout=1)
            result = execute_code("while True: pass", timeout_seconds=1)

        assert result["exit_code"] == 1
        assert "timed out" in result["stderr"].lower()
        assert result["stdout"] == ""
        assert result["truncated"] is False

    def test_timeout_message_includes_seconds(self):
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.TimeoutExpired(cmd=["python"], timeout=5)
            result = execute_code("while True: pass", timeout_seconds=5)

        assert "5" in result["stderr"]

    def test_default_timeout_is_30_seconds(self):
        """Verify the default argument value without actually waiting."""
        import inspect

        sig = inspect.signature(execute_code)
        assert sig.parameters["timeout_seconds"].default == 30


# ---------------------------------------------------------------------------
# Unexpected / OS-level errors
# ---------------------------------------------------------------------------


class TestUnexpectedErrors:
    """Tests for non-TimeoutExpired exceptions from subprocess.run."""

    def test_os_error_returns_error_dict(self):
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_run.side_effect = OSError("no such file")
            result = execute_code("print('hi')")

        assert result["exit_code"] == 1
        assert "no such file" in result["stderr"]
        assert result["stdout"] == ""
        assert result["truncated"] is False

    def test_permission_error_handled(self):
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_run.side_effect = PermissionError("denied")
            result = execute_code("print('hi')")

        assert result["exit_code"] == 1
        assert "denied" in result["stderr"]


# ---------------------------------------------------------------------------
# Temp file cleanup
# ---------------------------------------------------------------------------


class TestTempFileCleanup:
    """Verify temp files are removed regardless of execution outcome."""

    def test_tempfile_removed_after_success(self):
        created_paths = []
        __import__("tempfile").NamedTemporaryFile

        import tempfile as _tempfile

        real_ntf = _tempfile.NamedTemporaryFile

        def capturing_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(f.name)
            return f

        with patch("tools.code_interpreter.tempfile.NamedTemporaryFile", side_effect=capturing_ntf):
            execute_code('print("ok")')

        import os

        for p in created_paths:
            assert not os.path.exists(p), f"Temp file not cleaned up: {p}"

    def test_tempfile_removed_after_timeout(self):
        created_paths = []

        import tempfile as _tempfile

        real_ntf = _tempfile.NamedTemporaryFile

        def capturing_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(f.name)
            return f

        with patch("tools.code_interpreter.tempfile.NamedTemporaryFile", side_effect=capturing_ntf):
            with patch("tools.code_interpreter.subprocess.run") as mock_run:
                mock_run.side_effect = subprocess.TimeoutExpired(cmd=["python"], timeout=1)
                execute_code("while True: pass", timeout_seconds=1)

        import os

        for p in created_paths:
            assert not os.path.exists(p), f"Temp file not cleaned up after timeout: {p}"

    def test_tempfile_removed_after_os_error(self):
        created_paths = []

        import tempfile as _tempfile

        real_ntf = _tempfile.NamedTemporaryFile

        def capturing_ntf(*args, **kwargs):
            f = real_ntf(*args, **kwargs)
            created_paths.append(f.name)
            return f

        with patch("tools.code_interpreter.tempfile.NamedTemporaryFile", side_effect=capturing_ntf):
            with patch("tools.code_interpreter.subprocess.run") as mock_run:
                mock_run.side_effect = OSError("fail")
                execute_code("print('hi')")

        import os

        for p in created_paths:
            assert not os.path.exists(p), f"Temp file not cleaned up after error: {p}"


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestCodeInterpreterSchema:
    """Verify the LLM tool schema structure."""

    def test_schema_has_required_top_level_keys(self):
        assert "name" in CODE_INTERPRETER_SCHEMA
        assert "description" in CODE_INTERPRETER_SCHEMA
        assert "parameters" in CODE_INTERPRETER_SCHEMA

    def test_schema_name_is_code_interpreter(self):
        assert CODE_INTERPRETER_SCHEMA["name"] == "code_interpreter"

    def test_schema_parameters_type_is_object(self):
        assert CODE_INTERPRETER_SCHEMA["parameters"]["type"] == "object"

    def test_schema_code_property_defined(self):
        props = CODE_INTERPRETER_SCHEMA["parameters"]["properties"]
        assert "code" in props
        assert props["code"]["type"] == "string"

    def test_schema_timeout_seconds_property_defined(self):
        props = CODE_INTERPRETER_SCHEMA["parameters"]["properties"]
        assert "timeout_seconds" in props
        assert props["timeout_seconds"]["type"] == "integer"
        assert props["timeout_seconds"]["default"] == 30

    def test_schema_code_is_required(self):
        required = CODE_INTERPRETER_SCHEMA["parameters"].get("required", [])
        assert "code" in required

    def test_schema_description_is_nonempty_string(self):
        assert isinstance(CODE_INTERPRETER_SCHEMA["description"], str)
        assert len(CODE_INTERPRETER_SCHEMA["description"]) > 0


# ---------------------------------------------------------------------------
# subprocess invocation details
# ---------------------------------------------------------------------------


class TestSubprocessInvocation:
    """Verify execute_code calls subprocess with correct arguments."""

    def test_uses_current_python_executable(self):
        """Subprocess must use the same interpreter (sys.executable)."""
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = b""
            mock_result.stderr = b""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            execute_code("pass")

        call_args = mock_run.call_args
        cmd = call_args[0][0]
        assert cmd[0] == sys.executable

    def test_capture_output_is_enabled(self):
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = b""
            mock_result.stderr = b""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            execute_code("pass")

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("capture_output") is True

    def test_timeout_forwarded_to_subprocess(self):
        with patch("tools.code_interpreter.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = b""
            mock_result.stderr = b""
            mock_result.returncode = 0
            mock_run.return_value = mock_result

            execute_code("pass", timeout_seconds=99)

        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("timeout") == 99


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
