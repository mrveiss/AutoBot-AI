# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16299 review: the VNC password's secrets-vault registration must be
idempotent and self-healing, not gated on a local marker file.

A fresh host's first attempt can genuinely fail (the backend's secrets-table
migration may not have run yet, since this role can run before it in some
playbooks). The task used to be gated on the LOCAL password-generation
marker file, which is created before this ever runs and only exists once
per host, ever -- a failed first attempt was never retried, permanently
breaking the VNC feature on that host. These assert the fix: gating on an
actual vault read-back instead, plus retry/wait logic against a backend
that may not be ready yet, plus an explicit refusal to send the password
over plaintext HTTP to a non-co-located host.

No live ansible target host is available in this environment; these are
static assertions on the task file's own text, same approach as
repo_tests/ansible_generated_secrets_16299_test.py. The retry/idempotency
jinja logic itself was verified functionally with a throwaway playbook
before relying on it (see the PR's own commit message).
"""

from __future__ import annotations

from repo_tests._paths import repo_root

REPO_ROOT = repo_root()
_VNC_TASKS = REPO_ROOT / "autobot-slm-backend/ansible/roles/vnc/tasks/main.yml"


def _text() -> str:
    assert _VNC_TASKS.is_file(), f"{_VNC_TASKS} is missing — this guard would otherwise pass vacuously"
    return _VNC_TASKS.read_text(encoding="utf-8")


def _registration_block() -> str:
    text = _text()
    start = text.index('name: "VNC | Read AUTOBOT_INTERNAL_API_KEY from slm-secrets.env')
    end = text.index("--- Node-level TLS cert")
    assert start < end, "task order changed -- this guard's slice no longer isolates the registration block"
    return text[start:end]


def test_registration_is_not_gated_on_the_local_marker_file() -> None:
    """The old bug: `when: not vnc_secrets_stat.stat.exists` on the read-back
    check or the registration POST means a failed first attempt is never
    retried, because password generation already created that file before
    either of these tasks runs."""
    block = _registration_block()
    assert "not vnc_secrets_stat.stat.exists" not in block, (
        "the registration block must not gate on the local vnc-secrets.env marker file -- "
        "that file is created before this code runs, so a failed first attempt would never "
        "be retried on any later run (#16299 review)"
    )


def test_registration_checks_the_vault_before_posting() -> None:
    block = _registration_block()
    assert "selectattr('name', 'equalto', 'vnc-password-' + vnc_type)" in block, (
        "the registration POST must be gated on an actual read-back of the secrets vault "
        "(does this name already exist?), not just on having generated a local password"
    )


def test_registration_and_readback_have_retry_logic() -> None:
    block = _registration_block()
    assert block.count("retries:") >= 2, (
        "both the vault read-back and the registration POST need retry/wait logic against a "
        "backend whose secrets-table migration may not have run yet (#16299 review)"
    )
    assert "until:" in block


def test_non_desktop_registration_is_explicitly_refused_not_silently_sent() -> None:
    """vnc_type is hardcoded to "desktop" (co-located, loopback-adjacent)
    everywhere this role is invoked today. The registration POST goes over
    plain HTTP with no TLS -- safe for that loopback case, but would send
    the password in cleartext to a genuinely remote host once "browser" is
    wired. Must fail loudly instead of silently proceeding."""
    text = _text()
    assert "ansible.builtin.fail" in text
    assert "vnc_type != 'desktop'" in text, (
        "a non-desktop vnc_type must be refused explicitly, not silently sent over plaintext "
        "HTTP to a non-co-located host (#16299 review)"
    )


def test_the_password_read_task_has_no_log() -> None:
    """#16299 review: the pre-existing 'Read VNC password from secrets file'
    task's stdout is the plaintext password. It predates this PR but this PR
    added a real consumer of it, making the missing no_log more consequential."""
    text = _text()
    start = text.index("name: Read VNC password from secrets file")
    end = text.index("name: Set VNC password file for user")
    block = text[start:end]
    assert "no_log: true" in block, (
        "'Read VNC password from secrets file' must carry no_log: true -- its stdout is the "
        "plaintext password, and #16299 added a real consumer of it (#16299 review)"
    )
