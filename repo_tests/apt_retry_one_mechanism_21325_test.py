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
    r"\b(?:apt-get\s+(?:update|install|upgrade|dist-upgrade|download|source|build-dep|remove|purge)\b|apt-add-repository\s|add-apt-repository\s)"
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


@pytest.mark.parametrize("path", _dockerfiles(), ids=lambda p: p.name)
def test_each_dockerfile_stage_has_the_policy_and_wrapper_before_its_first_apt_call(path: Path) -> None:
    stages = re.split(r"^FROM\b", path.read_text(encoding="utf-8"), flags=re.M)[1:]
    for stage in stages:
        copied = ""
        for line in stage.splitlines():
            if line.lstrip().startswith("#"):
                continue
            if _APT.search(line):
                for src in ("docker/apt/80-autobot-resilience", "docker/apt/apt-retry"):
                    assert f"COPY {src} " in copied, f"{path.name}: a stage runs apt before COPY {src}"
                break
            if line.startswith("COPY "):
                copied += line + "\n"


def test_the_policy_sets_the_options_the_mechanism_relies_on() -> None:
    conf = _CONF.read_text(encoding="utf-8")
    for key in ("Acquire::Retries", "Acquire::http::Timeout", "Acquire::https::Timeout", "APT::Update::Error-Mode"):
        assert re.search(rf'^{re.escape(key)}\s+"', conf, re.M), f"{key} is no longer set"


def test_the_wrapper_is_executable_in_git() -> None:
    assert (
        _HELPER.stat().st_mode & stat.S_IXUSR
    ), "COPY keeps the mode: a non-executable apt-retry fails every image build"


# -- the wrapper's behaviour: a first-attempt resolver failure is survived ---------------------------


def _run_wrapper(tmp_path: Path, fail_times: int, attempts: int) -> tuple[subprocess.CompletedProcess, int]:
    sh = shutil.which("sh")
    if sh is None:
        pytest.skip("sh unavailable")
    count = tmp_path / "count"
    count.write_text("0", encoding="utf-8")
    stub = tmp_path / "apt-get"
    stub.write_text(
        f'#!/bin/sh\nn=$(($(cat "{count}") + 1)); echo $n > "{count}"\n'
        f'if [ "$n" -le {fail_times} ]; then echo "W: Temporary failure resolving mirror" >&2; exit 100; fi\n',
        encoding="utf-8",
    )
    stub.chmod(0o755)
    env = {"PATH": f"{tmp_path}:/usr/bin:/bin", "APT_RETRY_ATTEMPTS": str(attempts), "APT_RETRY_DELAY_S": "0"}
    done = subprocess.run(
        [sh, str(_HELPER), "apt-get", "update"], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    return done, int(count.read_text(encoding="utf-8"))


def test_a_first_attempt_failure_passes_on_the_second(tmp_path: Path) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=1, attempts=3)
    assert (done.returncode, calls) == (0, 2), done.stderr


def test_exhausted_attempts_fail_loudly_with_the_apt_error(tmp_path: Path) -> None:
    done, calls = _run_wrapper(tmp_path, fail_times=99, attempts=3)
    assert (done.returncode, calls) == (100, 3)
    assert "Temporary failure resolving mirror" in done.stderr and "giving up after 3 attempts" in done.stderr
