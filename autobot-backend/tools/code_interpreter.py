# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Code Interpreter Tool

Model-callable Python sandbox that executes code in a subprocess and returns
stdout/stderr.  The caller (AgentLoop) must gate execution behind the
SENSITIVE_TOOLS approval workflow — code_interpreter is listed there.

Security notes:
- Runs code as the current OS user; no sandboxing beyond what the OS provides.
- Stdout and stderr are each truncated to MAX_OUTPUT_BYTES (10 KB) so a
  runaway print loop cannot flood the agent context window.
- The temp file is always removed after execution, even on timeout/error.
"""

import os
import subprocess
import sys
import tempfile
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from services.tool_output_filter import get_tool_output_filter

logger = get_logger(__name__)

MAX_OUTPUT_BYTES = 10 * 1024  # 10 KB per stream


def execute_code(code: str, timeout_seconds: int = 30) -> Dict[str, Any]:
    """Execute Python code in a subprocess and return stdout/stderr.

    Args:
        code: Python source code to execute.
        timeout_seconds: Wall-clock timeout for the subprocess (default 30 s).

    Returns:
        Dict with keys:
            stdout     (str)  – captured standard output (≤ 10 KB)
            stderr     (str)  – captured standard error  (≤ 10 KB)
            exit_code  (int)  – process exit code (1 on timeout/error)
            truncated  (bool) – True when either stream was truncated
    """
    tmp_path: str = ""
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        result = subprocess.run(
            [sys.executable, tmp_path],
            capture_output=True,
            timeout=timeout_seconds,
        )

        raw_stdout = result.stdout
        raw_stderr = result.stderr
        truncated = len(raw_stdout) > MAX_OUTPUT_BYTES or len(raw_stderr) > MAX_OUTPUT_BYTES

        stdout_text = get_tool_output_filter().prepare_and_filter(
            "python", raw_stdout[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
        )
        return {
            "stdout": stdout_text,
            "stderr": raw_stderr[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace"),
            "exit_code": result.returncode,
            "truncated": truncated,
        }

    except subprocess.TimeoutExpired:
        logger.warning("code_interpreter: execution timed out after %ss", timeout_seconds)
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout_seconds} seconds.",
            "exit_code": 1,
            "truncated": False,
        }
    except Exception as exc:
        logger.error("code_interpreter: unexpected error: %s", exc, exc_info=True)
        return {
            "stdout": "",
            "stderr": f"Execution error: {exc}",
            "exit_code": 1,
            "truncated": False,
        }
    finally:
        if tmp_path:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


#: Tool schema for LLM tool-call registration.
CODE_INTERPRETER_SCHEMA: Dict[str, Any] = {
    "name": "code_interpreter",
    "description": "Execute Python code and return stdout/stderr",
    "parameters": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python source code to execute.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Maximum execution time in seconds (default 30).",
                "default": 30,
            },
        },
        "required": ["code"],
    },
}
