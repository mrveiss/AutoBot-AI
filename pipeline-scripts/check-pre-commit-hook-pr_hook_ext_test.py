# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""--ext after a hook name widens the wrapper's pathspec (#18553).

The Redis matcher reads ``.sh`` as well as ``.py``, but the wrapper's default pathspec has no
``.sh``, so a shell-only PR never reached it. Lives beside ``check-pre-commit-hook-pr_test.py``
rather than inside it: that file is at its grandfathered size ceiling and may not grow. Its
repo-building helper is loaded by path and reused here, not copied.
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

_SHELL_REDIS = "#!/bin/bash\npython3 -c 'import redis; redis.Redis()'\n"


def _run(tmp_path: Path, base: str, head: str, *ext: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(WRAPPER), "pre-commit-no-direct-redis", *ext],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        env={"BASE_SHA": base, "HEAD_SHA": head, "PATH": "/usr/bin:/bin"},
    )


@pytest.mark.skipif(not WRAPPER.exists(), reason="wrapper script not found")
class TestHookModeExt:
    """The step in code-quality.yml passes ``--ext py,sh`` to the Redis hook."""

    def test_the_default_pathspec_never_reaches_a_shell_only_change(self, tmp_path: Path) -> None:
        """The control: without --ext the .sh change is skipped as 'no changed source files'."""
        base, head = _make_pr(tmp_path, {"scripts/r.sh": _SHELL_REDIS})
        assert "No changed source files" in _run(tmp_path, base, head).stdout

    def test_ext_py_sh_hands_a_shell_only_change_to_the_redis_matcher(self, tmp_path: Path) -> None:
        base, head = _make_pr(tmp_path, {"scripts/r.sh": _SHELL_REDIS})
        result = _run(tmp_path, base, head, "--ext", "py,sh")
        assert "No changed source files" not in result.stdout, result.stdout
        assert result.returncode == 1, result.stdout + result.stderr

    @pytest.mark.parametrize("bad_ext", [".sh", " sh", "sh!"])
    def test_a_malformed_ext_after_a_hook_name_exits_2(self, tmp_path: Path, bad_ext: str) -> None:
        base, head = _make_pr(tmp_path, {"scripts/r.sh": _SHELL_REDIS})
        result = _run(tmp_path, base, head, "--ext", bad_ext)
        assert result.returncode == 2, result.stdout
        assert "No changed source files" not in result.stdout
