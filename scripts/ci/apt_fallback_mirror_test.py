# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""scripts/ci/apt_fallback_mirror.sh, on fixture apt directories (#19308, #21325).

The first version rewrote only archive.ubuntu.com URIs. The runners resolve the archive through
`mirror+file:/etc/apt/apt-mirrors.txt`, so it matched nothing and the "fallback" retried the
same mirror in silence (#19345 review). These pin both formats and the zero-change signal.

#21325: the script now probes before it repoints. `curl` is a stub on PATH that answers per host from a file in a
tmp dir (ok / fail / empty / stall / second-stalls); the apt directory and os-release are tmp paths, the probe limit is
one second. No network, no sudo, no real /etc/apt.
"""

from __future__ import annotations

import os
import stat
import subprocess  # nosec B404  # fixed argv, no shell
from pathlib import Path

_SCRIPT = Path(__file__).with_name("apt_fallback_mirror.sh")
_MIRROR = "http://fallback.example/ubuntu/"
_PRIMARY_HOST = "azure.archive.ubuntu.com"
_RUNNER_LIST = "http://azure.archive.ubuntu.com/ubuntu/\tpriority:1\nhttp://archive.ubuntu.com/ubuntu/\tpriority:2\n"
_PLAIN_SOURCES = "Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\n"
_MIRROR_SOURCES = "Types: deb\nURIs: mirror+file:/etc/apt/apt-mirrors.txt\nSuites: noble\n\nTypes: deb\nURIs: http://security.ubuntu.com/ubuntu/\n"


def _effective_order(entries: list[str]) -> list[str]:
    """The order apt's mirror+file method tries entries in: by `priority:`, entries without one last."""

    def priority(entry: str) -> float:
        fields = entry.split("\t")[1:]
        values = [int(f.split(":", 1)[1]) for f in fields if f.startswith("priority:")]
        return values[0] if values else float("inf")

    return [e.split("\t")[0] for e in sorted(entries, key=priority)]


_STUB = r"""#!/usr/bin/env bash
out=""; url=""
while [ $# -gt 0 ]; do case "$1" in -o) out=$2; shift 2 ;; -*) shift ;; *) url=$1; shift ;; esac; done
host=${url#*//}; host=${host%%/*}
mode=$(cat "$STUB_DIR/$host" 2>/dev/null || echo fail)
case "$mode" in
  ok) echo "Release" > "$out" ;;
  empty) : > "$out" ;;
  second-stalls) case "$url" in */InRelease) echo "Release" > "$out" ;; *) exec sleep 30 ;; esac ;;
  stall) exec sleep 30 ;;
  *) exit 22 ;;
esac
"""


def _env(tmp_path: Path, primary: str, fallback: str) -> dict[str, str]:
    stub_dir = tmp_path / "stub"
    stub_dir.mkdir(exist_ok=True)
    curl = stub_dir / "curl"
    curl.write_text(_STUB, encoding="utf-8")
    curl.chmod(curl.stat().st_mode | stat.S_IXUSR)
    (stub_dir / _PRIMARY_HOST).write_text(primary, encoding="utf-8")
    (stub_dir / "fallback.example").write_text(fallback, encoding="utf-8")
    osr = tmp_path / "os-release"
    osr.write_text("VERSION_CODENAME=noble\n", encoding="utf-8")
    return {
        **os.environ,
        "PATH": f"{stub_dir}:{os.environ['PATH']}",
        "STUB_DIR": str(stub_dir),
        "APT_PROBE_TIMEOUT_S": "1",
        "APT_FALLBACK_OS_RELEASE": str(osr),
    }


def _run(apt: Path, primary: str = "fail", fallback: str = "ok", *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(  # nosec B603  # fixed argv, no shell
        ["bash", str(_SCRIPT), str(apt), _MIRROR, *args],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
        env=_env(apt.parent, primary, fallback),
    )


def _apt(tmp_path: Path, files: dict[str, str]) -> Path:
    apt = tmp_path / "apt"
    for rel, body in files.items():
        (apt / rel).parent.mkdir(parents=True, exist_ok=True)
        (apt / rel).write_text(body, encoding="utf-8")
    return apt


def test_the_runners_mirror_list_gets_the_fallback_first(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST, "sources.list.d/ubuntu.sources": _MIRROR_SOURCES})

    result = _run(apt)

    assert result.returncode == 0 and result.stdout.strip() == "1", result.stdout + result.stderr
    entries = (apt / "apt-mirrors.txt").read_text(encoding="utf-8").splitlines()
    assert _effective_order(entries) == [
        _MIRROR,
        "http://azure.archive.ubuntu.com/ubuntu/",
        "http://archive.ubuntu.com/ubuntu/",
    ]
    assert (apt / "sources.list.d/ubuntu.sources").read_text(encoding="utf-8") == _MIRROR_SOURCES


def test_a_plain_archive_uri_is_rewritten_and_security_is_left_alone(tmp_path):
    body = "Types: deb\nURIs: http://azure.archive.ubuntu.com/ubuntu/\n\nTypes: deb\nURIs: http://security.ubuntu.com/ubuntu/\n"
    apt = _apt(tmp_path, {"sources.list.d/ubuntu.sources": body})

    assert _run(apt).returncode == 0
    text = (apt / "sources.list.d/ubuntu.sources").read_text(encoding="utf-8")
    assert f"URIs: {_MIRROR}" in text
    assert "URIs: http://security.ubuntu.com/ubuntu/\n" in text
    assert "azure.archive" not in text


def test_nothing_to_point_anywhere_exits_3_rather_than_reporting_success(tmp_path):
    apt = _apt(tmp_path, {"sources.list.d/other.sources": "Types: deb\nURIs: https://packages.example/repo/\n"})

    result = _run(apt)

    assert result.returncode == 3 and result.stdout.strip() == "0"


def test_a_second_run_does_not_stack_the_fallback_and_leaves_the_same_files(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST, "sources.list.d/a.sources": _PLAIN_SOURCES})
    assert _run(apt).returncode == 0
    first = _snapshot(apt)

    assert _run(apt).returncode == 0
    assert _snapshot(apt) == first
    firsts = [e.split("\t")[0] for e in (apt / "apt-mirrors.txt").read_text(encoding="utf-8").splitlines()]
    assert firsts.count(_MIRROR) == 1


def test_the_fallback_outranks_entries_with_and_without_a_priority(tmp_path):
    """#19345 review: a plain prepended line ranked LAST, behind the runner's priority:1/2."""
    apt = _apt(tmp_path, {"apt-mirrors.txt": "http://slow.example/ubuntu/\tpriority:1\nhttp://other.example/ubuntu/\n"})

    assert _run(apt).returncode == 0
    entries = (apt / "apt-mirrors.txt").read_text(encoding="utf-8").splitlines()
    assert _effective_order(entries)[0] == _MIRROR
    assert "http://slow.example/ubuntu/\tpriority:2" in entries


def _snapshot(apt: Path) -> dict[str, str]:
    return {p.relative_to(apt).as_posix(): p.read_text(encoding="utf-8") for p in sorted(apt.rglob("*")) if p.is_file()}


def test_a_healthy_primary_changes_nothing_and_says_so(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST, "sources.list.d/a.sources": _PLAIN_SOURCES})
    before = _snapshot(apt)

    result = _run(apt, primary="ok", fallback="ok")

    assert result.returncode == 3 and result.stdout.strip() == "0"
    assert "primary healthy; fallback not applied" in result.stderr and "primary archive:" in result.stderr
    assert _snapshot(apt) == before


def test_a_bad_primary_and_good_fallback_applies_it_and_keeps_the_primary_lower(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST})

    result = _run(apt)

    assert result.returncode == 0 and result.stdout.strip() == "1"
    assert "fallback mirror applied to 1 apt file(s)" in result.stderr
    entries = (apt / "apt-mirrors.txt").read_text(encoding="utf-8").splitlines()
    assert entries[0] == f"{_MIRROR}\tpriority:1"
    assert f"http://{_PRIMARY_HOST}/ubuntu/\tpriority:2" in entries


def test_a_bad_primary_and_bad_fallback_changes_nothing_and_says_so(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST, "sources.list.d/a.sources": _PLAIN_SOURCES})
    before = _snapshot(apt)

    for fallback in ("fail", "empty"):
        result = _run(apt, primary="fail", fallback=fallback)
        assert result.returncode == 3 and "fallback unhealthy; not applied" in result.stderr, fallback
    assert _snapshot(apt) == before


def test_a_fallback_that_connects_and_then_stalls_is_bad_within_the_limit(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST})
    before = _snapshot(apt)

    for fallback in ("stall", "second-stalls"):
        result = _run(apt, primary="fail", fallback=fallback)
        assert result.returncode == 3 and "fallback unhealthy; not applied" in result.stderr, fallback
        assert "stalled past 1 s" in result.stderr
    assert _snapshot(apt) == before


def test_a_primary_that_answers_once_and_then_stalls_is_still_unhealthy(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST})

    result = _run(apt, primary="second-stalls", fallback="ok")

    assert result.returncode == 0 and "fallback mirror applied" in result.stderr


def test_a_recovered_primary_restores_the_original_files(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST, "sources.list.d/a.sources": _PLAIN_SOURCES})
    before = _snapshot(apt)
    assert _run(apt).returncode == 0 and _snapshot(apt) != before

    result = _run(apt, primary="ok", fallback="ok")

    assert result.returncode == 3 and "restored" in result.stderr
    assert _snapshot(apt) == before, "files and backups back to the pre-fallback state"


def test_primary_known_bad_skips_only_the_primary_probe(tmp_path):
    apt = _apt(tmp_path, {"apt-mirrors.txt": _RUNNER_LIST})

    applied = _run(apt, "ok", "ok", "--primary-known-bad")  # the stub would call the primary healthy
    assert applied.returncode == 0 and "primary archive: not probed" in applied.stderr

    other = _apt(tmp_path / "second", {"apt-mirrors.txt": _RUNNER_LIST})
    refused = _run(other, "ok", "fail", "--primary-known-bad")
    assert refused.returncode == 3 and "fallback unhealthy; not applied" in refused.stderr
    assert (other / "apt-mirrors.txt").read_text(encoding="utf-8") == _RUNNER_LIST
