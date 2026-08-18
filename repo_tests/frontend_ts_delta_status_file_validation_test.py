# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""check-ts-delta.sh must not read a malformed TSC_STATUS_FILE as exit 0 (#14503).

`scripts/check-ts-delta.sh` reuses a caller's prior vue-tsc run via
`TSC_OUTPUT_FILE`/`TSC_STATUS_FILE` (#14481). Bash arithmetic reads an empty
`TSC_STATUS_FILE` as `0` — indistinguishable from a genuinely clean compile.
Fed a crash-shaped output (zero `error TS` lines) alongside an empty status
file, the script printed ``PASS: 0 errors`` and exited 0, bypassing its own
documented discriminator: "a count alone is not a measurement... the exit
status is what separates [a compiler that never ran] from a genuine clean
compile." An empty status file silently supplied a fake clean one.

The first fix (`^[0-9]+$` plus `(( TSC_STATUS > 255 ))`) covered exactly the
shapes the issue named — empty, whitespace, multi-line, non-numeric — but not
the input *space*: bash's `(( ))` is fixed-width (64-bit) and NOT
decimal-only, so a value the pattern accepts can still defeat the range check
below it. `2**64` matches the pattern, then WRAPS to `0` in fixed-width
arithmetic (same bug, one layer down); a leading zero (`"008"`) matches the
pattern too, but bash parses it as octal, `8`/`9` are not valid octal digits,
`(( ))` throws, and because that arithmetic sits in a *tested* `if (( ... ))`
context the throw is swallowed as false rather than propagating — the guard's
own error path silently reads a malformed value as clean, the exact defect
being fixed, one layer up. The current fix rejects both by shape (length +
no leading zero) before arithmetic ever sees them, and forces base-10 parsing
(`10#`) on whatever does reach `(( ))`.

`autobot-frontend/` is in no `testpaths` entry (see pytest.ini), so this test
lives in `repo_tests/` and drives the real script via `subprocess`, in an
isolated sandbox tree (its own `docs/developer/audits/typescript-baseline.md`
and no `node_modules/`) so the always-reachable reuse path never depends on
`vue-tsc` being installed and no test here runs `npm`/`vue-tsc` for real.

Discrimination: every ``*_is_rejected``/``*_rejected`` test below FAILS
against the pre-#14503 script (empty/whitespace/multiline/overflow/octal all
printed ``PASS: 0 errors`` / exit 0; non-numeric leaked bash's raw
``unbound variable`` message) and PASSES against the fixed one — the overflow
and octal cases specifically discriminate the *first* #14503 patch
(`^[0-9]+$` + `(( TSC_STATUS > 255 ))`, no length bound, no `10#`) from the
current one, since the first patch still passed both through. The fail-safe
controls at the bottom prove the fix does not touch: a genuinely clean status
of 0, a genuinely detected crash status, the missing-file fallback to
recompile, and the standalone no-env local path.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import project_root

SCRIPT_RELATIVE_PATH = "autobot-frontend/scripts/check-ts-delta.sh"

# Crash-shaped compiler output: zero "error TS" lines, as if vue-tsc died
# before emitting any diagnostics — the exact shape #14503 was reproduced with.
_CRASH_OUTPUT = "internal compiler crash, no diagnostics emitted\n"


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """An isolated repo-shaped tree: real script, no real node_modules.

    Mirrors just enough of the repo layout for the script's own path
    resolution (SCRIPT_DIR -> REPO_ROOT -> BASELINE_FILE) to work, without
    depending on this checkout's actual baseline doc or any installed
    vue-tsc binary — so the missing-status-file fallback below deterministically
    hits the "vue-tsc not found" branch instead of trying to compile anything.
    """
    baseline_dir = tmp_path / "docs" / "developer" / "audits"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "typescript-baseline.md").write_text(
        "**Total:** 0\n", encoding="utf-8"
    )

    script_dir = tmp_path / "autobot-frontend" / "scripts"
    script_dir.mkdir(parents=True)
    real_script = project_root() / SCRIPT_RELATIVE_PATH
    assert real_script.is_file(), f"missing {SCRIPT_RELATIVE_PATH}"
    shutil.copy2(real_script, script_dir / "check-ts-delta.sh")

    return tmp_path


def _run(
    sandbox: Path,
    status_content: str | None,
    output_content: str = _CRASH_OUTPUT,
) -> subprocess.CompletedProcess:
    """Invoke the sandboxed script with a given TSC_STATUS_FILE shape.

    ``status_content=None`` omits the status file entirely (the missing-file
    fail-safe case); any string writes it verbatim (no trailing newline added
    beyond what the caller supplies, so whitespace/multi-line cases are exact).
    """
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")

    work = sandbox / "work"
    work.mkdir(exist_ok=True)
    output_file = work / "vue-tsc-output.txt"
    output_file.write_text(output_content, encoding="utf-8")

    env = {"PATH": "/usr/bin:/bin:/usr/local/bin"}
    env["TSC_OUTPUT_FILE"] = str(output_file)

    if status_content is not None:
        status_file = work / "vue-tsc-status.txt"
        status_file.write_text(status_content, encoding="utf-8")
        env["TSC_STATUS_FILE"] = str(status_file)
    else:
        status_file = work / "vue-tsc-status.txt"  # deliberately never created

    return subprocess.run(
        [bash, str(sandbox / SCRIPT_RELATIVE_PATH)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(sandbox),
        env=env,
    )


# --- Malformed status file: must be rejected, never read as a clean 0 ---


def test_empty_status_file_is_rejected_not_treated_as_clean(sandbox: Path) -> None:
    result = _run(sandbox, status_content="")
    assert result.returncode != 0, (
        "an empty TSC_STATUS_FILE must not be treated as exit status 0 — "
        f"got PASS. stdout:\n{result.stdout}"
    )
    assert "PASS" not in result.stdout


def test_whitespace_only_status_file_is_rejected(sandbox: Path) -> None:
    result = _run(sandbox, status_content="   \n")
    assert result.returncode != 0, f"stdout:\n{result.stdout}"
    assert "PASS" not in result.stdout


def test_multiline_status_file_is_rejected(sandbox: Path) -> None:
    result = _run(sandbox, status_content="0\n1\n")
    assert result.returncode != 0, f"stdout:\n{result.stdout}"
    assert "PASS" not in result.stdout


def test_non_numeric_status_file_reports_through_the_scripts_own_error(
    sandbox: Path,
) -> None:
    result = _run(sandbox, status_content="banana")
    assert result.returncode != 0, f"stdout:\n{result.stdout}"
    assert "PASS" not in result.stdout
    # The old failure mode: bash's own `set -u` message on the raw arithmetic
    # read, not the script's crafted diagnostic.
    assert "unbound variable" not in result.stderr, (
        "non-numeric TSC_STATUS_FILE content must be refused through the "
        f"script's own error handling, not bash's raw message. stderr:\n{result.stderr}"
    )
    assert "valid exit status" in result.stderr


def test_overflow_beyond_64bit_wraps_but_is_still_rejected(sandbox: Path) -> None:
    """2**64 matches a naive `^[0-9]+$` pattern, then WRAPS to 0 under bash's
    fixed-width `(( ))` arithmetic — so a length/range-blind check would read
    it right back as `(( 0 > 255 ))`: false, accepted, PASS. Pre-fix (the
    first #14503 patch, `^[0-9]+$` + `(( TSC_STATUS > 255 ))` with no `10#`
    and no length bound) this value sailed straight through both this check
    and the pre-existing crash discriminator at line ~115, printing
    `PASS: 0 errors` / exit 0 — reproduced against that shape before this test
    was written. The shape check must reject it purely on digit count, before
    arithmetic ever sees it.
    """
    result = _run(sandbox, status_content="18446744073709551616")  # 2**64
    assert result.returncode != 0, f"stdout:\n{result.stdout}"
    assert "PASS" not in result.stdout
    assert "valid exit status" in result.stderr


def test_leading_zero_octal_invalid_value_is_rejected(sandbox: Path) -> None:
    """A leading zero makes bash's `(( ))` parse the numeral as OCTAL, and `8`/
    `9` are not valid octal digits, so `(( ))` throws. Because that arithmetic
    sits in a *tested* context (an `if (( ... ))` condition), `set -e` does not
    propagate the throw — it is silently read as boolean false. Pre-fix (the
    first #14503 patch) "008" passed `^[0-9]+$`, then threw on both `(( TSC_STATUS
    > 255 ))` here and the pre-existing crash check, each throw swallowed as
    "false" — so the guard neither rejected nor errored, and the script fell
    through to `PASS: 0 errors` / exit 0 exactly like the empty-file case this
    whole fix exists to close. This is the guard's own error path being
    swallowed by the construct it is written inside — reject the shape before
    arithmetic, and force base 10 (`10#`) on whatever does reach it.
    """
    result = _run(sandbox, status_content="008")
    assert result.returncode != 0, f"stdout:\n{result.stdout}"
    assert "PASS" not in result.stdout
    assert "valid exit status" in result.stderr


# --- Fail-safe controls: the fix must not touch these ---


def test_valid_zero_status_file_still_passes(sandbox: Path) -> None:
    """A genuinely clean compile (status 0, no diagnostics) must still PASS."""
    result = _run(sandbox, status_content="0")
    assert result.returncode == 0, f"stderr:\n{result.stderr}"
    assert "PASS" in result.stdout


def test_valid_nonzero_status_with_no_diagnostics_is_still_a_detected_crash(
    sandbox: Path,
) -> None:
    """Unrelated to #14503: status 2 with zero diagnostics is the pre-existing
    crash discriminator (comment above TSC_STATUS in the script) — must still fire.
    """
    result = _run(sandbox, status_content="2")
    assert result.returncode != 0
    assert "without completing a check" in result.stderr


def test_missing_status_file_falls_back_to_recompile(sandbox: Path) -> None:
    """A MISSING file (not an empty one) must still fail open to a fresh compile.

    In this sandbox there is no installed vue-tsc, so the fallback deterministically
    reports "vue-tsc not found" rather than reusing anything — proving the reuse
    branch was never taken.
    """
    result = _run(sandbox, status_content=None)
    assert result.returncode != 0
    assert "Reusing vue-tsc output" not in result.stdout
    assert "vue-tsc not found" in result.stderr


def test_standalone_no_env_still_falls_back_to_recompile(sandbox: Path) -> None:
    """`bash scripts/check-ts-delta.sh` with neither env var set — the documented
    standalone local-development path — must be unchanged by this fix.
    """
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")

    result = subprocess.run(
        [bash, str(sandbox / SCRIPT_RELATIVE_PATH)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(sandbox),
        env={"PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    assert result.returncode != 0
    assert "Reusing vue-tsc output" not in result.stdout
    assert "vue-tsc not found" in result.stderr
