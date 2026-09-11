# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The CI system-package step recovers from its own timeout (#15515).

``setup-python-suite`` wrapped each apt command in ``timeout 300`` and retried
it three times. When a slow mirror pushed an install past that bound while
dpkg was unpacking, the kill left dpkg interrupted. Both retries then failed at
once with "dpkg was interrupted", so the three attempts were really one.

These tests run the step's own shell script, read from the action, against
stand-ins for sudo, timeout, tee, sleep, dpkg and apt-get. No package is
installed and nothing needs root. The apt-get stand-in reproduces the failure:
an unpack it is told to kill exits 124 and leaves dpkg interrupted, and every
install after that exits 100 until ``dpkg --configure -a`` runs.
"""

import shutil
import subprocess  # nosec B404  # runs bash on the action's own script
from pathlib import Path
from typing import List, Tuple

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ACTION = _REPO_ROOT / ".github/actions/setup-python-suite/action.yml"
_STEP = "Install CI system packages (#14550, #13896)"
_BASH = shutil.which("bash")

#: The apt-get stand-in. ``KILL`` lists the unpack calls (1-based) to kill, or
#: ``all``. ``UPDATE_EXIT`` is what ``update`` returns; ``--download-only`` fetches succeed.
_APT_GET = r"""
printf 'apt-get %s\n' "$*" >> "$STATE/calls"
case " $* " in
  *" update "*) exit "${UPDATE_EXIT:-0}" ;;
  *" --download-only "*) exit 0 ;;
esac
if [ "$(< "$STATE/dpkg")" = interrupted ]; then
  echo "E: dpkg was interrupted, you must manually run 'sudo dpkg --configure -a' to correct the problem." >&2
  exit 100
fi
n=$(( $(< "$STATE/unpacks") + 1 ))
printf '%s' "$n" > "$STATE/unpacks"
case ",$KILL," in
  *",$n,"*|*",all,"*) printf interrupted > "$STATE/dpkg"; exit 124 ;;
esac
exit 0
"""

_STAND_INS = {
    "sudo": 'exec "$@"',
    "timeout": 'printf "timeout %s\\n" "$1" >> "$STATE/calls"; shift; exec "$@"',
    "tee": 'printf "%s" "$(< /dev/stdin)" > "$STATE/apt.conf"',
    "sleep": 'printf "sleep %s\\n" "$*" >> "$STATE/calls"',
    "dpkg": (
        'printf "dpkg %s\\n" "$*" >> "$STATE/calls"; '
        '[ "$*" = "--configure -a" ] && printf ok > "$STATE/dpkg"; exit 0'
    ),
    "apt-get": _APT_GET,
}


def _step_script() -> str:
    steps = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))["runs"]["steps"]
    scripts = [step["run"] for step in steps if step.get("name") == _STEP]
    assert len(scripts) == 1, f"expected one {_STEP!r} step, found {len(scripts)}"
    return scripts[0]


def _run(tmp_path: Path, kill: str, update_exit: str = "0") -> Tuple[subprocess.CompletedProcess, List[str], Path]:
    """Run the step with only the stand-ins on PATH; return the result, the calls made, and the state dir."""
    bin_dir, state = tmp_path / "bin", tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    for name, body in _STAND_INS.items():
        stand_in = bin_dir / name
        stand_in.write_text(f"#!{_BASH}\n{body}\n", encoding="utf-8")
        stand_in.chmod(0o755)
    for name, value in (("dpkg", "ok"), ("unpacks", "0"), ("calls", "")):
        (state / name).write_text(value, encoding="utf-8")
    result = subprocess.run(  # nosec B603  # fixed argv: bash and the action's own step script
        [_BASH, "-c", _step_script()],
        env={"PATH": str(bin_dir), "STATE": str(state), "KILL": kill, "UPDATE_EXIT": update_exit},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return result, (state / "calls").read_text(encoding="utf-8").splitlines(), state


def _unpacks(calls: List[str]) -> List[int]:
    """Indexes of the install calls that unpack, as opposed to only downloading."""
    return [i for i, call in enumerate(calls) if call.startswith("apt-get install") and "--download-only" not in call]


@pytest.mark.parametrize("killed", [1, 2], ids=["ffmpeg", "tesseract-ocr"])
def test_an_unpack_killed_by_the_timeout_is_repaired_before_it_is_retried(tmp_path: Path, killed: int) -> None:
    """The #15515 failure: without the repair, every attempt after the kill fails at once."""
    result, calls, _ = _run(tmp_path, kill=str(killed))

    assert result.returncode == 0, result.stderr
    unpacks = _unpacks(calls)
    first, retry = unpacks[killed - 1], unpacks[killed]
    assert calls[first] == calls[retry], "the retry must repeat the killed command"
    assert first < calls.index("dpkg --configure -a") < retry, calls
    assert "attempt 1/3 failed (exit 124, timed out)" in result.stderr


def test_an_exhausted_retry_ends_in_a_titled_annotation_without_a_trailing_sleep(tmp_path: Path) -> None:
    result, calls, _ = _run(tmp_path, kill="all")

    assert result.returncode != 0
    annotation = "::error title=CI toolchain provisioning failed (no tests ran)::install ffmpeg failed 3 times"
    assert f"{annotation}, last exit 124, timed out" in result.stderr
    assert [call for call in calls if call.startswith("sleep")] == ["sleep 15", "sleep 30"], calls


def test_both_packages_are_downloaded_before_dpkg_unpacks_anything(tmp_path: Path) -> None:
    """A kill during a download is harmless; fetching first keeps most of the wall clock off dpkg."""
    result, calls, state = _run(tmp_path, kill="")

    assert result.returncode == 0, result.stderr
    apt = [call for call in calls if call.startswith("apt-get")]
    downloads = [i for i, call in enumerate(apt) if "--download-only" in call]
    assert apt[0].startswith("apt-get update") and max(downloads) < min(_unpacks(apt)), apt
    assert {apt[i].split()[-1] for i in downloads} == {"ffmpeg", "tesseract-ocr"}

    conf = (state / "apt.conf").read_text(encoding="utf-8")
    assert 'Acquire::Retries "3";' in conf and 'Acquire::http::Timeout "30";' in conf
    assert "Error-Mode" not in conf, "a failing third-party index on the runner image must not fail a shard"


def test_a_failing_update_warns_and_the_installs_still_decide(tmp_path: Path) -> None:
    """The 2026-09-09 shape: a third-party index fails ``update`` on every try, and the shard must not die there."""
    result, calls, _ = _run(tmp_path, kill="", update_exit="100")

    assert result.returncode == 0, result.stderr
    assert "::warning title=apt update failed (continuing)::update failed 3 times, last exit 100" in result.stderr
    assert "::error" not in result.stderr
    assert sum(call.startswith("apt-get install") for call in calls) == 4, calls
