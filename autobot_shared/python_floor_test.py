# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the interpreter floor refusal (#20903)."""

import shutil
import subprocess  # nosec B404  # fixed argv, no shell

import pytest

from autobot_shared.python_floor import (
    _REPO_ROOT,
    UnsupportedPythonError,
    minimum_python_version,
    require_supported_python,
)


def test_floor_is_read_from_python_version():
    declared = (_REPO_ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert "%d.%d" % minimum_python_version() == declared


def test_an_old_interpreter_is_refused_with_an_actionable_message():
    floor = "%d.%d" % minimum_python_version()
    with pytest.raises(UnsupportedPythonError) as raised:
        require_supported_python((3, 10, 12), "/usr/bin/python3")
    message = str(raised.value)
    for needle in (f"Python {floor}", "3.10.12", "/usr/bin/python3", ".python-version", "venv/bin/python", "#20903"):
        assert needle in message


@pytest.mark.parametrize("version", [(3, 13, 9), (3, 0, 0), (2, 7, 18)])
def test_versions_below_the_floor_raise(version):
    with pytest.raises(UnsupportedPythonError):
        require_supported_python(version, "x")


@pytest.mark.parametrize("version", [(3, 14, 0), (3, 15, 0), (4, 0, 0)])
def test_versions_at_or_above_the_floor_pass(version):
    require_supported_python(version, "x")


def test_the_running_interpreter_passes():
    require_supported_python()


@pytest.mark.skipif(shutil.which("python3.10") is None, reason="python3.10 not installed")
def test_importing_autobot_shared_on_python_310_is_refused_cleanly():
    code = f"import sys; sys.path.insert(0, {str(_REPO_ROOT)!r}); import autobot_shared"
    result = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["python3.10", "-I", "-c", code], capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode != 0
    assert "requires Python %d.%d" % minimum_python_version() in result.stderr
    assert "multiple repeat" not in result.stderr
