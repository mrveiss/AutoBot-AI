# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A configured apt repo is replaced only on POSITIVE evidence it is broken (#17897).

A one-command install failed at ``Install PostgreSQL packages`` with
``No package matching 'postgresql-16' is available``. The repo-add helper had
found an ``apt.postgresql.org`` source on the host, logged "preserving
device-shipped config", and skipped adding the canonical ``<codename>-pgdg``
entry. jammy and older ship ``postgresql-14``, so 16 comes only from pgdg.

The first fix introduced a worse defect than the one it closed. Its remedy for
an unusable repo is to **move the host's own source aside**, and it decided
usability from an empty ``apt-cache policy`` candidate. ``apt-get update``
**exits 0 with ``W: Failed to fetch``** for an unreachable source -- recorded
under #6719 by the ``nginx | Refresh apt cache`` task -- so a slow mirror
produced an empty candidate on a perfectly good repository, and a working
device-shipped source would have been moved to a backup with a message saying
it "did not serve that package". That claim would have been false.

So the verdict needs positive evidence, and these tests EXECUTE the probe's
ladder against fake ``apt-get``/``apt-cache`` rather than matching its text.
A substring test cannot tell ``not X`` from ``X`` -- which is exactly how the
first version of this file passed over the destructive bug.
"""

from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
HELPER = ANSIBLE / "roles" / "_shared" / "tasks" / "add_apt_repository_idempotent.yml"
PG_INSTALL = ANSIBLE / "roles" / "postgresql" / "tasks" / "install.yml"

VERIFY_VAR = "apt_repo_verify_package"
MATCH = "apt.postgresql.org"
PKG = "postgresql-16"

#: The helper's full task list. Pinned to the real count, not a loose floor: at 7
#: against 9 actual, two tasks could be dropped without reddening anything.
EXPECTED_HELPER_TASKS = 9


def _module(task: dict, name: str) -> object | None:
    """A task's module body whether written short or fully qualified."""
    for key in (name, f"ansible.builtin.{name}"):
        if key in task:
            return task[key]
    return None


def _has_module(task: dict, name: str) -> bool:
    return name in task or f"ansible.builtin.{name}" in task


def _tasks(path: Path) -> list[dict]:
    if not path.exists():
        pytest.fail(f"{path.relative_to(repo_root())} does not exist -- the fix's home moved")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        pytest.fail(f"{path.relative_to(repo_root())} did not parse as a task list")
    return [t for t in loaded if isinstance(t, dict)]


def _named(tasks: list[dict], fragment: str) -> dict:
    hits = [t for t in tasks if fragment in str(t.get("name", ""))]
    assert hits, f"no task whose name contains {fragment!r} -- the mechanism was removed"
    return hits[0]


@pytest.fixture(scope="module")
def helper_tasks() -> list[dict]:
    return _tasks(HELPER)


@pytest.fixture(scope="module")
def probe_script(helper_tasks: list[dict]) -> str:
    """The probe's shell, with Jinja rendered as ansible would render it."""
    body = _module(_named(helper_tasks, "Probe whether the configured repo serves"), "shell")
    assert isinstance(body, str) and body.strip(), "the probe task carries no shell body"
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - shell, not markup
    env.filters["quote"] = shlex.quote
    return env.from_string(body).render(
        apt_repo_match=MATCH,
        apt_repo_verify_package=PKG,
        apt_repo_probe_timeout=5,
        apt_repo_probe_retries=0,
    )


def _policy(candidate: str | None, origins: tuple[str, ...] = ()) -> str:
    """A realistic ``apt-cache policy`` block, including the version table.

    The probe reads the table's origin rows to answer "does THIS repository serve the
    package", so a fixture that prints only a ``Candidate:`` line cannot distinguish
    our source from any other and would make the origin check untestable.
    """
    lines = [f"{PKG}:", "  Installed: (none)", f"  Candidate: {candidate or '(none)'}"]
    lines.append("  Version table:")
    if candidate:
        lines.append(f" *** {candidate} 500")
        for origin in origins:
            lines.append(f"        500 {origin} jammy/main amd64 Packages")
        lines.append("        100 /var/lib/dpkg/status")
    return "\n".join(lines)


def _run_probe(script: str, tmp_path: Path, *, update_out: str, update_rc: int, policy: str) -> str:
    """Execute the probe with apt shadowed, and return its VERDICT."""
    fake = tmp_path / "bin"
    fake.mkdir(exist_ok=True)
    (fake / "apt-get").write_text(
        f"#!/bin/bash\nprintf '%s' {shlex.quote(update_out)} >&2\nexit {update_rc}\n",
        encoding="utf-8",
    )
    (fake / "apt-cache").write_text(f"#!/bin/bash\nprintf '%s\\n' {shlex.quote(policy)}\n", encoding="utf-8")
    for f in fake.iterdir():
        f.chmod(0o755)
    done = subprocess.run(  # noqa: S603 - fixed argv, fakes shadow apt, nothing touches /etc
        ["/bin/bash", "-c", script],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": f"{fake}:/usr/bin:/bin", "HOME": str(tmp_path)},
    )
    for line in done.stdout.splitlines():
        if line.startswith("VERDICT="):
            return line.split("=", 1)[1].strip()
    pytest.fail(f"probe printed no VERDICT.\nstdout={done.stdout}\nstderr={done.stderr}")


def test_the_helper_task_list_is_whole(helper_tasks: list[dict]) -> None:
    """An exact count, so a dropped task reddens instead of passing a loose floor."""
    assert len(helper_tasks) == EXPECTED_HELPER_TASKS, (
        f"{len(helper_tasks)} tasks, expected {EXPECTED_HELPER_TASKS}. Every assertion "
        f"below selects tasks by name and would pass over a shortened list"
    )


def test_a_resolved_candidate_is_usable(probe_script: str, tmp_path: Path) -> None:
    verdict = _run_probe(
        probe_script,
        tmp_path,
        update_out="",
        update_rc=0,
        policy=_policy("16.15-1", (f"https://{MATCH}/pub/repos/apt",)),
    )
    assert verdict == "usable", "a repo that serves the package must be preserved, not replaced"


def test_no_candidate_and_no_error_naming_the_repo_is_unusable(probe_script: str, tmp_path: Path) -> None:
    """The original defect: the repo was reached, said nothing, and serves nothing."""
    verdict = _run_probe(probe_script, tmp_path, update_out="", update_rc=0, policy=_policy(None))
    assert verdict == "unusable", "a clean update with no candidate is the #17897 case and must be replaced"


def test_a_candidate_from_a_DIFFERENT_source_is_not_usable(probe_script: str, tmp_path: Path) -> None:
    """The false-usable case. ``apt-cache policy``'s candidate is a GLOBAL answer.

    If another enabled source supplies the package, a probe that reads "a candidate
    exists" as "this source serves it" answers a different question than the helper
    asks -- and the consequence is the one this whole change exists to prevent: an
    unusable device-shipped source is PRESERVED and the canonical add is skipped.
    The install may still succeed from the other source, which is what makes this
    quiet: the host ends up depending on a source nobody chose, and the broken one
    stays. Covers the pre-add and post-add probes together, since both run this script.
    """
    verdict = _run_probe(
        probe_script,
        tmp_path,
        update_out="",
        update_rc=0,
        policy=_policy("16.15-1", ("http://archive.ubuntu.com/ubuntu",)),
    )
    assert verdict != "usable", (
        "a candidate supplied by an unrelated source marked this source usable. The "
        "helper would preserve a source that serves nothing and skip adding the "
        "canonical one"
    )


def test_a_candidate_this_repo_serves_at_an_older_version_is_still_usable(probe_script: str, tmp_path: Path) -> None:
    """The contrast case that stops the origin check over-firing.

    Judging by the CANDIDATE's origin alone would call this source unusable because
    something else ships a newer build -- and the remedy for unusable DISPLACES the
    host's own configuration. The question is whether this repo serves the package at
    all, so the check counts origin rows across every version, not just the candidate's.
    """
    policy = _policy("16.15-1", ("http://archive.ubuntu.com/ubuntu",))
    policy += f"\n     16.14-1 500\n        500 https://{MATCH}/pub/repos/apt jammy-pgdg/main amd64 Packages"
    verdict = _run_probe(probe_script, tmp_path, update_out="", update_rc=0, policy=policy)
    assert verdict == "usable", (
        "this repository does serve the package, at an older version than another "
        "source's candidate, and was judged unusable -- which would move the host's "
        "own working source aside"
    )


def test_the_post_add_check_fails_unless_the_verdict_is_positively_usable(
    helper_tasks: list[dict],
) -> None:
    """The pre-add path stops on `undetermined`; the post-add path must too.

    Firing only on `unusable` let the play SUCCEED over a post-add probe that never
    confirmed the repository serves the package, and the failure then surfaced three
    steps later as a package-install error. Asked the other way: a PASS of the old
    condition licensed a green play over an unverified provision.
    """
    task = _named(helper_tasks, "Fail with the real cause")
    for verdict, probe, should_fail in [
        ("unusable", "VERDICT=unusable\nUPDATE_RC=0", True),
        ("undetermined", "VERDICT=undetermined\nUPDATE_RC=0", True),
        ("usable", "VERDICT=usable\nUPDATE_RC=0", False),
    ]:
        got = _eval_when(
            _when_of(task),
            apt_repo_verify_package=PKG,
            _apt_repo_verdict="unusable",
            _apt_repo_probe_final={"stdout": probe},
            _apt_repo_moved={"stdout": ""},
        )
        assert got is should_fail, (
            f"post-add verdict {verdict!r}: the play "
            f"{'continued' if should_fail else 'failed'} when it must not. An "
            f"`undetermined` post-add probe means the provision was never confirmed"
        )


def test_a_definitive_server_answer_naming_the_repo_is_unusable(probe_script: str, tmp_path: Path) -> None:
    verdict = _run_probe(
        probe_script,
        tmp_path,
        update_out=f"E: The repository 'https://{MATCH}/pub/repos/apt bogus-pgdg Release'"
        " does not have a Release file.\n",
        update_rc=0,
        policy=_policy(None),
    )
    assert verdict == "unusable", "a 404 / missing Release naming this repo is positive evidence"


def test_a_failed_fetch_naming_the_repo_is_UNDETERMINED_not_unusable(probe_script: str, tmp_path: Path) -> None:
    """THE REGRESSION THAT MATTERS: apt exits 0 on an unreachable mirror (#6719).

    Reading this as "unusable" moves a working device-shipped source to a backup
    and reports a reason that is false. It must touch nothing.
    """
    verdict = _run_probe(
        probe_script,
        tmp_path,
        update_out=f"W: Failed to fetch https://{MATCH}/pub/repos/apt/dists/jammy-pgdg/InRelease"
        "  Connection timed out [IP: 2001:db8::1 443]\n",
        update_rc=0,
        policy=_policy(None),
    )
    assert verdict == "undetermined", (
        "a slow or unreachable mirror was read as proof the repository is broken. The "
        "remedy for 'unusable' MOVES the host's own source aside, so this verdict "
        "destroys working configuration and states a false reason"
    )


def test_a_timeout_is_undetermined(probe_script: str, tmp_path: Path) -> None:
    verdict = _run_probe(probe_script, tmp_path, update_out="", update_rc=124, policy=_policy(None))
    assert verdict == "undetermined", "a timed-out update measured nothing about the repo"


def test_a_held_lock_is_retried_not_judged(probe_script: str, tmp_path: Path) -> None:
    verdict = _run_probe(
        probe_script,
        tmp_path,
        update_out="E: Could not get lock /var/lib/apt/lists/lock. It is held by process 900\n",
        update_rc=100,
        policy=_policy(None),
    )
    assert verdict == "locked", "a dpkg/apt lock must be waited out, never treated as a verdict about the repo"


def _when_of(task: dict) -> str:
    when = task.get("when")
    return " and ".join(f"({c})" for c in when) if isinstance(when, list) else str(when)


def _eval_when(expr: str, **state: object) -> bool:
    """Evaluate an ansible `when` as Jinja, modelling the filters it uses."""
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - condition, not markup
    env.filters["bool"] = lambda v: str(v).strip().lower() in {"true", "yes", "1", "on"} or v is True
    return bool(env.compile_expression(expr, undefined_to_none=True)(**state))


@pytest.mark.parametrize(
    "present,verdict,should_add",
    [
        ("MISSING", "usable", True),
        ("PRESENT", "usable", False),
        ("PRESENT", "unusable", True),
        ("PRESENT", "undetermined", False),
    ],
)
def test_the_add_fires_exactly_when_it_should(
    helper_tasks: list[dict], present: str, verdict: str, should_add: bool
) -> None:
    """Evaluated, not substring-matched: a dropped `not` or an inversion reddens here."""
    block = _named(helper_tasks, "Install the canonical repo definition")
    got = _eval_when(
        _when_of(block),
        _apt_repo_present={"stdout": present},
        _apt_repo_verdict=verdict,
    )
    assert got is should_add, (
        f"present={present} verdict={verdict}: the canonical add "
        f"{'did not fire when it must' if should_add else 'fired when it must not'}. "
        f"Firing on 'undetermined' is the destructive case"
    )


def test_undetermined_changes_nothing_on_the_host(helper_tasks: list[dict]) -> None:
    """The move must be unreachable unless the verdict is positively `unusable`."""
    block = _named(helper_tasks, "Install the canonical repo definition")
    move = _named(block.get("block", []), "Move aside")
    for verdict in ("usable", "undetermined"):
        assert not _eval_when(_when_of(move), _apt_repo_verdict=verdict), (
            f"the move aside is reachable on verdict={verdict!r} -- it may run only on "
            f"positive evidence the repo is broken"
        )
    assert _eval_when(
        _when_of(move), _apt_repo_verdict="unusable"
    ), "the move never runs, so an unusable source is never replaced"


def test_a_failed_add_restores_the_moved_source(helper_tasks: list[dict]) -> None:
    block = _named(helper_tasks, "Install the canonical repo definition")
    rescue = block.get("rescue") or []
    assert rescue, (
        "the add has no rescue, so a failure after the move leaves the host with no "
        "source for this repository at all"
    )
    restore = _named(rescue, "Restore the moved source")
    body = str(_module(restore, "shell") or "")
    # This used to assert the literal "/etc/apt/sources.list.d/" appeared in the
    # script -- a mechanism assertion that passed while the rescue restored EVERY
    # backup generation, because a glob over the backup directory contains that
    # string too. What matters is that the restore is SCOPED to this run, which the
    # destination now carries per-file from the move's PAIR line.
    assert "_AUTOBOT_MOVED" in body or "PAIR" in body, (
        "the restore does not read the move's own output, so it can only find files "
        "by globbing the backup directory -- which restores earlier runs' sources too"
    )
    # Asserted as "does not need the backup DIRECTORY" rather than by matching a
    # glob pattern: the pattern as a literal here reads as a glob declaration to
    # repo_tests/glob_declared_reads_15900_test.py, which is correct about the string
    # and wrong about this file. A restore scoped to the move's output never needs
    # the directory, because each backup's full path arrives on its PAIR line.
    assert "BACKUP_DIR" not in body, (
        "the restore still resolves the backup directory, which it only needs in order "
        "to iterate it. Backups are never deleted after a successful add, so that "
        "directory accumulates generations and iterating it puts an earlier run's "
        "source back beside the current one -- #7218's collision, reintroduced"
    )
    failures = [t for t in rescue if _has_module(t, "fail")]
    assert failures, "the rescue restores but never fails -- the deploy would continue"
    msg = str((_module(failures[0], "fail") or {}).get("msg", ""))
    assert "apt_repo_backup_dir" in msg or "backups" in msg, (
        "the failure message does not name the backup location, so the operator cannot "
        "find the configuration that was moved"
    )


def _rescue_script(helper_tasks: list[dict]) -> str:
    """The rescue's restore shell, Jinja rendered as ansible would render it."""
    block = _named(helper_tasks, "Install the canonical repo definition")
    restore = _named(block.get("rescue") or [], "Restore the moved source")
    body = _module(restore, "shell")
    assert isinstance(body, str) and body.strip(), "the restore task carries no shell body"
    env = jinja2.Environment(autoescape=False)  # noqa: S701 - shell, not markup
    env.filters["quote"] = shlex.quote
    return env.from_string(body).render(apt_repo_match=MATCH, apt_repo_backup_dir="/unused-by-this-path")


def test_the_move_emits_a_machine_readable_pair_for_the_rescue(
    helper_tasks: list[dict],
) -> None:
    """The rescue's input contract. Without it the rescue cannot scope to this run."""
    block = _named(helper_tasks, "Install the canonical repo definition")
    move = str(_module(_named(block.get("block", []), "Move aside"), "shell") or "")
    assert "PAIR" in move and "printf" in move, (
        "the move no longer emits a PAIR line, so the rescue has nothing to scope to "
        "and would have to glob the backup directory -- which restores every generation"
    )


def test_the_rescue_restores_only_this_runs_backup_not_every_generation(
    helper_tasks: list[dict], tmp_path: Path
) -> None:
    """Two generations in one backup directory; only this run's may come back.

    Nothing deletes a backup after a SUCCESSFUL add -- a displaced device
    configuration stays recoverable on purpose -- so the directory accumulates. The
    first version of this rescue globbed ``$BACKUP_DIR/*.bak`` and filtered on
    content, so a later run that hit the keyserver transient the ``until:`` exists
    for would restore an EARLIER run's source as well. Two sources for one repo in
    ``sources.list.d`` is #7218's Signed-By collision, reintroduced on a host that
    was fine by the code meant to protect it.
    """
    sources, backups = tmp_path / "sources.list.d", tmp_path / "backups"
    sources.mkdir()
    backups.mkdir()
    stale = backups / "pgdg-old.list.20260101T000000Z.bak"
    stale.write_text(f"deb https://{MATCH}/pub/repos/apt old-pgdg main\n", encoding="utf-8")
    mine = backups / "pgdg.list.20261003T120000Z.bak"
    mine.write_text(f"deb https://{MATCH}/pub/repos/apt jammy-pgdg main\n", encoding="utf-8")

    # Exactly what the move would have emitted for THIS run: one file.
    moved = f"Moved aside {sources / 'pgdg.list'}\nPAIR\t{sources / 'pgdg.list'}\t{mine}\n"
    done = subprocess.run(  # noqa: S603 - fixed argv, all paths under tmp_path
        ["/bin/bash", "-c", _rescue_script(helper_tasks)],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "_AUTOBOT_MOVED": moved},
    )
    assert done.returncode == 0, f"rescue failed: {done.stderr}"
    assert (sources / "pgdg.list").is_file(), (
        f"this run's source was not restored, so a failed add leaves the host with no "
        f"source at all. stdout={done.stdout} stderr={done.stderr}"
    )
    assert stale.is_file(), (
        "an EARLIER run's backup was restored as well. Both sources now sit in "
        "sources.list.d for one repo, which is the #7218 Signed-By collision this "
        "file moves files out of that directory to avoid"
    )
    assert not (sources / "pgdg-old.list").exists(), (
        "the stale generation was written into sources.list.d -- apt reads every file "
        "in that directory, so the collision is live"
    )
    assert "Restored" in done.stdout, "the rescue restored silently; the log must say what came back"


def test_the_rescue_says_so_when_this_run_moved_nothing(helper_tasks: list[dict], tmp_path: Path) -> None:
    """A MISSING-repo add that fails moved nothing, and must restore nothing."""
    backups = tmp_path / "backups"
    backups.mkdir()
    stale = backups / "pgdg.list.20260101T000000Z.bak"
    stale.write_text(f"deb https://{MATCH}/pub/repos/apt old-pgdg main\n", encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - fixed argv, all paths under tmp_path
        ["/bin/bash", "-c", _rescue_script(helper_tasks)],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "_AUTOBOT_MOVED": ""},
    )
    assert done.returncode == 0, f"rescue failed on an empty move set: {done.stderr}"
    assert "Nothing to restore" in done.stdout, f"expected an explicit no-op: {done.stdout}"
    assert stale.is_file(), "a backup was consumed although this run moved nothing"


def test_the_postgresql_role_names_the_package_it_needs() -> None:
    """Verification is opt-in: an unnamed package silently keeps the old behaviour."""
    pgdg = [
        t
        for t in _tasks(PG_INSTALL)
        if "add_apt_repository_idempotent" in str(t.get("ansible.builtin.include_tasks", ""))
    ]
    assert pgdg, "the postgresql role no longer uses the shared repo-add helper"
    passed = str(pgdg[0].get("vars", {}).get(VERIFY_VAR, ""))
    assert "postgresql-" in passed, (
        f"the role does not pass `{VERIFY_VAR}` (got {passed!r}), so a device-shipped "
        f"apt.postgresql.org source is trusted unverified again"
    )
    assert "postgresql_version" in passed, (
        f"`{VERIFY_VAR}` hardcodes a version instead of deriving it from "
        f"`postgresql_version`, so the check and the install can disagree"
    )


# ── The verdict must survive a probe that named no VERDICT ────────────────────
#
# Broke a real install at 18:06 on 2026-10-03, hours after #17897 merged:
#
#     TASK [postgresql : PostgreSQL pgdg | Record the verdict]
#     fatal: [00-SLM-Manager]: FAILED! => {"changed": false}
#
# No message. `set_fact` evaluating a raising expression reports the bare dict,
# so the play stopped and said nothing -- on the documented one-line installer,
# which is the first thing a new user runs.
#
# Cause: `regex_search(...) | first | default('undetermined', true)`. On no match
# `regex_search` returns None, and `None | first` raises BEFORE the default can
# apply. A default placed after `first` can never run.
#
# Two reachable no-match paths, so this is not a corner: the probe is skipped by
# its `when:` (stdout undefined), or it ran and emitted no VERDICT line. The
# second shows as `ok:` because of `failed_when: false` -- which is exactly what
# the broken install printed one task before the failure.


def test_the_no_match_default_precedes_first(helper_tasks: list[dict]) -> None:
    """`default` must sit BEFORE `first`. That ordering IS the defect.

    Asserted on filter order rather than by rendering, deliberately. Rendering
    needs a Jinja environment whose `first` behaves as Ansible's does, and a
    hand-rolled `first` (``next(iter(x))``) raises on an empty list where Jinja's
    returns Undefined -- so it reports a FALSE FAILURE against correct code. That
    happened while fixing this, and a test that can cry wolf about a working tree
    is worse than no test.
    """
    expr = " ".join(
        str(_named(helper_tasks, "Record the verdict")["ansible.builtin.set_fact"]["_apt_repo_verdict"]).split()
    )

    assert "| default([], true) | first" in expr, (
        "the no-match guard is missing or misplaced. `regex_search` returns None when "
        "the pattern does not match and `None | first` raises TypeError, which set_fact "
        "reports as a bare FAILED with no message. The default must PRECEDE `first`. "
        f"Expression now reads: {expr}"
    )


def test_an_undetermined_verdict_still_halts_the_play(helper_tasks: list[dict]) -> None:
    """Routing a no-match to `undetermined` only helps if something still stops.

    The fix turns a raise into a verdict. If nothing downstream halted on that
    verdict, the change would convert a loud crash into a silent `usable` -- which
    is strictly worse than the bug it replaces. This pins the halt.
    """
    stoppers = [
        str(t.get("name", ""))
        for t in helper_tasks
        if "Stop:" in str(t.get("name", "")) or "could not determine" in str(t.get("name", ""))
    ]

    assert stoppers, (
        "no task halts on an undetermined verdict. Without one, a probe that named no "
        "VERDICT would pass as fine and the unusable-repo case this helper exists for "
        "would ship silently."
    )
