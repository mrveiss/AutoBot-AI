# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20935: the remote test node tooling, with a stand-in `ssh` that runs the remote command in a scratch home.

Covers: configuration and fallback, a run end to end, cleanup of the checkout after success, failure, timeout,
SIGTERM and a lost SSH session, the stale sweep, the provisioning script's distro detection and Python floor
check (stubbed commands), and the pre-push hook's fallback to local runs.
"""

from __future__ import annotations

import importlib.util
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

from autobot_shared.paths import scrubbed_git_env

_ROOT = repo_root()
_TOOL = _ROOT / "tools/remote_test_node"
_spec = importlib.util.spec_from_file_location("remote_test_node_run", _TOOL / "run.py")
run = importlib.util.module_from_spec(_spec)
sys.modules["remote_test_node_run"] = run
_spec.loader.exec_module(run)

_FAKE_SSH = """#!/usr/bin/env bash
# Stand-in for ssh: ignores the options and the destination, runs the remote command in $FAKE_HOME.
cd "$FAKE_HOME" || exit 255
args=("$@")
last="${args[${#args[@]}-1]}"
bash -c "$last"
"""


def _git(cwd: Path, *args: str) -> str:
    env = dict(
        scrubbed_git_env(),
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )
    return subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def node(tmp_path: Path):
    """A fake home with a provisioned mirror and venv, plus a source repo with one commit on main."""
    home, src = tmp_path / "home", tmp_path / "src"
    home.mkdir()
    src.mkdir()
    _git(src, "init", "-q", "-b", "main")
    (src / "hello.txt").write_text("hi\n", encoding="utf-8")
    _git(src, "add", "-A")
    _git(src, "commit", "-q", "-m", "first")
    base = home / "base"
    (base / "venv/bin").mkdir(parents=True)
    (base / "venv/bin/python").symlink_to(sys.executable)
    _git(home, "init", "-q", "--bare", str(base / "mirror.git"))
    _git(base, "--git-dir=mirror.git", "remote", "add", "origin", str(src))
    ssh = tmp_path / "fake-ssh"
    ssh.write_text(_FAKE_SSH, encoding="utf-8")
    ssh.chmod(0o755)
    env = dict(
        os.environ,
        FAKE_HOME=str(home),
        AUTOBOT_TEST_NODE_HOST="node.invalid",
        AUTOBOT_TEST_NODE_USER="u",
        AUTOBOT_TEST_NODE_BASE="base",
        AUTOBOT_TEST_NODE_SSH_BIN=str(ssh),
        AUTOBOT_TEST_NODE_SLOTS="2",
    )
    return {"home": home, "src": src, "base": base, "env": env, "sha": _git(src, "rev-parse", "HEAD")}


def _run(node: dict, *cmd: str, timeout: int = 30) -> subprocess.Popen:
    argv = [sys.executable, str(_TOOL / "run.py"), "--sha", node["sha"], "--timeout", str(timeout), "--", *cmd]
    return subprocess.Popen(
        argv, cwd=node["src"], env=node["env"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
    )


def _leftovers(node: dict) -> list[str]:
    runs = node["base"] / "runs"
    refs = _git(node["base"], "--git-dir=mirror.git", "for-each-ref", "refs/runs")
    return [p.name for p in runs.glob("*")] + ([refs] if refs else [])


def _wait_for(pred, secs: float = 20.0) -> bool:
    end = time.time() + secs
    while time.time() < end:
        if pred():
            return True
        time.sleep(0.2)
    return False


def test_unconfigured_node_is_reported_not_silent():
    assert "not set" in run.load_config({})
    assert run.load_config({"AUTOBOT_TEST_NODE_ENABLED": "0"}) == "AUTOBOT_TEST_NODE_ENABLED=0"
    cfg = run.load_config({"AUTOBOT_TEST_NODE_HOST": "h", "AUTOBOT_TEST_NODE_USER": "u"})
    assert cfg.slots == 3 and cfg.timeout == 600 and run.ssh_argv(cfg)[-1] == "u@h"


def test_unconfigured_and_unreachable_exit_75_with_a_reason(capfd):
    assert run.main(["--sha", "HEAD", "--", "true"], env={}) == run.UNAVAILABLE
    assert "UNAVAILABLE: not configured" in capfd.readouterr().err
    env = {"AUTOBOT_TEST_NODE_HOST": "h", "AUTOBOT_TEST_NODE_USER": "u", "AUTOBOT_TEST_NODE_SSH_BIN": "false"}
    assert run.main(["--sha", "HEAD", "--", "true"], env=env) == run.UNAVAILABLE
    assert "ssh to the test node failed" in capfd.readouterr().err


def test_a_run_sees_the_pushed_tree_and_leaves_nothing(node):
    proc = _run(node, "cat", "hello.txt")
    out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0 and "hi" in out
    assert _leftovers(node) == []


def test_a_failing_command_reports_its_status_and_cleans_up(node):
    proc = _run(node, "sh", "-c", "exit 3")
    proc.communicate(timeout=60)
    assert proc.returncode == 3
    assert _leftovers(node) == []


def test_a_timeout_stops_the_command_and_cleans_up(node):
    proc = _run(node, "sleep", "60", timeout=2)
    proc.communicate(timeout=60)
    assert proc.returncode == 124
    assert _leftovers(node) == []


def test_sigterm_mid_run_leaves_no_checkout(node):
    proc = _run(node, "sleep", "60")
    assert _wait_for(lambda: any((node["base"] / "runs").glob("job.*/tree/hello.txt")))
    proc.send_signal(signal.SIGTERM)
    proc.communicate(timeout=60)
    assert proc.returncode == 128 + signal.SIGTERM
    assert _wait_for(lambda: _leftovers(node) == [])


def test_a_lost_ssh_session_removes_the_checkout(node):
    proc = _run(node, "sleep", "60")
    assert _wait_for(lambda: any((node["base"] / "runs").glob("job.*/tree/hello.txt")))
    pid = subprocess.run(["pgrep", "-f", "fake-ssh"], capture_output=True, text=True).stdout.split()[0]
    os.kill(int(pid), signal.SIGKILL)
    assert _wait_for(lambda: _leftovers(node) == [], 30), "the node must clean up when its session vanishes"
    proc.kill()
    proc.communicate()


def test_a_stale_dir_from_a_hard_kill_is_swept_at_the_next_start(node):
    stale = node["base"] / "runs/job.dead"
    stale.mkdir(parents=True)
    old = time.time() - 3 * 3600
    os.utime(stale, (old, old))
    proc = _run(node, "true")
    proc.communicate(timeout=60)
    assert not stale.exists()


def _provision(tmp_path: Path, body: str) -> subprocess.CompletedProcess:
    script = f'PROVISION_SOURCE_ONLY=1 . "{_TOOL}/provision.sh"; set +e\n{body}'
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=tmp_path, check=False)


@pytest.mark.parametrize(
    "os_release,expected",
    [
        ("ID=ubuntu\nID_LIKE=debian", "apt"),
        ('ID=elementary\nID_LIKE="ubuntu debian"', "apt"),
        ("ID=debian", "apt"),
        ("ID=fedora", "dnf"),
        ('ID=rocky\nID_LIKE="rhel centos fedora"', "dnf"),
    ],
)
def test_distro_detection_picks_the_package_manager(tmp_path, os_release, expected):
    (tmp_path / "os-release").write_text(os_release + "\n", encoding="utf-8")
    done = _provision(tmp_path, f'OS_RELEASE_FILE="{tmp_path}/os-release"; detect_pkg_manager')
    assert done.stdout.strip() == expected


def test_an_unknown_distro_fails_loudly(tmp_path):
    (tmp_path / "os-release").write_text("ID=plan9\n", encoding="utf-8")
    done = _provision(tmp_path, f'( OS_RELEASE_FILE="{tmp_path}/os-release"; detect_pkg_manager ); echo "rc=$?"')
    assert "unsupported distribution 'plan9'" in done.stderr and "rc=1" in done.stdout


def _stub_python(tmp_path: Path, version: str) -> Path:
    """An interpreter that reports `version` to the code it is given with -c."""
    py = tmp_path / "python-stub"
    py.write_text(
        "#!/usr/bin/env bash\n"
        f"exec {sys.executable} -c \"import sys; sys.version_info = tuple(map(int, '{version}'.split('.'))) + "
        "(0, 'final', 0); "
        'code = sys.argv.pop(1); exec(code)" "$2" "${@:3}"\n',
        encoding="utf-8",
    )
    py.chmod(0o755)
    return py


@pytest.mark.parametrize(
    "have,floor,ok", [("3.14", "3.14", True), ("3.15", "3.14", True), ("3.12", "3.14", False), ("3.9", "3.14", False)]
)
def test_the_python_floor_check(tmp_path, have, floor, ok):
    py = _stub_python(tmp_path, have)
    done = _provision(tmp_path, f'python_meets_floor "{py}" {floor}; echo "rc=$?"')
    assert (f"rc={0 if ok else 1}") in done.stdout


def test_below_the_floor_fails_with_a_clear_message(tmp_path):
    py = _stub_python(tmp_path, "3.12")
    done = _provision(tmp_path, f'( check_floor_or_die "{py}" 3.14 ); echo "rc=$?"')
    assert "is below the repository floor 3.14" in done.stderr and "rc=1" in done.stdout


def test_run_reads_the_floor_from_the_repo(tmp_path):
    (tmp_path / ".python-version").write_text("3.14.2\n", encoding="utf-8")
    assert run.python_floor(tmp_path) == "3.14"
    assert (_ROOT / ".python-version").is_file()


def test_ensure_python_falls_back_from_the_base_package_to_uv(tmp_path):
    body = (
        "python_meets_floor() { return 1; }; pkg_available() { return 1; }\n"
        'install_python_with_uv() { echo "uv-route $1"; }\n'
        "ensure_python 3.14"
    )
    assert "uv-route 3.14" in _provision(tmp_path, body).stdout


def test_ensure_python_prefers_the_base_package_when_it_has_one(tmp_path):
    body = (
        'calls=0; python_meets_floor() { calls=$((calls+1)); [ "$calls" -gt 2 ]; }; pkg_available() { return 0; }\n'
        'pkg_install() { echo "pkg $*" >&2; }; install_python_with_uv() { echo uv-route; }\n'
        "ensure_python 3.14"
    )
    done = _provision(tmp_path, body)
    assert "pkg python3.14 python3.14-venv" in done.stderr and "uv-route" not in done.stdout


_HOOK = (_ROOT / "tools/git-hooks/pre-push").read_text(encoding="utf-8")


def _hook_fn() -> str:
    return re.search(r"^remote_guard_pytest\(\) \{\n(?:.*\n)*?\}$", _HOOK, re.MULTILINE).group(0)


def _call_hook_fn(tmp_path: Path, run_rc: int) -> subprocess.CompletedProcess:
    stub = tmp_path / "tools/remote_test_node"
    stub.mkdir(parents=True)
    (stub / "run.py").write_text(
        f"import sys\nprint('[remote-test-node] UNAVAILABLE: stub' if {run_rc} == 75 else 'ran')\nsys.exit({run_rc})\n",
        encoding="utf-8",
    )
    script = (
        f'REPO_ROOT="{tmp_path}"; PYTEST_PYTHON="{sys.executable}"; local_sha=abc; MAX_BUDGET=5\n'
        'warn() { echo "WARN $*" >&2; }\n'
        f"{_hook_fn()}\n"
        'rc=0; guard_output=""; remote_guard_pytest "a.py" ""; handled=$?\n'
        'echo "handled=$handled rc=$rc"'
    )
    return subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)


def test_the_hook_falls_back_to_local_and_says_so(tmp_path):
    done = _call_hook_fn(tmp_path, 75)
    assert "handled=1 rc=0" in done.stdout
    assert "UNAVAILABLE: stub" in done.stderr and "running the fast guards locally" in done.stderr


def test_a_remote_test_failure_is_a_failure_not_a_fallback(tmp_path):
    assert "handled=0 rc=1" in _call_hook_fn(tmp_path, 1).stdout


def test_no_address_or_credential_is_written_into_the_tooling():
    for path in (p for p in _TOOL.iterdir() if p.is_file()):
        text = path.read_text(encoding="utf-8")
        assert not re.search(r"\b\d{1,3}(\.\d{1,3}){3}\b", text), path.name
        assert "BEGIN" not in text or "PRIVATE KEY" not in text
