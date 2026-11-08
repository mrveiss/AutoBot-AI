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

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
sys.path.insert(0, str(REPO_ROOT))

from repo_tests._reach import declare  # noqa: E402

from autobot_shared.testfile_names import is_test_filename
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths  # noqa: E402

LITERAL = "Simulated output"


def _is_test_path(path: str) -> bool:
    parts = Path(path).parts
    return is_test_filename(path, include_js=False) or "tests" in parts or "repo_tests" in parts


def contains_literal(source: str) -> bool:
    """Whether *source* carries the canned-output literal (case-insensitive)."""
    return LITERAL.lower() in source.lower()


def _production_python_files(root: Path) -> list[str]:
    """Tracked non-test ``.py`` files that exist in the working tree, i.e. the files that can be read."""
    try:
        listed = tracked_paths(root, "*.py")
    except EmptyEnumeration:
        return []
    return [path for path in listed if not _is_test_path(path) and (root / path).is_file()]


def _all_python(root: Path) -> int:
    try:
        return len(tracked_paths(root, "*.py"))
    except EmptyEnumeration:
        return 0


#: Measured ~49% of tracked ``.py`` is non-test and present on disk; 0.35 leaves room for tests to grow.
FRACTION = 0.35

REACH = declare(
    "no-simulated-command-output-19807-scan",
    discover=_production_python_files,
    what="tracked non-test Python files present in the working tree",
    reference=_all_python,
    min_fraction=FRACTION,
)


def test_the_detector_sees_the_literal_and_ignores_other_text():
    assert contains_literal('"stdout": "Simulated output",')
    assert not contains_literal('"stdout": completed.stdout,')


def test_no_production_code_returns_simulated_command_output():
    read = REACH.examined(REPO_ROOT)
    offenders = [path for path in read if contains_literal((REPO_ROOT / path).read_text(encoding="utf-8"))]
    assert offenders == [], f"canned command output in non-test code: {offenders}"
