# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Production code must not return a canned command result (#19807).

``WorkflowAutomationExecutor._execute_command`` slept and returned exit 0 with the
text "Simulated output". Every command step then "succeeded" without running
anything, and nothing failed to say so. The literal must not come back in
non-test code.

The detector is checked against a control string first, and the scan must have
read files, so a scanner that parses nothing cannot pass for a clean tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.lint._scan_helpers import tracked_paths  # noqa: E402

LITERAL = "Simulated output"
_MIN_FILES_SCANNED = 1000


def _is_test_path(path: str) -> bool:
    name = Path(path).name
    parts = Path(path).parts
    return name.endswith("_test.py") or name.startswith("test_") or "tests" in parts or "repo_tests" in parts


def contains_literal(source: str) -> bool:
    """Whether *source* carries the canned-output literal (case-insensitive)."""
    return LITERAL.lower() in source.lower()


def _production_python_files() -> list[str]:
    listed = tracked_paths(REPO_ROOT, "*.py")
    return [path for path in listed if not _is_test_path(path)]


def test_the_detector_sees_the_literal_and_ignores_other_text():
    assert contains_literal('"stdout": "Simulated output",')
    assert not contains_literal('"stdout": completed.stdout,')


def test_no_production_code_returns_simulated_command_output():
    files = _production_python_files()
    assert len(files) >= _MIN_FILES_SCANNED, f"scanned only {len(files)} files; the listing is broken"
    offenders = [
        path
        for path in files
        if (REPO_ROOT / path).is_file() and contains_literal((REPO_ROOT / path).read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"canned command output in non-test code: {offenders}"
