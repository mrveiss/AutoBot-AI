# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The node-side scripts of the stale code-sync file cleanup, run for real against a temp directory (#22033).

``LIST_SCRIPT`` and ``REMOVE_SCRIPT`` are executed by ``/bin/bash`` exactly as the node would run them (path in
``$1``, candidates on stdin). Each check has its contrast: the file that is listed or removed, and the one that
must not be.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from services import stale_sync_remote as remote
from services.stale_sync_targets import StaleFile, StaleListingError

_ZERO = "0" * 40


def blob_id(content: bytes) -> str:
    """git's blob id of *content*: sha1 of ``blob <size>\\0`` + the bytes."""
    return hashlib.sha1(b"blob %d\0" % len(content) + content, usedforsecurity=False).hexdigest()


_HELLO = hashlib.sha1(b"blob 6\0hello\n", usedforsecurity=False).hexdigest()  # a.py's blob in ``tree``


def run_done(script: str, root: Path, lines: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/bash", "-c", script, "stale-sync", str(root)],
        input="".join(f"{line}\n" for line in lines).encode("utf-8"),
        capture_output=True,
        check=False,
        **kwargs,
    )


def run_script(script: str, root: Path, lines: list[str]) -> list[str]:
    return run_done(script, root, lines).stdout.decode("utf-8").splitlines()


@pytest.fixture
def tree(tmp_path: Path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    (root / "sub").mkdir(parents=True)
    outside.mkdir()
    (root / "a.py").write_bytes(b"hello\n")
    (root / "sub" / "b y.py").write_bytes(b"spaced")
    (outside / "secret").write_bytes(b"s")
    (root / "link.py").symlink_to(outside / "secret")
    (root / "sub" / "dirlink").symlink_to(outside)
    return root, outside


def test_listing_reports_size_mtime_and_the_git_blob_of_a_regular_file_only(tree) -> None:
    root, _ = tree
    out = run_script(remote.LIST_SCRIPT, root, ["a.py", "sub/b y.py", "link.py", "sub/dirlink/secret", "missing.py"])
    rows = {line.split("\t")[3]: line.split("\t") for line in out}
    assert set(rows) == {
        "a.py",
        "sub/b y.py",
    }  # a symlink, a path through a symlinked parent and an absent file are skipped
    assert rows["a.py"][0] == "6" and rows["a.py"][2] == blob_id(b"hello\n")


def test_a_candidate_that_looks_like_shell_is_a_file_name_and_nothing_runs(tree, tmp_path) -> None:
    root, _ = tree
    names = ["$(touch pwned)", "`touch pwned`", "x; touch pwned"]
    for name in names:
        (root / name).write_bytes(b"literal")
    listed = run_done(remote.LIST_SCRIPT, root, names, cwd=tmp_path)
    assert listed.returncode == 0  # the script ran to the end: the names below were processed, not skipped
    assert [line.split("\t")[3] for line in listed.stdout.decode("utf-8").splitlines()] == names
    removal = run_done(remote.REMOVE_SCRIPT, root, [f"{blob_id(b'literal')}\t{names[0]}"], cwd=tmp_path)
    assert removal.returncode == 0 and removal.stdout.decode("utf-8").splitlines() == [f"removed\t{names[0]}"]
    assert not (tmp_path / "pwned").exists() and not (root / "pwned").exists()
    assert not (root / names[0]).exists() and (root / names[1]).exists()


def test_a_file_equal_to_its_approved_blob_is_removed_and_a_changed_one_is_kept(tree) -> None:
    root, _ = tree
    hello = blob_id(b"hello\n")
    out = run_script(remote.REMOVE_SCRIPT, root, [f"{hello}\ta.py", f"{_ZERO}\tsub/b y.py"])
    assert out == ["removed\ta.py", "changed\tsub/b y.py"]
    assert not (root / "a.py").exists() and (root / "sub" / "b y.py").exists()


def test_a_symlink_or_a_path_through_one_is_refused_and_its_target_survives(tree) -> None:
    root, outside = tree
    secret = blob_id(b"s")
    out = run_script(
        remote.REMOVE_SCRIPT, root, [f"{secret}\tlink.py", f"{secret}\tsub/dirlink/secret", f"{_ZERO}\tabsent.py"]
    )
    assert out == ["refused\tlink.py", "refused\tsub/dirlink/secret", "absent\tabsent.py"]
    assert (outside / "secret").exists() and (root / "link.py").is_symlink()


def test_the_command_runs_the_script_under_sudo_with_the_root_as_one_quoted_argument(monkeypatch) -> None:
    monkeypatch.setattr(remote, "key_only_ssh_command", lambda _node: ["ssh", "--", "u@h"])
    cmd = remote._command(object(), remote.LIST_SCRIPT, "/srv/it's a root")
    assert cmd[:3] == ["ssh", "--", "u@h"] and len(cmd) == 4
    assert cmd[3].startswith("sudo -n /bin/bash -c ") and cmd[3].endswith(" stale-sync '/srv/it'\"'\"'s a root'")


async def test_the_listing_keeps_only_well_formed_rows_for_paths_it_asked_about(monkeypatch) -> None:
    async def output(*_a):
        return f"6\t100\t{'a' * 40}\ta.py\nnoise\n1\t2\t{'b' * 40}\tnot_asked.py\nWarning: ssh banner\n"

    monkeypatch.setattr(remote, "_run", output)
    found = await remote.stat_candidates(object(), "/srv", ["a.py"])
    assert [(f.rel, f.size, f.mtime, f.blob) for f in found] == [("a.py", 6, 100, "a" * 40)]


async def test_a_path_the_node_did_not_answer_for_is_failed_never_assumed_removed(monkeypatch) -> None:
    async def output(*_a):
        return "removed\ta.py\n"

    monkeypatch.setattr(remote, "_run", output)
    files = [StaleFile("/srv", "backend", p, 1, None, "a" * 40) for p in ("a.py", "b.py")]  # type: ignore[arg-type]
    assert await remote.remove_files(object(), "/srv", files) == {"a.py": "removed", "b.py": "failed"}


async def test_a_node_that_cannot_be_reached_is_an_error_not_an_empty_listing(monkeypatch) -> None:
    async def down(*_a, **_kw):
        return False, "ssh: connect to host failed"

    monkeypatch.setattr(remote, "run_command", down)
    monkeypatch.setattr(remote, "key_only_ssh_command", lambda _node: ["ssh", "--", "u@h"])
    with pytest.raises(StaleListingError):
        await remote.stat_candidates(type("N", (), {"node_id": "n"})(), "/srv", ["a.py"])


def test_a_symlinked_root_is_refused_by_both_scripts_and_nothing_is_listed_or_removed(tree, tmp_path) -> None:
    root, _ = tree
    alias = tmp_path / "alias"
    alias.symlink_to(root)
    listed = run_done(remote.LIST_SCRIPT, alias, ["a.py"])
    removal = run_done(remote.REMOVE_SCRIPT, alias, [f"{_HELLO}\ta.py"])
    assert (listed.returncode, listed.stdout) == (3, b"") and (removal.returncode, removal.stdout) == (3, b"")
    assert (root / "a.py").exists()  # the contrast, the canonical root, lists and removes in the tests above


@pytest.fixture
def failing_cat(tmp_path) -> dict:
    """A PATH whose ``cat`` writes part of the file and then fails, as a read error mid-file would."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    cat = bin_dir / "cat"
    cat.write_text("#!/bin/sh\nprintf partial\nexit 1\n", encoding="utf-8")
    cat.chmod(0o755)
    return {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}


def test_an_unreadable_file_is_a_listing_error_and_a_failed_removal_never_a_partial_hash(tree, failing_cat) -> None:
    root, _ = tree
    listed = run_done(remote.LIST_SCRIPT, root, ["a.py"], env=failing_cat)
    assert listed.returncode == 4 and listed.stdout == b""
    removal = run_done(remote.REMOVE_SCRIPT, root, [f"{_HELLO}\ta.py"], env=failing_cat)
    assert removal.stdout.decode("utf-8").splitlines() == ["failed\ta.py"] and (root / "a.py").exists()
