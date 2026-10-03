# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The nightly Redis backup must survive Jinja rendering and fail loudly (#17932).

`roles/redis/templates/redis-backup.sh.j2` produced **zero** archives for ~125 days
on the live fleet while logging a success line on every run. Two defects, both of
which a source-reading guard is structurally unable to see:

1. Ansible renders templates with ``trim_blocks=True``, which eats the newline
   following a block tag. The template ended one command line with ``{% endif %}``
   and began the next with ``rm``, so the rendered script carried
   ``tar -czf ... appendonly-$TS.aofrm -f ...`` -- one command, ``-f`` twice, tar
   refusing with *"Multiple archive files require '-M'"*. ``set -e`` then aborted
   before the retention sweep, which has therefore never run.
2. The AOF guard tested ``$REDIS_DATA_DIR/appendonly.aof``. Redis 7 keeps append-only
   data in ``appendonlydir/`` (the ``appenddirname`` default), so the guard was false
   on every run and no AOF was ever archived despite ``appendonly yes``.

**Why this file renders rather than greps.** Defect 1 does not exist in the template
source -- the two commands are on two lines there. It is *created* by rendering. Any
assertion over the ``.j2`` text would have passed throughout the 125 days. So every
check here runs against rendered output, and the central one is differential: the
template rendered with ``trim_blocks=True`` must equal the template rendered with
``trim_blocks=False``. That is the invariant "this script's correctness does not
depend on a whitespace setting", stated without naming any particular command pair,
and it reddens for any future block tag placed at the end of a line.

**Reach.** Rendering is unconditional. ``repo_tests._ansible_tasks`` already imports
jinja2 at module level, so it is present wherever this suite runs and a failure to
render is a failure here, never a skip. Only the checks needing external binaries
(``bash -n``, and the end-to-end runs, which need ``bash`` and ``tar``) can skip, and
they skip by name so "the tool was absent" is never read as "the script is clean".

**Limits, stated.** Rendering is plain jinja2 configured to match the ``template``
module's documented defaults (``trim_blocks=True``, ``lstrip_blocks=False``) -- not
Ansible's own templar. That is faithful for this template, which uses no Ansible
filter, lookup or fact; it would not be for one that did. The end-to-end runs replace
the script's two hardcoded directory assignments with tmpdirs and shadow ``redis-cli``,
so they prove the script's *control flow and file handling*, not that a real Redis
BGSAVE lands where the script looks for it.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import tarfile
import time
from pathlib import Path

import pytest
from repo_tests._paths import repo_root
from repo_tests._redis_backup_harness import (
    _BASH,
    _MERGED,
    _OLD_ARCHIVE_AGE_SECONDS,
    _RUNNABLE,
    MIN_RENDERED_LINES,
    RENDER_VARS,
    _archives,
    _command_lines,
    _retarget,
    _run,
    _stage,
    render,
)


@pytest.fixture(scope="module")
def script() -> str:
    """The rendered script with persistence on -- the live fleet's configuration."""
    rendered = render(persistence=True)
    assert len(rendered.splitlines()) >= MIN_RENDERED_LINES, "render produced a stub, not the backup script"
    return rendered


@pytest.mark.parametrize("persistence", [True, False])
def test_rendering_does_not_depend_on_trim_blocks(persistence: bool) -> None:
    """Whitespace stripping must not change a single character of the output.

    This is the general form of the 125-day outage. Against the defective template
    the two renders differed -- one fused ``tar``/``rm``, the other did not -- and
    that difference is the defect itself, with no command name hardcoded here.
    """
    trimmed = render(persistence=persistence, trim_blocks=True)
    untrimmed = render(persistence=persistence, trim_blocks=False)
    assert trimmed == untrimmed, (
        "the rendered script changes when trim_blocks is toggled, so its correctness "
        "depends on Jinja whitespace handling -- move every block tag off the end of a "
        "command line, or decide the condition in shell instead (#17932)"
    )


def test_no_jinja_markers_survive_rendering(script: str) -> None:
    """A leftover ``{%``/``{{`` means a tag was not substituted and shell will choke."""
    for marker in ("{%", "{{", "}}"):
        assert marker not in script, f"unrendered Jinja marker {marker!r} in the generated script"


def test_tar_and_rm_are_separate_commands(script: str) -> None:
    """The specific regression: ``rm`` must be a command, never a ``tar`` argument.

    Counting ``-f`` is the discriminator rather than searching for the word ``rm``:
    the fused line gave tar a second archive flag, which is why it refused with
    *"Multiple archive files require '-M'"* instead of doing something plausible.
    """
    lines = _command_lines(script)
    tar_lines = [line for line in lines if line.startswith("tar ")]
    rm_lines = [line for line in lines if line.startswith("rm ")]
    assert len(tar_lines) == 1, f"expected exactly one tar command, found {tar_lines}"
    assert len(rm_lines) == 1, f"expected exactly one rm command, found {rm_lines}"
    options = [token for token in shlex.split(tar_lines[0])[1:] if token.startswith("-")]
    archive_flags = [token for token in options if "f" in token.lstrip("-")]
    assert len(archive_flags) == 1, (
        f"tar is given the archive flag {len(archive_flags)} times: {tar_lines[0]!r} -- a second "
        "-f is what the trim_blocks fusion produced, and tar refuses it (#17932)"
    )
    # Over executable lines only -- the template quotes the fused token in its own
    # whitespace-contract comment, and a comment is not a command.
    assert not re.search(r"aofrm", "\n".join(lines)), "the historical fused token is back in the output"


def test_aof_is_taken_from_the_redis_7_directory(script: str) -> None:
    """Redis 7's ``appendonlydir/`` must be handled, and the pre-7 file kept."""
    assert re.search(r'\[\s+-d\s+"\$REDIS_DATA_DIR/appendonlydir"\s+\]', script), (
        "no directory test for $REDIS_DATA_DIR/appendonlydir -- Redis 7 keeps the AOF "
        "in a directory, so a file test matches nothing and no AOF is archived (#17932)"
    )
    assert re.search(
        r'\[\s+-f\s+"\$REDIS_DATA_DIR/appendonly\.aof"\s+\]', script
    ), "the pre-Redis-7 single-file layout is no longer handled"


def test_aof_section_is_absent_when_persistence_is_off() -> None:
    """A control: the AOF path is reached only when the role enables persistence."""
    off = render(persistence=False)
    assert "REDIS_PERSISTENCE=no" in off
    assert "REDIS_PERSISTENCE=yes" in render(persistence=True)


@pytest.mark.skipif(_BASH is None, reason="bash is not installed; syntax could not be checked")
@pytest.mark.parametrize("persistence", [True, False])
def test_rendered_script_is_valid_shell(persistence: bool, tmp_path: Path) -> None:
    """``bash -n`` over the rendered script, for both role configurations."""
    path = tmp_path / "redis-backup.sh"
    path.write_text(render(persistence=persistence), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - fixed argv, parse-only, nothing executes
        [str(_BASH), "-n", str(path)], capture_output=True, text=True, timeout=60
    )
    assert done.returncode == 0, f"rendered script is not valid bash:\n{done.stderr}"


@_RUNNABLE
@pytest.mark.parametrize(
    ("aof", "expected_member", "expected_status"),
    [
        ("appendonlydir", "appendonlydir-", "aof=appendonlydir"),
        ("appendonly.aof", "appendonly-", "aof=appendonly.aof"),
    ],
)
def test_a_run_produces_an_archive_holding_the_rdb_and_the_aof(
    tmp_path: Path, aof: str, expected_member: str, expected_status: str
) -> None:
    """Both AOF layouts end in one archive carrying both the dump and the AOF."""
    rc, log, backup_dir = _run(tmp_path, aof=aof)
    assert rc == 0, f"the backup exited {rc}:\n{log}"
    archives = _archives(backup_dir)
    assert len(archives) == 1, f"expected one archive, found {[p.name for p in archives]}\n{log}"
    with tarfile.open(archives[0]) as handle:
        names = handle.getnames()
    assert any(name.startswith("dump-") for name in names), f"no RDB in the archive: {names}"
    assert any(name.startswith(expected_member) for name in names), f"no AOF in the archive: {names}"
    assert expected_status in log.splitlines()[-1], f"final log line omits the AOF verdict:\n{log}"


@_RUNNABLE
def test_the_staged_copies_are_removed_after_archiving(tmp_path: Path) -> None:
    """``rm`` ran as a command. Under the fused line it was a tar argument and never did."""
    rc, log, backup_dir = _run(tmp_path, aof="appendonlydir")
    assert rc == 0, log
    leftovers = [p.name for p in backup_dir.iterdir() if not p.name.endswith(".tar.gz")]
    assert leftovers == [], f"staging copies survived the run: {leftovers}"


@_RUNNABLE
def test_the_retention_sweep_actually_runs(tmp_path: Path) -> None:
    """An archive older than the retention window is deleted; a fresh one is kept.

    The sweep is the last statement before the success line, so it is the first thing
    an abort costs -- it had never executed on the live fleet.
    """
    data_dir, backup_dir, bin_dir = _stage(tmp_path, aof="appendonlydir")
    stale = backup_dir / "redis-backup-20260101_020000.tar.gz"
    stale.write_bytes(b"old")
    old = time.time() - _OLD_ARCHIVE_AGE_SECONDS
    os.utime(stale, (old, old))
    path = tmp_path / "redis-backup.sh"
    path.write_text(_retarget(render(persistence=True), backup_dir, data_dir), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - fixed argv, tmpdir-scoped script, redis-cli shadowed
        [str(_BASH), str(path)],
        stdout=subprocess.PIPE,
        stderr=_MERGED,
        text=True,
        timeout=120,
        env={"PATH": f"{bin_dir}:{os.environ.get('PATH', '/usr/bin:/bin')}", "HOME": str(tmp_path)},
    )
    assert done.returncode == 0, done.stdout
    assert not stale.exists(), f"the {RENDER_VARS['redis_backup_retention_days']}-day sweep did not run"
    assert len(_archives(backup_dir)) == 1, "the sweep deleted the archive it had just written"


@_RUNNABLE
def test_an_abort_after_the_success_line_is_loud(tmp_path: Path) -> None:
    """The silent-success property, asserted directly.

    ``tar`` is shadowed with a failing stub, reproducing the live symptom: the log
    already carries ``Backup created: ...`` by then. The run must still exit non-zero
    and its LAST line must say it failed, because the last line is where an operator
    looks and the first line has always said the backup worked.
    """
    rc, log, backup_dir = _run(tmp_path, aof="appendonlydir", break_tar=True)
    assert "Backup created:" in log, "the harness did not reach the point where the log claims success"
    assert rc != 0, f"a backup that produced no archive exited 0:\n{log}"
    assert _archives(backup_dir) == [], "an archive exists although tar failed"
    last = log.splitlines()[-1]
    assert "FAILED" in last, f"the final log line does not report the failure: {last!r}"
    assert "Redis Stack backup complete" not in log, "an aborted run logged the completion line"


# --------------------------------------------------------------------------------------
# The AOF-layout defect is a CLASS, not an instance (#17932, after #17434, #16060/#16071).
# Fixing only the nightly template would leave the next copy of the same premise to be
# rediscovered, so this sweeps every ansible source that copies AOF data for a backup.
# --------------------------------------------------------------------------------------

#: A site that COPIES the AOF for backup, as opposed to one that merely names the file.
#: `redis-stack.conf.j2` legitimately writes `appendfilename "appendonly.aof"` and must
#: not be flagged -- that is Redis's own setting, and on 7 it lives inside the directory.
AOF_COPY_SITE = re.compile(r"(?:\bs?cp\b|\[\s+-f)[^\n]*appendonly\.aof")

#: Reach floor: the nightly template and `utils/backup.sh`. A sweep finding fewer has
#: stopped reading the tree, and "no offenders" would then mean "nothing was scanned".
MIN_AOF_COPY_SITES = 2

AOF_SOURCE_SUFFIXES = {".sh", ".j2", ".yml", ".yaml"}

#: THIS ONLY SHRINKS. One entry, and it is an admission rather than an allowance: the
#: data-migration play's import end is wrong with certainty, but its SOURCE is a docker
#: container whose Redis version cannot be established from this repository, so the
#: correct copy is not derivable here and guessing it would be worse than saying so.
#: The entry leaves when #17933 answers that question.
AOF_LAYOUT_EXEMPT = {
    "autobot-slm-backend/ansible/playbooks/data-migration.yml": "#17933 -- source Redis version unknown",
}


def test_every_aof_backup_path_handles_the_redis_7_directory() -> None:
    """Any source that copies ``appendonly.aof`` must also know ``appendonlydir``."""
    ansible = repo_root() / "autobot-slm-backend" / "ansible"
    assert ansible.is_dir(), f"{ansible} is missing -- the sweep read nothing"
    offenders: list[str] = []
    sites = 0
    for path in sorted(ansible.rglob("*")):
        if not path.is_file() or path.suffix not in AOF_SOURCE_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if not AOF_COPY_SITE.search(text):
            continue
        sites += 1
        relative = str(path.relative_to(repo_root()))
        if "appendonlydir" not in text and relative not in AOF_LAYOUT_EXEMPT:
            offenders.append(relative)
    assert sites >= MIN_AOF_COPY_SITES, (
        f"found {sites} AOF copy sites, expected at least {MIN_AOF_COPY_SITES} -- the sweep "
        "is not reading the tree, so a clean result here would mean nothing"
    )
    assert not offenders, (
        "these back up the pre-Redis-7 appendonly.aof file and would silently archive no "
        f"AOF on a Redis 7 host: {offenders} (#17932)"
    )
    stale = [name for name in AOF_LAYOUT_EXEMPT if not (repo_root() / name).exists()]
    assert not stale, f"exemptions naming files that no longer exist: {stale}"
