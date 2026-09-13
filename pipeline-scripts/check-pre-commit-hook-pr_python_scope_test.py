# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""--changed-lines-only in --python mode (#16178).

Lives beside ``check-pre-commit-hook-pr_test.py`` rather than inside it: that file
is at its grandfathered size ceiling (747 lines) and may not grow. Its repo-building
helper is loaded by path and reused here, not copied.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

_SIBLING = Path(__file__).with_name("check-pre-commit-hook-pr_test.py")
_spec = importlib.util.spec_from_file_location("_wrapper_tests", _SIBLING)
assert _spec is not None and _spec.loader is not None
_wrapper_tests = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_wrapper_tests)

WRAPPER = _wrapper_tests.WRAPPER
_make_pr = _wrapper_tests._make_pr

_ECHO_ARGV = "import sys\nprint('ARGV', sys.argv[1:])\n"


def _run(tmp_path: Path, validator: Path, base: str, head: str, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(WRAPPER), *flags, "--python", str(validator), "--ext", "py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestPythonValidatorChangedLinesOnly:
    """The flag used to be accepted in --python mode and silently dropped."""

    def test_the_validator_receives_the_scoping_flags_and_the_base(self, tmp_path: Path) -> None:
        validator = tmp_path / "echo_argv.py"
        validator.write_text(_ECHO_ARGV, encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})

        result = _run(tmp_path, validator, base, head, "--changed-lines-only")

        assert result.returncode == 0, result.stderr
        assert "'--changed-lines-only'" in result.stdout
        assert f"'--base', '{base}'" in result.stdout

    def test_a_validator_that_cannot_scope_fails_instead_of_running_whole_file(self, tmp_path: Path) -> None:
        """An unknown flag must fail the run, not be ignored the way the wrapper used to ignore it."""
        validator = tmp_path / "strict.py"
        validator.write_text(
            "import argparse\n"
            "parser = argparse.ArgumentParser()\n"
            "parser.add_argument('files', nargs='*')\n"
            "parser.parse_args()\n",
            encoding="utf-8",
        )
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})

        assert _run(tmp_path, validator, base, head, "--changed-lines-only").returncode != 0

    def test_without_the_flag_the_validator_is_called_exactly_as_before(self, tmp_path: Path) -> None:
        """The contrast: unscoped --python mode keeps its argv unchanged."""
        validator = tmp_path / "echo_argv.py"
        validator.write_text(_ECHO_ARGV, encoding="utf-8")
        base, head = _make_pr(tmp_path, {"src/foo.py": "x = 1\n"})

        result = _run(tmp_path, validator, base, head)

        assert result.returncode == 0, result.stderr
        assert "--changed-lines-only" not in result.stdout
