# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
"""
Extractor for run_command tool output (MVA-1407).

Keys produced:
  run_command:exit_code/{cmd_class}   → int exit code, confidence 1.0
  run_command:port/{label}            → int port number, confidence 0.9
"""

from __future__ import annotations

import re
from typing import Any

# Classifies a command string into a short label
_CMD_CLASS_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\blsof\b"), "lsof"),
    (re.compile(r"\bss\b"), "ss"),
    (re.compile(r"\bnetstat\b"), "netstat"),
    (re.compile(r"\bnpm\b"), "npm"),
    (re.compile(r"\bpython\b|\bpython3\b"), "python"),
    (re.compile(r"\bpip\b"), "pip"),
    (re.compile(r"\bgit\b"), "git"),
    (re.compile(r"\bdocker\b"), "docker"),
    (re.compile(r"\bbash\b|\bsh\b"), "shell"),
]

# Patterns to extract port numbers from stdout
_PORT_PATTERNS: list[tuple[re.Pattern, str]] = [
    # lsof/netstat/ss style: ":8080 " or "0.0.0.0:8080 " or "0.0.0.0:8080\n"
    (re.compile(r":(\d{2,5})(?=\s|$)", re.MULTILINE), "listen"),
    # --port 8080 or --port=8080
    (re.compile(r"--port[=\s]+(\d{2,5})", re.IGNORECASE), "arg"),
    # "port 8080" or "PORT=8080"
    (re.compile(r"\bport[=:\s]+(\d{2,5})", re.IGNORECASE), "env"),
    # "listening on :8080" or "listening on 0.0.0.0:8080"
    (re.compile(r"listening\s+on\s+[^:]*:(\d{2,5})", re.IGNORECASE), "listen"),
    # "started on port 8080"
    (re.compile(r"started\s+on\s+port\s+(\d{2,5})", re.IGNORECASE), "start"),
]

_VALID_PORT_RANGE = range(1, 65536)


def _classify_command(cmd: str) -> str:
    for pattern, label in _CMD_CLASS_PATTERNS:
        if pattern.search(cmd):
            return label
    return "generic"


def _extract_ports(stdout: str) -> list[tuple[str, int]]:
    """Return list of (label, port) from stdout."""
    seen: set[int] = set()
    results: list[tuple[str, int]] = []
    for pattern, label in _PORT_PATTERNS:
        for match in pattern.finditer(stdout):
            port = int(match.group(1))
            if port in _VALID_PORT_RANGE and port not in seen:
                seen.add(port)
                results.append((label, port))
    return results


class RunCommandExtractor:
    """Extract exit-code and port assertions from run_command output."""

    def extract(self, tool_output: Any) -> list[tuple[str, Any, float]]:
        if not isinstance(tool_output, dict):
            return []

        cmd = tool_output.get("command") or tool_output.get("cmd") or ""
        cmd_class = _classify_command(str(cmd)) if cmd else "generic"

        results: list[tuple[str, Any, float]] = []

        exit_code = (
            tool_output.get("exit_code") if tool_output.get("exit_code") is not None else tool_output.get("returncode")
        )
        if exit_code is not None:
            results.append((f"run_command:exit_code/{cmd_class}", int(exit_code), 1.0))

        stdout = tool_output.get("stdout") or tool_output.get("output") or ""
        if stdout:
            for label, port in _extract_ports(str(stdout)):
                results.append((f"run_command:port/{label}", port, 0.9))

        return results
