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

from autobot_shared.isolated_git import git, make_repo

_ROOT = repo_root()
_TOOL = _ROOT / "tools/remote_test_node"
_spec = importlib.util.spec_from_file_location("remote_test_node_run", _TOOL / "run.py")
run = importlib.util.module_from_spec(_spec)
sys.modules["remote_test_node_run"] = run
_spec.loader.exec_module(run)
sys.modules.pop("remote_test_node_run", None)  # needed only while the dataclass is built

_FAKE_SSH = """#!/usr/bin/env bash
# Stand-in for ssh: ignores the options and the destination, runs the remote command in $FAKE_HOME.
cd "$FAKE_HOME" || exit 255
args=("$@")
last="${args[${#args[@]}-1]}"
bash -c "$last"
"""


def _git(cwd: Path, *args: str) -> str:
    return git(cwd, *args).stdout.strip()


@pytest.fixture()
def node(tmp_path: Path):
    """A fake home with a provisioned mirror and venv, plus a source repo with one commit on main."""
    home, src = tmp_path / "home", tmp_path / "src"
    home.mkdir()
    src.mkdir()
    make_repo(src, default_branch="main")
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
    dirs = sorted(os.listdir(runs)) if runs.is_dir() else []
    return dirs + ([refs] if refs else [])


def _refs(node: dict) -> set[str]:
    out = _git(node["base"], "--git-dir=mirror.git", "for-each-ref", "--format=%(refname)", "refs/runs")
    return set(out.split())


def _checked_out(node: dict) -> bool:
    runs = node["base"] / "runs"
    return any((runs / name / "tree/hello.txt").is_file() for name in (os.listdir(runs) if runs.is_dir() else []))


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
    assert _wait_for(lambda: _checked_out(node))
    proc.send_signal(signal.SIGTERM)
    proc.communicate(timeout=60)
    assert proc.returncode == 128 + signal.SIGTERM
    assert _wait_for(lambda: _leftovers(node) == [])


def test_a_lost_ssh_session_removes_the_checkout(node):
    proc = _run(node, "sleep", "60")
    assert _wait_for(lambda: _checked_out(node))
    # Only this runner's own session: another run's stand-in on the same machine must never be hit.
    found = subprocess.run(
        ["pgrep", "-P", str(proc.pid), "-f", "fake-ssh"], capture_output=True, text=True, check=False
    ).stdout.split()
    assert found, "no stand-in ssh session found under the runner"
    os.kill(int(found[0]), signal.SIGKILL)
    assert _wait_for(lambda: _leftovers(node) == [], 30), "the node must clean up when its session vanishes"
    proc.kill()
    proc.communicate()


def test_a_stale_dir_from_a_hard_kill_is_swept_at_the_next_start(node):
    stale = node["base"] / "runs/job.dead"
    stale.mkdir(parents=True)
    old = time.time() - 3 * 3600
    os.utime(stale, (old, old))
    _git(node["base"], "--git-dir=mirror.git", "fetch", "-q", str(node["src"]), "HEAD:refs/runs/dead")
    proc = _run(node, "true")
    proc.communicate(timeout=60)
    assert not stale.exists() and _leftovers(node) == []


def test_a_live_run_is_not_swept_by_a_run_with_a_shorter_ttl(node):
    live = _run(node, "sleep", "60", timeout=3600)
    assert _wait_for(lambda: _checked_out(node))
    dirs = list((node["base"] / "runs").iterdir())
    old = time.time() - 5 * 3600
    for d in dirs:
        os.utime(d, (old, old))
    short = _run(node, "true", timeout=60)  # ttl 31 min: the live run's dir is older than that
    short.communicate(timeout=60)
    assert all(d.exists() for d in dirs), "a run holding its liveness lock must survive another run's sweep"
    live.send_signal(signal.SIGTERM)
    live.communicate(timeout=60)
    assert _wait_for(lambda: _leftovers(node) == [])


def test_a_queued_job_whose_caller_left_never_takes_a_slot(node):
    holders = [_run(node, "sleep", "60") for _ in range(2)]  # SLOTS=2: both slots busy
    runs = node["base"] / "runs"
    assert _wait_for(lambda: len(os.listdir(runs)) >= 2 if runs.is_dir() else False)
    held_dirs, held_refs = sorted(os.listdir(runs)), _refs(node)
    queued = _run(node, "true")
    assert _wait_for(lambda: len(_refs(node) - held_refs) == 1), "the queued job's ref never appeared"
    queued_ref = next(iter(_refs(node) - held_refs))
    found = subprocess.run(
        ["pgrep", "-P", str(queued.pid), "-f", "fake-ssh"], capture_output=True, text=True, check=False
    ).stdout.split()
    assert found, "the queued job's stand-in ssh session was not found"
    os.kill(int(found[0]), signal.SIGKILL)
    assert _wait_for(lambda: queued_ref not in _refs(node), 30), "the queued job's ref survived its caller"
    assert sorted(os.listdir(runs)) == held_dirs, "a dir appeared for the queued job: it took a slot"
    for proc in (queued, *holders):
        proc.kill()
        proc.communicate()


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


_TOOL_FILES = ("run.py", "remote_job.sh", "provision.sh")


def _hardcoded_secrets(text: str) -> list[str]:
    """What must not be written into the tooling: an IPv4 address or a private key block."""
    found = re.findall(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", text)
    return found + (["private key"] if "BEGIN" in text and "PRIVATE KEY" in text else [])


@pytest.mark.parametrize("text", ["ssh 10.0.0.5", "-----BEGIN " + "OPENSSH PRIVATE" + " KEY-----"])
def test_the_detector_trips_on_an_address_and_a_key(text):
    assert _hardcoded_secrets(text)


@pytest.mark.parametrize("text", ["python 3.14.2", "pip==25.3", "BEGIN the run"])
def test_the_detector_passes_version_strings_and_plain_words(text):
    assert _hardcoded_secrets(text) == []


def test_no_address_or_credential_is_written_into_the_tooling():
    for path in (_TOOL / name for name in _TOOL_FILES):
        assert _hardcoded_secrets(path.read_text(encoding="utf-8")) == [], path.name


def test_shipping_a_commit_does_not_run_the_repos_own_pre_push_hook(node):
    """The hook calls this tool; a hook-running transport would recurse into itself."""
    hook = node["src"] / ".git/hooks/pre-push"
    hook.write_text("#!/bin/sh\necho hook-ran >&2\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    proc = _run(node, "true")
    out, _ = proc.communicate(timeout=60)
    assert proc.returncode == 0 and "hook-ran" not in out


_BASE_ENV = {"AUTOBOT_TEST_NODE_HOST": "h", "AUTOBOT_TEST_NODE_USER": "u"}


def _expire(*_args, **_kwargs):
    raise subprocess.TimeoutExpired("ssh", 1)


def test_a_missing_ssh_executable_is_unavailable_not_a_failure(capfd):
    env = {**_BASE_ENV, "AUTOBOT_TEST_NODE_SSH_BIN": "/nonexistent/ssh"}
    assert run.probe(run.load_config(env)) == "ssh to the test node could not start (FileNotFoundError)"
    assert run.main(["--sha", "HEAD", "--", "true"], env=env) == run.UNAVAILABLE
    assert "UNAVAILABLE" in capfd.readouterr().err


def test_a_hung_probe_is_unavailable_not_a_failure(monkeypatch, capfd):
    monkeypatch.setattr(run.subprocess, "run", _expire)
    assert run.probe(run.load_config(_BASE_ENV)) == "ssh to the test node timed out"
    assert run.main(["--sha", "HEAD", "--", "true"], env=_BASE_ENV) == run.UNAVAILABLE
    assert "UNAVAILABLE" in capfd.readouterr().err


def test_a_hung_ship_is_unavailable_not_124(monkeypatch):
    monkeypatch.setattr(run.subprocess, "run", _expire)
    cfg = run.load_config(_BASE_ENV)
    assert "timed out" in run.ship_commit(cfg, "abc", "job")
    monkeypatch.setattr(run, "probe", lambda _cfg: None)
    assert run.main(["--sha", "HEAD", "--", "true"], env=_BASE_ENV) == run.UNAVAILABLE


def test_a_hung_cleanup_cannot_mask_the_result(monkeypatch):
    monkeypatch.setattr(run.subprocess, "run", _expire)
    run.remote_cleanup(run.load_config(_BASE_ENV), "job")  # does not raise
    monkeypatch.setattr(run, "ship_commit", lambda *_a: None)
    monkeypatch.setattr(run, "_script_command", lambda *_a: "true")
    monkeypatch.setattr(
        run.subprocess, "Popen", lambda *_a, **_k: type("P", (), {"wait": lambda s, timeout: 7, "poll": lambda s: 7})()
    )
    assert run.run_remote(run.load_config(_BASE_ENV), "abc", ["true"], 30) == 7


@pytest.mark.parametrize(
    "name,value,attr,expected",
    [
        ("AUTOBOT_TEST_NODE_SLOTS", "0", "slots", 3),
        ("AUTOBOT_TEST_NODE_SLOTS", "99", "slots", 3),
        ("AUTOBOT_TEST_NODE_SLOTS", "abc", "slots", 3),
        ("AUTOBOT_TEST_NODE_SLOTS", "5", "slots", 5),
        ("AUTOBOT_TEST_NODE_TIMEOUT", "1", "timeout", 600),
        ("AUTOBOT_TEST_NODE_CONNECT_TIMEOUT", "0", "connect_timeout", 10),
    ],
)
def test_env_ints_are_validated_against_the_registered_ranges(name, value, attr, expected):
    assert getattr(run.load_config({**_BASE_ENV, name: value}), attr) == expected


def test_host_key_trust_is_first_use_unless_pinned():
    assert "StrictHostKeyChecking=accept-new" in run.ssh_argv(run.load_config(_BASE_ENV))
    pinned = run.ssh_argv(run.load_config({**_BASE_ENV, "AUTOBOT_TEST_NODE_KNOWN_HOSTS": "/pins/kh"}))
    assert "StrictHostKeyChecking=yes" in pinned and "UserKnownHostsFile=/pins/kh" in pinned
    assert "GlobalKnownHostsFile=/dev/null" in pinned  # the pinned file is the only trust source
    assert "StrictHostKeyChecking=accept-new" not in pinned
    assert pinned[pinned.index("-F") + 1] == "/dev/null"  # a user ssh config cannot widen trust
    assert "-F" not in run.ssh_argv(run.load_config(_BASE_ENV)) and "-p" in pinned  # port stays explicit


def test_the_stale_sweep_ttl_follows_the_effective_timeout(monkeypatch):
    sent = []
    monkeypatch.setattr(run, "ship_commit", lambda *_a: None)
    monkeypatch.setattr(run, "remote_cleanup", lambda *_a: None)
    monkeypatch.setattr(run, "_script_command", lambda *a: sent.append(a) or "true")
    monkeypatch.setattr(
        run.subprocess, "Popen", lambda *_a, **_k: type("P", (), {"wait": lambda s, timeout: 0, "poll": lambda s: 0})()
    )
    run.run_remote(run.load_config(_BASE_ENV), "abc", ["true"], 3600)
    assert sent[0][4] == "90"  # 3600 s -> 60 min + 30


def test_the_hook_ignores_an_invalid_worker_count(tmp_path):
    stub = tmp_path / "tools/remote_test_node"
    stub.mkdir(parents=True)
    (stub / "run.py").write_text("import sys\nprint(' '.join(sys.argv))\n", encoding="utf-8")
    for bad in ("0", "abc", "99", ""):
        script = (
            f'REPO_ROOT="{tmp_path}"; PYTEST_PYTHON="{sys.executable}"; local_sha=abc; MAX_BUDGET=5\n'
            f'warn() {{ :; }}; export AUTOBOT_TEST_NODE_WORKERS="{bad}"\n{_hook_fn()}\n'
            'rc=0; guard_output=""; remote_guard_pytest "a.py" ""; echo "$guard_output"'
        )
        out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False).stdout
        assert " -n 2 " in out, (bad, out)


def test_the_node_collects_its_mirror_and_pins_what_it_installs():
    job = (_TOOL / "remote_job.sh").read_text(encoding="utf-8")
    assert "gc_mirror" in job and 'git --git-dir="$mirror" gc' in job
    prov = (_TOOL / "provision.sh").read_text(encoding="utf-8")
    assert "pip==${AUTOBOT_TEST_NODE_PIP_VERSION" in prov and "--upgrade pip" not in prov


def _split(tmp_path: Path, payload: bytes) -> tuple[subprocess.CompletedProcess, str, str]:
    body = 'reqs="$PWD/reqs.out"; cons="$PWD/cons.out"; : > "$reqs"; : > "$cons"\n' 'split_payload; echo "rc=$?"'
    script = f'PROVISION_SOURCE_ONLY=1 . "{_TOOL}/provision.sh"; set +e\n{body}'
    done = subprocess.run(["bash", "-c", script], input=payload, capture_output=True, cwd=tmp_path, check=False)
    read = lambda n: (tmp_path / n).read_text(encoding="utf-8") if (tmp_path / n).exists() else ""  # noqa: E731
    return done, read("reqs.out"), read("cons.out")


def test_the_payload_splits_into_requirements_and_exactly_the_shared_constraints(tmp_path):
    payload = run._requirements_payload(_ROOT)
    done, reqs, cons = _split(tmp_path, payload.encode("utf-8"))
    assert "rc=0" in done.stdout.decode()
    assert cons == (_ROOT / run.CONSTRAINTS).read_text(encoding="utf-8")
    assert reqs.strip()
    assert not re.search(r"^\s*(-c|--constraint)", reqs, re.MULTILINE)


def test_a_payload_without_the_marker_fails_instead_of_installing_unconstrained(tmp_path):
    done, _reqs, cons = _split(tmp_path, b"pytest==9.0.0\nrequests\n")
    assert done.returncode != 0 and b"marker is missing" in done.stderr
    assert cons == ""


def test_a_crlf_payload_still_splits_at_the_marker(tmp_path):
    done, reqs, cons = _split(tmp_path, b"pytest==9.0.0\r\n#--constraints--\r\nfoo==1.0\r\n")
    assert "rc=0" in done.stdout.decode()
    assert reqs == "pytest==9.0.0\n" and cons == "foo==1.0\n"


@pytest.mark.parametrize(
    "line",
    [
        "-c constraints/shared.txt",
        "-c=constraints/shared.txt",
        "-cconstraints/shared.txt",
        "--constraint constraints/shared.txt",
        "--constraint=constraints/shared.txt",
        "  -c  ../x.txt  ",
        "-c constraints/shared.txt  # the shared pins",
    ],
)
def test_every_relative_constraint_form_is_stripped(tmp_path, line):
    root = _payload_root(tmp_path, f"pytest==9.0.0\n{line}\n")
    head, marker, tail = run._requirements_payload(root).partition(run.CONSTRAINTS_MARKER)
    assert marker and head == "pytest==9.0.0\n"
    assert tail.strip() == "foo==1.0"


@pytest.mark.parametrize("line", ["-r base.txt", "-rbase.txt", "--requirement base.txt", "--requirement=base.txt"])
def test_a_requirement_include_line_is_rejected(tmp_path, line):
    root = _payload_root(tmp_path, f"pytest==9.0.0\n{line}\n")
    with pytest.raises(ValueError, match="cannot be sent"):
        run._requirements_payload(root)


def _payload_root(tmp_path: Path, text: str) -> Path:
    (tmp_path / "constraints").mkdir()
    (tmp_path / "constraints/shared.txt").write_text("foo==1.0\n", encoding="utf-8")
    (tmp_path / run.REQUIREMENTS[0]).write_text(text, encoding="utf-8")
    return tmp_path


def test_a_malformed_version_pin_is_refused(monkeypatch):
    assert all(re.match(r"^\d+(\.\d+)*$", pin) for pin in run._pins())
    monkeypatch.setenv("AUTOBOT_TEST_NODE_PIP_VERSION", "25.3; rm -rf ~")
    with pytest.raises(ValueError, match="not a version number"):
        run._pins()


def _no_ship(*_args, **_kwargs):
    raise AssertionError("a refused provision must not reach the node")


@pytest.mark.parametrize("bad", ["requirements", "pin"])
def test_provision_refuses_before_touching_the_node(tmp_path, monkeypatch, capfd, bad):
    root = _payload_root(tmp_path, "pytest==9.0.0\n-r base.txt\n" if bad == "requirements" else "pytest==9.0.0\n")
    if bad == "pin":
        monkeypatch.setenv("AUTOBOT_TEST_NODE_UV_VERSION", "1.0; echo x")
    monkeypatch.setattr(run.subprocess, "run", _no_ship)
    assert run.provision(run.load_config(_BASE_ENV), root) == 1
    assert "provision refused" in capfd.readouterr().err


def test_a_payload_with_constraints_but_no_requirements_fails(tmp_path):
    done, _reqs, _cons = _split(tmp_path, b"#--constraints--\nfoo==1.0\n")
    assert done.returncode != 0 and b"carries no requirements" in done.stderr


def test_provision_without_an_origin_remote_is_refused_not_a_traceback(tmp_path, monkeypatch, capfd):
    root = _payload_root(tmp_path, "pytest==9.0.0\n")
    (root / ".python-version").write_text("3.14.2\n", encoding="utf-8")
    monkeypatch.setattr(run, "_origin_url", lambda: (_ for _ in ()).throw(subprocess.CalledProcessError(2, "git")))
    monkeypatch.setattr(run.subprocess, "run", _no_ship)
    assert run.provision(run.load_config(_BASE_ENV), root) == 1
    assert "provision refused" in capfd.readouterr().err


def test_a_session_that_gives_no_result_is_unavailable_not_a_124(monkeypatch):
    def _hang(_self, timeout):
        raise subprocess.TimeoutExpired("ssh", timeout)

    monkeypatch.setattr(run, "ship_commit", lambda *_a: None)
    monkeypatch.setattr(run, "_script_command", lambda *_a: "true")
    monkeypatch.setattr(run, "remote_cleanup", lambda *_a: None)
    monkeypatch.setattr(
        run.subprocess, "Popen", lambda *_a, **_k: type("P", (), {"wait": _hang, "poll": lambda s: 0})()
    )
    assert run.run_remote(run.load_config(_BASE_ENV), "abc", ["true"], 30) == run.UNAVAILABLE


def test_an_unsupported_distro_stops_a_package_step_instead_of_passing_it(tmp_path):
    (tmp_path / "os-release").write_text("ID=plan9\n", encoding="utf-8")
    done = _provision(tmp_path, f'OS_RELEASE_FILE="{tmp_path}/os-release"; pkg_available git; echo reached')
    assert done.returncode == 1 and "reached" not in done.stdout
    assert "unsupported distribution 'plan9'" in done.stderr


def test_a_venv_without_a_working_pip_is_rebuilt(tmp_path):
    broken = tmp_path / "base/venv/bin"
    broken.mkdir(parents=True)
    (broken / "python").write_text(
        f'#!/usr/bin/env bash\n[ "$1" = "-m" ] && exit 1\nexec {sys.executable} "$@"\n', encoding="utf-8"
    )
    (broken / "python").chmod(0o755)
    done = _provision(
        tmp_path,
        f'base="{tmp_path}/base"; make_venv "{sys.executable}" 3.0; echo "rc=$?"; "$base/venv/bin/python" -m pip --version',
    )
    assert "no working pip: rebuilding" in done.stderr and "rc=0" in done.stdout, done.stderr
    assert "pip " in done.stdout
