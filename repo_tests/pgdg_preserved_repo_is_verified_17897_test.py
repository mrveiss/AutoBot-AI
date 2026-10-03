# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A repo found already configured is trusted only if it serves the package (#17897).

A one-command install on a host whose image already carried an
``apt.postgresql.org`` source failed at ``Install PostgreSQL packages`` with::

    No package matching 'postgresql-16' is available

The repo-add helper had detected the existing source, logged "preserving
device-shipped config", and skipped adding the canonical ``<codename>-pgdg``
entry. jammy and older ship ``postgresql-14``, so 16 comes only from pgdg --
the preserved source was present and useless, and apt's message named neither
the repository, nor the skip, nor the file responsible.

These assertions pin the three halves of the fix, because each can regress
independently and silently:

1. the helper can tell presence from usability at all,
2. the add still fires when the preserved repo fails verification -- a `when`
   that only tests ``MISSING`` restores the defect while every task above it
   still looks right,
3. the postgresql role actually names the package, since the verification is
   opt-in and an unnamed package means the old behaviour.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
HELPER = ANSIBLE / "roles" / "_shared" / "tasks" / "add_apt_repository_idempotent.yml"
PG_INSTALL = ANSIBLE / "roles" / "postgresql" / "tasks" / "install.yml"

#: The contract parameter that turns presence-checking into usability-checking.
VERIFY_VAR = "apt_repo_verify_package"

#: Below this the file has been gutted or the parse is returning something else,
#: and every assertion keyed on task names would pass over an empty list.
MIN_HELPER_TASKS = 7


def _module(task: dict, name: str) -> object | None:
    """Return a task's module body whether it is written short or fully qualified.

    Ansible accepts both ``set_fact:`` and ``ansible.builtin.set_fact:``. A guard
    that matches only one form reports a missing mechanism that is present, which
    is the same class of false negative the fix itself is about.
    """
    for key in (name, f"ansible.builtin.{name}"):
        if key in task:
            return task[key]
    return None


def _has_module(task: dict, name: str) -> bool:
    return name in task or f"ansible.builtin.{name}" in task


def _tasks(path: Path) -> list[dict]:
    """Parse an ansible task file, failing loudly rather than returning []."""
    if not path.exists():
        pytest.fail(f"{path.relative_to(repo_root())} does not exist -- the fix's home moved")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        pytest.fail(f"{path.relative_to(repo_root())} did not parse as a task list: {type(loaded)}")
    return [t for t in loaded if isinstance(t, dict)]


@pytest.fixture(scope="module")
def helper_tasks() -> list[dict]:
    return _tasks(HELPER)


@pytest.fixture(scope="module")
def pg_tasks() -> list[dict]:
    return _tasks(PG_INSTALL)


def test_the_helper_parses_to_a_populated_task_list(helper_tasks: list[dict]) -> None:
    """FLOOR: an empty or mis-parsed list would make every test below vacuous."""
    assert len(helper_tasks) >= MIN_HELPER_TASKS, (
        f"only {len(helper_tasks)} tasks parsed from {HELPER.name}, expected at least "
        f"{MIN_HELPER_TASKS} -- the assertions below match on task names and would "
        f"pass over a short or empty list without examining anything"
    )


def test_the_helper_decides_sufficiency_rather_than_only_presence(helper_tasks: list[dict]) -> None:
    """The fact that distinguishes "a repo is configured" from "it serves the package"."""
    setters = [t for t in helper_tasks if _has_module(t, "set_fact")]
    decided = [t for t in setters if "_apt_repo_preserve_ok" in str(_module(t, "set_fact"))]
    assert decided, (
        "no task sets `_apt_repo_preserve_ok`. Without it the helper can only answer "
        "'is a source present', which is the #17897 defect: a present source that cannot "
        "serve the package still suppresses the add"
    )


def test_the_preserve_branch_is_gated_on_sufficiency(helper_tasks: list[dict]) -> None:
    """"Preserving device-shipped config" must not be reachable on an unusable repo."""
    preserve = [t for t in helper_tasks if "Preserve device-shipped repo" in str(t.get("name", ""))]
    assert preserve, "the preserve task is gone -- #7218's device-shipped behaviour was dropped"
    for task in preserve:
        assert "_apt_repo_preserve_ok" in str(task.get("when", "")), (
            "the preserve task does not test `_apt_repo_preserve_ok`, so it logs "
            "'preserving device-shipped config' for a repo that serves nothing"
        )


def test_the_add_still_fires_when_the_preserved_repo_fails_verification(
    helper_tasks: list[dict],
) -> None:
    """The regression that would be invisible: a `when` testing only MISSING."""
    adds = [t for t in helper_tasks if _has_module(t, "apt_repository")]
    assert adds, "the apt_repository task is gone -- nothing adds a repo at all now"
    for task in adds:
        when = str(task.get("when", ""))
        assert "MISSING" in when, f"the add no longer fires for an unconfigured repo: {when}"
        assert "_apt_repo_preserve_ok" in when, (
            "the add fires only on MISSING, so a present-but-useless repo is still never "
            "replaced -- this is exactly the #17897 failure, with the verification above "
            "it computing a value nothing acts on"
        )


def test_the_displaced_source_is_moved_outside_sources_list_d_not_deleted(
    helper_tasks: list[dict],
) -> None:
    """apt reads every file in that directory, so disabling in place still collides."""
    movers = [t for t in helper_tasks if "Move aside" in str(t.get("name", ""))]
    assert movers, (
        "nothing moves the unusable source out of the way, so adding the canonical entry "
        "leaves two sources for one URL -- #7218's Signed-By conflict, which aborts "
        "`apt-get update` outright and is worse than the missing package"
    )
    body = str(_module(movers[0], "shell") or "")
    assert "/var/backups/" in body, (
        "the displaced source is not kept under /var/backups -- a device-shipped "
        "configuration must be recoverable, never destroyed"
    )
    assert "sources.list.d" not in body.split("BACKUP_DIR=")[-1].split("\n")[0], (
        "the backup destination is inside sources.list.d, where apt will still read it"
    )


def test_the_failure_names_the_cause_instead_of_leaving_it_to_apt(
    helper_tasks: list[dict],
) -> None:
    """apt's "No package matching" names neither the repo nor the preserved file."""
    fails = [
        t for t in helper_tasks if _has_module(t, "fail") and "real cause" in str(t.get("name", ""))
    ]
    assert fails, (
        "no task fails with the real cause, so a repository that genuinely does not "
        "publish the package still surfaces as apt's bare 'No package matching'"
    )
    msg = str((_module(fails[0], "fail") or {}).get("msg", ""))
    for token in (VERIFY_VAR, "apt_repo_match", "apt_repo_spec"):
        assert token in msg, (
            f"the failure message does not interpolate `{token}`, so it cannot tell the "
            f"operator which package, which host source, or which repo was involved"
        )


def test_the_postgresql_role_names_the_package_it_needs(pg_tasks: list[dict]) -> None:
    """The verification is opt-in: an unnamed package silently keeps the old behaviour."""
    includes = [t for t in pg_tasks if "include_tasks" in str(t)]
    pgdg = [t for t in includes if "add_apt_repository_idempotent" in str(t)]
    assert pgdg, "the postgresql role no longer uses the shared repo-add helper"
    passed = str(pgdg[0].get("vars", {}).get(VERIFY_VAR, ""))
    assert "postgresql-" in passed, (
        f"the postgresql role does not pass `{VERIFY_VAR}` (got {passed!r}). Verification "
        f"is opt-in, so without it a device-shipped apt.postgresql.org source is trusted "
        f"unverified again and the install fails at 'Install PostgreSQL packages'"
    )
    assert "postgresql_version" in passed, (
        f"`{VERIFY_VAR}` hardcodes a version instead of deriving it from "
        f"`postgresql_version`, so the check and the install can disagree about which "
        f"major version is required"
    )
