"""End-to-end CLI tests for the Infra runner."""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNER = REPO_ROOT / "tools" / "lint" / "canonical_check_infra.py"
FIXTURES = REPO_ROOT / "tests" / "lint" / "canonical" / "fixtures" / "sh_echo_debug_smoke"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def test_runner_clean_file_exits_zero():
    result = _run("--files", str(FIXTURES / "negative.sh"))
    assert result.returncode == 0


def test_runner_violation_produces_warning_but_exits_zero():
    # sh-echo-debug-smoke is severity=warn, so exit 0
    result = _run("--files", str(FIXTURES / "positive.sh"))
    assert result.returncode == 0
    assert "sh-echo-debug-smoke" in result.stderr


def test_runner_format_json():
    result = _run("--files", str(FIXTURES / "positive.sh"), "--format", "json")
    assert result.stdout.startswith("[")
    assert "sh-echo-debug-smoke" in result.stdout
