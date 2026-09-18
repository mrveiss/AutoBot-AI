# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16299 review round 3: the VNC password's secrets-vault registration must
never abort the provisioning play, must never silently swallow a genuine
failure either, and a fresh host must end ONE run with the secret actually
registered.

Round 1 fixed the local-marker-file gate (a failed attempt was never
retried) by gating on an actual vault read-back instead, with retry/wait
logic -- round 2 found that retrying just delayed the same abort, since
setup-user-backend.yml runs `roles:` (which includes the vnc role) BEFORE
`post_tasks:` (which runs the backend's secrets-table migration): on a
fresh host the vault table cannot exist while the vnc role's inline task
runs, however long it retries.

Round 2's own fix (block/rescue around the registration call, in both
tasks/main.yml and setup-user-backend.yml's post_tasks) was ALSO wrong, in
the opposite direction: rescuing every failure into a debug line is only
correct for the ONE case that is genuinely expected to fail
(setup-user-backend.yml's roles:-phase call, pre-migration). On every OTHER
playbook that includes this role (deploy.yml, playbooks/deploy_role.yml,
playbooks/enroll-node.yml, playbooks/provision-fleet-roles.yml -- none run
migrations, so the vault already exists) and in setup-user-backend.yml's
OWN post_tasks call (after migrations), a failure is real (wrong API key,
backend down) and rescuing it just makes VNC fail closed silently.

Fixed with an explicit `vnc_defer_vault_registration` role var (defaults to
false): setup-user-backend.yml sets it true for the vnc role, so
tasks/main.yml SKIPS registration entirely there (nothing to rescue --
logged as deferred instead) and calls register-vnc-password.yml again,
unrescued, from its own post_tasks after migrations. Every other playbook
leaves the flag false, so tasks/main.yml's call there is unrescued too --
a real failure fails the play, as it should.

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


def test_non_desktop_registration_refusal_is_a_top_level_task() -> None:
    """vnc_type is hardcoded to "desktop" (co-located, loopback-adjacent)
    everywhere this role is invoked today. The registration POST goes over
    plain HTTP with no TLS -- safe for that loopback case, but would send
    the password in cleartext to a genuinely remote host once "browser" is
    wired. This is a real misconfiguration, not a migration-timing flake, so
    it must hard-fail the play unconditionally -- it must not be nested
    inside any conditional block that could soften it (there is no
    block/rescue in this file at all as of round 3, but a future edit
    reintroducing one around this task would be exactly the regression this
    guards against)."""
    text = _text(_VNC_MAIN_TASKS)
    fail_idx = text.index('name: "VNC | Refuse to register a non-co-located host')
    deferred_idx = text.index('name: "VNC | Secrets-vault registration deferred')
    assert fail_idx < deferred_idx, "the refusal must be declared before the deferred-log task"
    refusal_task_text = text[fail_idx : text.index("\n\n", fail_idx)]
    assert not refusal_task_text.startswith("    - name:"), (
        "the non-desktop refusal must be a top-level task, not nested inside a block -- "
        "otherwise a real misconfiguration could be softened into a rescued debug message "
        "instead of hard-failing the play (#16299 review)"
    )


def test_main_tasks_registration_defers_rather_than_rescues() -> None:
    """#16299 review round 3: a failure here is only ever expected on
    setup-user-backend.yml, which sets vnc_defer_vault_registration true and
    so never reaches the registration call at all -- it gets a deferred-log
    debug instead. On every OTHER playbook the flag is false, the call runs
    for real, and it must NOT be rescued: a failure there is genuine and
    must fail the play, not degrade into a silent debug line."""
    text = _text(_VNC_MAIN_TASKS)
    start = text.index('name: "VNC | Secrets-vault registration deferred')
    end = text.index("--- Node-level TLS cert")
    block = text[start:end]
    assert "vnc_defer_vault_registration" in block, (
        "the registration call must be gated on vnc_defer_vault_registration, not "
        "wrapped in a block/rescue that would swallow a genuine failure on every "
        "other playbook (#16299 review round 3)"
    )
    assert "rescue:" not in block, (
        "no rescue here -- a failure on a non-deferring playbook is real (wrong API key, "
        "backend down) and must fail the play, not become a silent debug line (#16299 review round 3)"
    )
    assert "register-vnc-password.yml" in block


def test_defer_flag_defaults_to_false() -> None:
    defaults_path = REPO_ROOT / "autobot-slm-backend/ansible/roles/vnc/defaults/main.yml"
    text = _text(defaults_path)
    assert "vnc_defer_vault_registration: false" in text, (
        "vnc_defer_vault_registration must default to false -- only setup-user-backend.yml "
        "opts into deferring (#16299 review round 3)"
    )


def test_setup_user_backend_sets_the_defer_flag_for_the_vnc_role() -> None:
    text = _text(_SETUP_USER_BACKEND)
    role_idx = text.index("role: vnc")
    post_tasks_idx = text.index("post_tasks:")
    role_block = text[role_idx:post_tasks_idx]
    assert "vnc_defer_vault_registration: true" in role_block, (
        "setup-user-backend.yml must set vnc_defer_vault_registration: true on the vnc role "
        "include -- its roles:-phase invocation runs before this play's own migrations "
        "(#16299 review round 3)"
    )


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


def test_setup_user_backend_post_migration_call_is_not_rescued() -> None:
    """#16299 review round 3: after migrations run and the health check
    above confirms the backend is up, a registration failure here is real
    (wrong API key, backend actually down) -- it must fail the play, not
    degrade into a debug line. Recovery is re-running this playbook through
    the builtin updater; there is no manual recovery path to fall back to."""
    text = _text(_SETUP_USER_BACKEND)
    start = text.index("Register the VNC password now that migrations have run")
    end = text.index("Display setup summary")
    block = text[start:end]
    assert "rescue:" not in block, (
        "the post-migration registration call must NOT be rescued -- migrations have already "
        "run and the backend is confirmed up, so a failure here is genuine (#16299 review round 3)"
    )
    assert "tasks_from: register-vnc-password" in block
    assert "register the secret by hand" not in text.lower(), (
        "no manual-recovery language -- recovery is re-running the playbook through the "
        "builtin updater (#16299 review round 3)"
    )


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
