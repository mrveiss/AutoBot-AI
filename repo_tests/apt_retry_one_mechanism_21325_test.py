# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every apt call the install and smoke workflows reach goes through one retry mechanism (#21325).

A DNS blip on an Ubuntu mirror turned install (tty), install (no-tty), smoke-test and
hardened-smoke-test red at once. The mechanism is two tracked files: ``docker/apt/80-autobot-resilience``
(apt settings) and ``docker/apt/apt-retry`` (backoff wrapper). Image builds COPY both and the Clean install
workflow's own apt step uses them.

What the detector SEES: a line, outside comments, in the Clean install / Docker Smoke Test /
Hardened Smoke Test workflow files and the Dockerfiles docker-compose*.yml build, where ``apt-get <verb>``
(or apt-add-repository) is not the first word of its command segment's ``apt-retry`` / ``apt_retry`` call.
What it does NOT see: install.sh (its 1168-line ceiling, #17353, leaves no room for the policy until the
installer's delivery of it is decided -- #21325), apt run by something install.sh starts (the NodeSource setup
script, Ansible roles, scripts/ci/*), Dockerfiles compose does not build, apt reached through a variable or function other than
``apt_retry``, and the apt calls inside the setup-python-suite action (its own wrapper, #15515).
"""

from __future__ import annotations

import re
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_ROOT = repo_root()
_CONF = _ROOT / "docker/apt/80-autobot-resilience"
_HELPER = _ROOT / "docker/apt/apt-retry"
_WORKFLOWS = [
    _ROOT / ".github/workflows" / name
    for name in ("clean-install.yml", "docker-smoke-test.yml", "hardened-smoke-test.yml")
]
_APT = re.compile(
    r"\b(?:apt-get\s+(?:-[oct]\s+\S+\s+|-\S+\s+)*(?:update|install|upgrade|dist-upgrade|download|source|build-dep|remove|purge)\b|apt-add-repository\s|add-apt-repository\s)"
)
_SEGMENT_BREAK = re.compile(r"&&|\|\||;|\||\bthen\b|\bdo\b|\belse\b")
_WRAPPED = re.compile(r"(?:^|[\s/])apt[-_]retry(?:\s|$)")


def _bare_apt(text: str) -> list[tuple[int, str]]:
    """(line number, line) for each apt invocation not first wrapped by apt-retry in its segment."""
    found = []
    for number, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith(("#", "//")):
            continue
        for match in _APT.finditer(line):
            segment = _SEGMENT_BREAK.split(line[: match.start()])[-1]
            if not _WRAPPED.search(segment):
                found.append((number, line.strip()))
    return found


def _count_apt(text: str) -> int:
    return sum(len(_APT.findall(line)) for line in text.splitlines() if not line.lstrip().startswith(("#", "//")))


def _dockerfiles() -> list[Path]:
    names: set[str] = set()
    for compose in _ROOT.glob("docker-compose*.yml"):
        names.update(re.findall(r"^\s*dockerfile:\s*(\S+)", compose.read_text(encoding="utf-8"), re.M))
    assert names, "no compose file names a Dockerfile -- the guard would scan nothing"
    return sorted(_ROOT / name for name in names)


# -- the detector itself: a parser's zero is a claim about the parser -------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "RUN apt-get update && apt-get install -y curl",
        "RUN apt-retry apt-get update && apt-get install -y curl",
        "    && apt-get install -y gh \\",
        "        apt-get update -qq",
        "sudo apt-get install -y -qq expect",
        "        apt-add-repository -y ppa:x/y",
        "RUN apt-get -qq update",
        "RUN apt-retry apt-get update && apt-get -y install curl",
        "    apt-get -o Dpkg::Options::=--force-confold install -y curl",
        "        env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git",
    ],
)
def test_the_detector_flags_an_unwrapped_apt_call(line: str) -> None:
    assert _bare_apt(line), line


@pytest.mark.parametrize(
    "line",
    [
        "RUN apt-retry apt-get update && apt-retry apt-get install -y curl",
        "        apt_retry env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git",
        "sudo sh docker/apt/apt-retry apt-get install -y -qq expect",
        "RUN apt-retry apt-get -qq update",
        "    apt_retry apt-get -o Dpkg::Options::=--force-confold install -y curl",
        "# apt-get update is described here",
        "// apt-get update is described here",
        "    for cmd in curl apt-get openssl; do",
    ],
)
def test_the_detector_accepts_a_wrapped_or_non_apt_line(line: str) -> None:
    assert not _bare_apt(line), line


def test_the_detector_finds_apt_calls_in_the_real_files() -> None:
    """A zero from the real files would mean the pattern stopped matching, not that they are clean."""
    for path in [*_WORKFLOWS[:1], *_dockerfiles()]:
        assert _count_apt(path.read_text(encoding="utf-8")) > 0, f"{path.name}: the detector sees no apt call"


# -- the real files go through the mechanism --------------------------------------------------------


@pytest.mark.parametrize("path", [*_WORKFLOWS, *_dockerfiles()], ids=lambda p: p.name)
def test_every_apt_call_is_wrapped(path: Path) -> None:
    bare = _bare_apt(path.read_text(encoding="utf-8"))
    assert not bare, f"{path.relative_to(_ROOT)}: apt call(s) outside apt-retry: {bare}"


def _stage_problems(text: str) -> tuple[int, list[str]]:
    """(stages swept, one message per stage that runs apt before COPYing the policy and the wrapper)."""
    stages = re.split(r"^FROM\b", text, flags=re.M)[1:]
    problems = []
    for stage in stages:
        copied = ""
        for line in stage.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if _APT.search(line):
                problems += [
                    f"apt before COPY {src}"
                    for src in ("docker/apt/80-autobot-resilience", "docker/apt/apt-retry")
                    if f"COPY {src} " not in copied
                ]
                break
            if line.startswith("COPY "):
                copied += line + "\n"
    return len(stages), problems


_GOOD_STAGE = (
    "FROM x\nCOPY docker/apt/80-autobot-resilience /e\nCOPY docker/apt/apt-retry /b\nRUN apt-retry apt-get update\n"
)


def test_the_stage_sweep_flags_a_stage_without_the_policy_and_accepts_one_with_it() -> None:
    assert _stage_problems(_GOOD_STAGE) == (1, [])
    count, problems = _stage_problems("FROM x\nCOPY docker/apt/apt-retry /b\nRUN apt-retry apt-get update\n")
    assert (count, problems) == (1, ["apt before COPY docker/apt/80-autobot-resilience"])
    assert _stage_problems("RUN apt-get update\n") == (
        0,
        [],
    ), "no FROM: the sweep reaches nothing, which the real-file test must reject"


@pytest.mark.parametrize("path", _dockerfiles(), ids=lambda p: p.name)
def test_each_dockerfile_stage_has_the_policy_and_wrapper_before_its_first_apt_call(path: Path) -> None:
    count, problems = _stage_problems(path.read_text(encoding="utf-8"))
    assert count > 0, f"{path.name}: the stage sweep found no FROM stage, so it checked nothing"
    assert not problems, f"{path.name}: {problems}"


_POLICY_VALUES = {
    "Acquire::Retries": (1, None),
    "Acquire::http::Timeout": (1, None),
    "Acquire::https::Timeout": (1, None),
    "APT::Update::Error-Mode": None,
}


def _policy_problems(conf: str) -> list[str]:
    problems = []
    for key, bounds in _POLICY_VALUES.items():
        m = re.search(rf'^{re.escape(key)}\s+"([^"]*)"\s*;', conf, re.M)
        if m is None:
            problems.append(f"{key} is not set")
        elif bounds is None and m.group(1) != "any":
            problems.append(f"{key} is {m.group(1)!r}, not 'any'")
        elif bounds is not None and not (m.group(1).isdigit() and int(m.group(1)) >= bounds[0]):
            problems.append(f"{key} is {m.group(1)!r}, not a positive number")
    return problems


def test_the_policy_check_flags_a_weakened_value_and_accepts_the_real_policy() -> None:
    weak = 'Acquire::Retries "3";\nAcquire::http::Timeout "0";\nAcquire::https::Timeout "30";\nAPT::Update::Error-Mode "none";\n'
    assert _policy_problems(weak) == [
        "Acquire::http::Timeout is '0', not a positive number",
        "APT::Update::Error-Mode is 'none', not 'any'",
    ]
    assert _policy_problems(_CONF.read_text(encoding="utf-8")) == []


def test_the_wrapper_is_executable_in_git() -> None:
    assert (
        _HELPER.stat().st_mode & stat.S_IXUSR
    ), "COPY keeps the mode: a non-executable apt-retry fails every image build"


# -- the runner mirror fallback (#19308) runs first in Clean install, from one definition -----------

_ACTION = _ROOT / ".github/actions/setup-python-suite/action.yml"
_FALLBACK = "scripts/ci/apt_fallback_mirror.sh"
_INSTALL_STEPS = ('- name: "Step: install (no tty)"', '- name: "Step: install (tty)"')


def _mirror_default(action_text: str) -> str:
    m = re.search(r"^  apt-fallback-mirror:\n(?:    .*\n)*?    default:\s*(\S+)", action_text, re.M)
    assert m, "no apt-fallback-mirror input default found"
    return m.group(1)


def _fallback_before_installs(workflow: str) -> bool:
    """True when the fallback script is called before the first apt use and before either install step."""
    call = workflow.find(_FALLBACK)
    first = [i for i in (workflow.find(s) for s in _INSTALL_STEPS) if i >= 0]
    apt = _APT.search("\n".join(l for l in workflow.splitlines() if not l.lstrip().startswith("#")))
    firsts = first + ([workflow.find(apt.group(0))] if apt else [])
    return call >= 0 and bool(firsts) and call < min(firsts)


def test_the_fallback_mirror_has_exactly_one_definition() -> None:
    mirror = _mirror_default(_ACTION.read_text(encoding="utf-8"))
    hits = [
        p.relative_to(_ROOT).as_posix()
        for p in (_ACTION, _ROOT / _FALLBACK, *_WORKFLOWS)
        if mirror in p.read_text(encoding="utf-8")
    ]
    assert hits == [".github/actions/setup-python-suite/action.yml"], hits


def test_clean_install_repoints_the_mirror_before_any_apt_use() -> None:
    text = (_ROOT / ".github/workflows/clean-install.yml").read_text(encoding="utf-8")
    assert _fallback_before_installs(text)
    assert "apt-fallback-mirror" in text and "action.yml" in text, "the mirror is not read from the action's default"


def test_the_pre_added_ppa_is_the_one_the_installer_adds_and_comes_before_the_install_steps() -> None:
    workflow = (_ROOT / ".github/workflows/clean-install.yml").read_text(encoding="utf-8")
    installer = (_ROOT / "install.sh").read_text(encoding="utf-8")
    ppas = re.findall(r"add_ppa_if_missing \"(ppa:[^\"]+)\"", installer)
    preadded = re.findall(r"apt-retry add-apt-repository -y (ppa:\S+)", workflow)
    assert preadded and set(preadded) <= set(ppas), (preadded, ppas)
    first = workflow.index("apt-retry add-apt-repository")
    assert workflow.index(_FALLBACK) < first < min(workflow.index(s) for s in _INSTALL_STEPS)


def test_a_launchpad_lookup_failure_is_transient_and_its_host_is_reported(tmp_path: Path) -> None:
    msg = "httplib2.error.ServerNotFoundError: Unable to find the server at api.example.invalid"
    done, calls = _run_wrapper(tmp_path, fail_times=99, attempts=2, message=msg)
    assert len(calls) == 2 and "--- getent hosts api.example.invalid" in done.stderr, done.stderr


def test_the_fallback_ordering_check_fires_on_a_fixture() -> None:
    good = f"steps:\n  - run: sudo bash {_FALLBACK}\n  {_INSTALL_STEPS[0]}\n"
    late = f"steps:\n  {_INSTALL_STEPS[0]}\n  - run: sudo bash {_FALLBACK}\n"
    apt_first = f"steps:\n  - run: sudo apt-get install -y x\n  - run: sudo bash {_FALLBACK}\n  {_INSTALL_STEPS[1]}\n"
    assert _fallback_before_installs(good)
    assert not _fallback_before_installs(late)
    assert not _fallback_before_installs(apt_first)
    assert not _fallback_before_installs(f"steps:\n  {_INSTALL_STEPS[0]}\n")


# -- the wrapper's behaviour: stubbed apt-get / getent, no network ----------------------------------

_ERR = "W: Failed to fetch http://mirror.invalid/dists/noble/InRelease  Temporary failure resolving 'mirror.invalid'"
_PERMANENT = "E: Unable to locate package nonesuch"


def _run_wrapper(
    tmp_path: Path,
    fail_times: int,
    attempts: int,
    args=("apt-get", "update"),
    extra_env=None,
    message=_ERR,
    exit_code=100,
):
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh unavailable")
    log = tmp_path / "calls"
    log.write_text("", encoding="utf-8")
    stub = tmp_path / "apt-get"
    stub.write_text(
        f'#!/bin/sh\necho "$*" >> "{log}"\nn=$(wc -l < "{log}")\n'
        f'if [ "$n" -le {fail_times} ]; then echo "{message}"; exit {exit_code}; fi\n',
        encoding="utf-8",
    )
    getent = tmp_path / "getent"
    getent.write_text(f'#!/bin/sh\necho "getent $*" >> "{log}.getent"\nexit 2\n', encoding="utf-8")
    for s in (stub, getent):
        s.chmod(0o755)
    mirrors = tmp_path / "mirrors.txt"
    mirrors.write_text("http://mirror.invalid/ubuntu/\tpriority:1\n", encoding="utf-8")
    env = {
        "PATH": f"{tmp_path}:/usr/bin:/bin",
        "APT_RETRY_ATTEMPTS": str(attempts),
        "APT_RETRY_DELAY_S": "0",
        "APT_RETRY_MIRRORS_FILE": str(mirrors),
        **(extra_env or {}),
    }
    done = subprocess.run([sh, str(_HELPER), *args], env=env, capture_output=True, text=True, timeout=60, check=False)
    return done, log.read_text(encoding="utf-8").splitlines()


def test_a_first_attempt_failure_passes_on_the_second(tmp_path: Path) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=1, attempts=3)
    assert (done.returncode, calls) == (0, ["update", "update"]), done.stderr


def test_a_permanent_failure_is_not_retried_and_keeps_its_exit_code_and_output(tmp_path: Path) -> None:
    done, calls = _run_wrapper(
        tmp_path, fail_times=99, attempts=5, args=("apt-get", "install", "nonesuch"), message=_PERMANENT, exit_code=100
    )
    assert (done.returncode, calls) == (100, ["install nonesuch"]), done.stderr
    assert _PERMANENT in done.stdout and "not retrying" in done.stderr


@pytest.mark.parametrize(
    "message",
    [
        "Err:1 http://m/ubuntu noble InRelease  Connection timed out",
        "E: Failed to fetch http://m/pool/x.deb  503  Service Unavailable [IP: 192.0.2.1 80]",
        "E: Failed to fetch http://m/Packages.gz  Hash Sum mismatch",
        "Could not connect to m:80 (192.0.2.1). - connect (111: Connection refused)",
    ],
)
def test_other_transient_signatures_are_retried(tmp_path: Path, message: str) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=1, attempts=3, message=message)
    assert (done.returncode, len(calls)) == (0, 2), done.stderr


def test_a_404_is_not_transient(tmp_path: Path) -> None:
    _, calls = _run_wrapper(
        tmp_path,
        fail_times=99,
        attempts=3,
        message="E: Failed to fetch http://m/x.deb  404  Not Found [IP: 192.0.2.1 80]",
    )
    assert len(calls) == 1


@pytest.mark.parametrize(
    "env",
    [
        {"APT_RETRY_ATTEMPTS": "many"},
        {"APT_RETRY_ATTEMPTS": "0"},
        {"APT_RETRY_DELAY_S": "soon"},
        {"APT_RETRY_MAX_DELAY_S": "-1"},
    ],
)
def test_an_invalid_setting_fails_before_anything_runs(tmp_path: Path, env: dict) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=0, attempts=3, extra_env=env)
    assert done.returncode == 2 and calls == [], (done.stderr, calls)
    assert "must be an integer" in done.stderr


@pytest.mark.parametrize(
    "args",
    [
        ("apt-get", "install", "-y", "curl"),
        ("apt-get", "-y", "install", "curl"),
        ("apt-get", "-o", "Dpkg::Options::=--force-confold", "install", "curl"),
        ("env", "DEBIAN_FRONTEND=noninteractive", "apt-get", "-qq", "dist-upgrade"),
    ],
)
def test_an_install_retry_reruns_update_first_wherever_the_subcommand_sits(tmp_path: Path, args: tuple) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=1, attempts=3, args=args)
    assert done.returncode == 0, done.stderr
    assert [c.split()[-1] if c.split()[0] == "update" else "cmd" for c in calls] == ["cmd", "update", "cmd"], calls


def test_an_update_retry_does_not_run_a_second_update(tmp_path: Path) -> None:
    _, calls = _run_wrapper(tmp_path, fail_times=2, attempts=3)
    assert calls == ["update"] * 3, calls


def test_exhausted_attempts_fail_loudly_with_the_apt_error_and_resolver_diagnostics(tmp_path: Path) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=99, attempts=3)
    assert done.returncode == 100 and len(calls) == 3
    assert "Temporary failure resolving 'mirror.invalid'" in done.stdout
    assert "giving up after 3 attempts" in done.stderr
    assert "--- getent hosts mirror.invalid" in done.stderr
    assert "http://mirror.invalid/ubuntu/" in done.stderr, "apt-mirrors.txt contents are missing"
    assert (tmp_path / "calls.getent").read_text(encoding="utf-8").strip() == "getent hosts mirror.invalid"


@pytest.mark.parametrize(
    "message",
    [
        "E: Failed to fetch http://m/x.deb  File has unexpected size (1 != 2). Mirror sync in progress?",
        "E: Writing more data than expected (1 > 0)",
    ],
)
def test_mirror_mid_sync_wordings_are_transient(tmp_path: Path, message: str) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=1, attempts=3, message=message)
    assert (done.returncode, len(calls)) == (0, 2), done.stderr


def test_no_arguments_is_a_usage_error() -> None:
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh unavailable")
    done = subprocess.run([sh, str(_HELPER)], capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 2 and "usage: apt-retry" in done.stderr


@pytest.mark.parametrize(
    "env",
    [
        {"APT_RETRY_DELAY_S": "08", "APT_RETRY_MAX_DELAY_S": "00"},
        {"APT_RETRY_DELAY_S": "100", "APT_RETRY_MAX_DELAY_S": "0"},
    ],
)
def test_leading_zeros_are_decimal_and_the_first_delay_is_capped(tmp_path: Path, env: dict) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=2, attempts=4, extra_env=env)
    assert (done.returncode, len(calls)) == (0, 3), done.stderr


def test_a_daemon_holding_the_output_does_not_hang_the_wrapper(tmp_path: Path) -> None:
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh unavailable")
    stub = tmp_path / "apt-get"
    stub.write_text("#!/bin/sh\necho started\nsleep 20 &\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "APT_RETRY_TEE_GRACE_S": "1"}
    start = time.monotonic()
    done = subprocess.run(
        [sh, str(_HELPER), "apt-get", "install", "x"], env=env, capture_output=True, text=True, timeout=15, check=False
    )
    assert done.returncode == 0 and "started" in done.stdout, done.stderr
    elapsed = time.monotonic() - start
    assert 0.9 <= elapsed < 10, f"the wrapper should wait out the 1 s grace, no longer ({elapsed:.1f} s)"


def test_a_prompt_capture_costs_none_of_the_grace(tmp_path: Path) -> None:
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh unavailable")
    stub = tmp_path / "apt-get"
    stub.write_text("#!/bin/sh\necho started\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "APT_RETRY_TEE_GRACE_S": "30"}
    start = time.monotonic()
    done = subprocess.run(
        [sh, str(_HELPER), "apt-get", "install", "x"], env=env, capture_output=True, text=True, timeout=20, check=False
    )
    assert done.returncode == 0 and "started" in done.stdout, done.stderr
    assert time.monotonic() - start < 10, "the wrapper waited out the grace although tee had exited"


def test_the_backoff_is_capped_and_spans_minutes() -> None:
    text = _HELPER.read_text(encoding="utf-8")
    d = {k: int(v) for k, v in re.findall(r'(attempts|delay|max_delay)="\$\{APT_RETRY_\w+:-(\d+)\}"', text)}
    total, delay = 0, d["delay"]
    for _ in range(d["attempts"] - 1):
        total += delay
        delay = min(delay * 2, d["max_delay"])
    assert total >= 300, f"the default window is {total}s; a CI resolver outage lasted a whole job"
