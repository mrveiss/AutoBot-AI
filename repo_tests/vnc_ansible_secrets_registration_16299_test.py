# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16299 review round 2: the VNC password's secrets-vault registration must
never abort the provisioning play, and a fresh host must end ONE run with
the secret actually registered.

Round 1 fixed the local-marker-file gate (a failed attempt was never
retried) by gating on an actual vault read-back instead, with retry/wait
logic. That was still wrong: setup-user-backend.yml runs `roles:` (which
includes the vnc role) BEFORE `post_tasks:` (which runs the backend's
secrets-table migration). On a fresh host the vault table cannot exist
while the vnc role's inline task runs, however long it retries -- the
retries just delay a `uri` task failure that still aborts the whole play
before post_tasks, including the migrations themselves, ever run. A fresh
host could then never finish provisioning at all, not just lose VNC.

Fixed by splitting the registration logic into its own tasks file
(register-vnc-password.yml) called from two places: tasks/main.yml calls it
best-effort (block/rescue) for every OTHER playbook that includes this role
on an already-provisioned, already-migrated host; setup-user-backend.yml
ALSO calls it directly from its own post_tasks, after the migration
sequence, which is the one playbook where the roles:-phase attempt cannot
succeed on a fresh host. register-vnc-password.yml's own vault-read-back check
makes a second, later, successful call safe regardless of whether the
first one ran, skipped, or failed.

No live ansible target host is available in this environment; these are
static assertions on the task files' own text, same approach as
repo_tests/ansible_generated_secrets_16299_test.py. The retry/idempotency
jinja logic itself was verified functionally with a throwaway playbook
before relying on it (see the PR's own commit messages).
"""

from __future__ import annotations

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
_VNC_MAIN_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/vnc/tasks/main.yml"
_VNC_REGISTER_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/vnc/tasks/register-vnc-password.yml"
_SETUP_USER_BACKEND = REPO_ROOT / "autobot-slm-backend/ansible/setup-user-backend.yml"


def _text(path) -> str:
    assert path.is_file(), f"{path} is missing — this guard would otherwise pass vacuously"
    return path.read_text(encoding="utf-8")


def test_registration_logic_lives_in_its_own_tasks_file() -> None:
    """Split out so it can be called from a point after migrations, not just
    inline where the vnc role happens to sit in a play's roles: list."""
    assert _VNC_REGISTER_TASKS.is_file(), (
        "roles/vnc/tasks/register-vnc-password.yml is missing -- the registration logic must be its "
        "own tasks file so it can be called again after migrations run (#16299 review round 2)"
    )


def test_registration_is_not_gated_on_the_local_marker_file() -> None:
    block = _text(_VNC_REGISTER_TASKS)
    assert "vnc_secrets_stat.stat.exists" not in block, (
        "register-vnc-password.yml must not gate on the local vnc-secrets.env marker file -- that "
        "file is created before this code runs, so a failed first attempt would never be "
        "retried on any later run (#16299 review)"
    )


def test_registration_checks_the_vault_before_posting() -> None:
    block = _text(_VNC_REGISTER_TASKS)
    assert "selectattr('name', 'equalto', 'vnc-password-' + vnc_type)" in block, (
        "the registration POST must be gated on an actual read-back of the secrets vault "
        "(does this name already exist?), not just on having generated a local password"
    )


def test_registration_and_readback_have_retry_logic() -> None:
    block = _text(_VNC_REGISTER_TASKS)
    assert block.count("retries:") >= 2, (
        "both the vault read-back and the registration POST need retry/wait logic against a "
        "backend whose secrets-table migration may not have run yet (#16299 review)"
    )
    assert "until:" in block


def test_no_hardcoded_backend_port_default() -> None:
    """#16299 review round 2: backend_port | default(8001) was a second,
    redundant hardcoded port literal -- roles/backend/defaults/main.yml's
    backend_port is the single source of truth. Must fail loudly if
    undefined, not silently substitute a guessed value."""
    block = _text(_VNC_REGISTER_TASKS)
    assert "default(8001)" not in block, "no hardcoded port default -- use backend_port directly (#16299 review)"
    assert "backend_port is defined" in block, (
        "must assert backend_port is defined and fail clearly if not, rather than silently "
        "defaulting to a hardcoded port (#16299 review)"
    )


def test_non_desktop_registration_is_a_hard_failure_not_rescued() -> None:
    """vnc_type is hardcoded to "desktop" (co-located, loopback-adjacent)
    everywhere this role is invoked today. The registration POST goes over
    plain HTTP with no TLS -- safe for that loopback case, but would send
    the password in cleartext to a genuinely remote host once "browser" is
    wired. This is a real misconfiguration, not a migration-timing flake, so
    it must hard-fail the play -- NOT be swallowed by the same block/rescue
    that makes migration-timing failures non-fatal."""
    text = _text(_VNC_MAIN_TASKS)
    fail_idx = text.index('name: "VNC | Refuse to register a non-co-located host')
    block_idx = text.index('name: "VNC | Register the VNC password in the canonical secrets system (best-effort')
    assert fail_idx < block_idx, "the refusal must be declared before the best-effort block, not inside it"
    # Confirm the refusal task itself is not nested inside a `block:` (i.e. not indented as a
    # block/rescue child) -- it must sit at the same top level as the block it precedes.
    refusal_task_text = text[fail_idx : text.index("\n\n", fail_idx)]
    assert not refusal_task_text.startswith("    - name:"), (
        "the non-desktop refusal must be a top-level task, not nested inside the best-effort "
        "block/rescue -- otherwise a real misconfiguration degrades into a rescued debug "
        "message instead of hard-failing the play (#16299 review)"
    )


def test_main_tasks_registration_is_best_effort() -> None:
    """The roles:-phase call (every playbook other than setup-user-backend.yml)
    must never abort the play -- block/rescue, mirroring the existing
    "Register VNC credentials in SLM" pattern in this same file."""
    text = _text(_VNC_MAIN_TASKS)
    start = text.index('name: "VNC | Register the VNC password in the canonical secrets system (best-effort')
    end = text.index("--- Node-level TLS cert")
    block = text[start:end]
    assert "rescue:" in block, "the roles:-phase registration call must be wrapped in block/rescue (#16299 review)"
    assert "register-vnc-password.yml" in block


def test_setup_user_backend_registers_again_after_migrations() -> None:
    """The play-order fix itself: setup-user-backend.yml must call
    register-vnc-password AFTER its migration task runs, not rely solely on the
    vnc role's own roles:-phase attempt (which cannot succeed on a fresh
    host, since roles: runs before post_tasks' migrations)."""
    text = _text(_SETUP_USER_BACKEND)
    migration_idx = text.index("Database migration sequence (Postgres-backed modes)")
    register_idx = text.index("Register the VNC password now that migrations have run")
    assert migration_idx < register_idx, (
        "the post-migration VNC registration call must come AFTER the migration task in "
        "setup-user-backend.yml's post_tasks, not before it (#16299 review round 2)"
    )
    # Confirm it's actually in post_tasks, not roles: -- both must be past the `post_tasks:` marker.
    post_tasks_idx = text.index("post_tasks:")
    assert post_tasks_idx < migration_idx < register_idx


def test_setup_user_backend_post_migration_call_is_also_rescued() -> None:
    """Even the authoritative post-migration attempt must not fail the whole
    provisioning run if it somehow still fails -- VNC registration is not
    as critical as the migrations themselves."""
    text = _text(_SETUP_USER_BACKEND)
    start = text.index("Register the VNC password now that migrations have run")
    end = text.index("Display setup summary")
    block = text[start:end]
    assert "rescue:" in block, (
        "the post-migration registration call must also be wrapped in block/rescue -- it must "
        "never fail the overall provisioning run (#16299 review round 2)"
    )
    assert "tasks_from: register-vnc-password" in block


def test_the_password_read_task_has_no_log() -> None:
    """#16299 review: the pre-existing 'Read VNC password from secrets file'
    task's stdout is the plaintext password. It predates this PR but this PR
    added a real consumer of it, making the missing no_log more consequential."""
    text = _text(_VNC_MAIN_TASKS)
    start = text.index("name: Read VNC password from secrets file")
    end = text.index("name: Set VNC password file for user")
    block = text[start:end]
    assert "no_log: true" in block, (
        "'Read VNC password from secrets file' must carry no_log: true -- its stdout is the "
        "plaintext password, and #16299 added a real consumer of it (#16299 review)"
    )
