# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`_shared/tasks/generate_self_signed_cert.yml` declares its own `become` (#16020).

Both of its tasks write to root-owned paths -- `/etc/autobot/certs` is `0755
root:root` -- so privilege is a property of THIS file, not of whoever includes
it. It did not always say so, and the omission was invisible for as long as
every caller happened to supply privilege from above.

Every original consumer reached it from a play with play-level `become: true`
(`playbooks/rotate-certs.yml:33,71,148,214`). The #16020 consolidation then
routed a second path here -- `_shared/tasks/ensure_node_tls_cert.yml`, included
from `playbooks/update-all-nodes.yml` Plays 1/2/2b, which set `become` PER TASK
instead. **A nested `include_tasks` does not inherit a per-task `become`**, so
on that path the wrapper created the directory as root and then `openssl` ran
unprivileged and could not write into it:

    fatal: FAILED! => {"changed": true, "cmd": ["openssl", "req", "-x509", ...
      "-keyout", "/etc/autobot/certs/server-key.pem", ...]}

`update-all-nodes.yml` is the playbook a GUI self-update runs, so the break
appeared only on code-sync and never during provisioning -- which is why four
roles could include this file and look fine.

CI does not execute Ansible, so nothing else can catch this. The assertion is
deliberately about the file DECLARING privilege rather than about any caller
supplying it: a guard that checked callers would pass again the moment a fifth
caller appeared, which is the shape of the original defect.

Mutation check: delete either `become: true` from the task file and this goes
red naming that task.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_CERT_TASKS = (
    repo_root() / "autobot-slm-backend" / "ansible" / "_shared" / "tasks" / "generate_self_signed_cert.yml"
)


def _tasks() -> list[dict]:
    assert _CERT_TASKS.is_file(), (
        f"{_CERT_TASKS.relative_to(repo_root())} is missing. It is included by "
        "_shared/tasks/ensure_node_tls_cert.yml and by playbooks/rotate-certs.yml; if it moved, "
        "move this guard with it rather than deleting the guard."
    )
    loaded = yaml.safe_load(_CERT_TASKS.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, "expected a non-empty Ansible task list"
    return [t for t in loaded if isinstance(t, dict)]


def test_every_task_declares_become() -> None:
    """Both tasks write under /etc/autobot/certs, so both must claim privilege."""
    missing = [str(t.get("name", "<unnamed>")) for t in _tasks() if t.get("become") is not True]
    assert not missing, (
        "these tasks in generate_self_signed_cert.yml do not set `become: true`, so they run with "
        "whatever privilege the caller happens to supply -- which is exactly how the fleet update "
        "broke (#16020): a per-task `become` in update-all-nodes.yml is NOT inherited through "
        "include_tasks, and openssl could not write into root-owned /etc/autobot/certs:\n  "
        + "\n  ".join(missing)
    )


def test_the_generation_task_is_still_the_one_writing_the_keypair() -> None:
    """Pin what the guard above is protecting, so a rename cannot hollow it out.

    Without this, renaming or re-shaping the openssl task would leave
    ``test_every_task_declares_become`` passing over whatever remained.
    """
    cmds = [str(t.get("ansible.builtin.command", {}).get("cmd", "")) for t in _tasks()]
    joined = " ".join(cmds)
    assert "openssl req" in joined, (
        "no task in generate_self_signed_cert.yml runs `openssl req` any more. If keypair "
        "generation moved, this guard is now watching nothing -- point it at the new writer."
    )
    assert "_key_file" in joined and "_cert_file" in joined, (
        "the openssl task no longer writes {{ _key_file }} / {{ _cert_file }}; the become "
        "assertion above may no longer be covering the privileged write."
    )
