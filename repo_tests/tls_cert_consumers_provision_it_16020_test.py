# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every role that reads the shared node keypair also ensures it exists (#16020).

An operator's VNC node could not start nginx for ten hours:

    [emerg] cannot load certificate "/etc/autobot/certs/server-cert.pem":
            BIO_new_file() failed (SSL: ...No such file or directory)
    nginx: configuration file /etc/nginx/nginx.conf test failed

`nginx -t` runs in ExecStartPre, so a missing cert is not a degraded start --
the unit can never come up, and every restart re-failed identically.

The census at the time: **five roles consumed `/etc/autobot/certs/`, four
provisioned it.** `redis` consumed without provisioning; `nginx` started a
daemon whose config references it without checking. The invariant was held by
each consumer separately remembering to, and the `vnc` role's own comment
records that as the design -- "Kept here so a vnc-only node still ends up with
one." That holds until someone adds a consumer that does not remember.

A duplicated guarantee fails silently the first time it is not duplicated, and
it fails on whichever node has the unlucky role set. This test is the control
that makes the invariant readable by a sweep rather than by four comments.
"""

from __future__ import annotations

import pathlib
import re

from repo_tests._paths import repo_root

_ROLES = repo_root() / "autobot-slm-backend" / "ansible" / "roles"

#: The shared keypair. Roles reading anything under this directory depend on it
#: existing; roles generating their own pair elsewhere (VNC's dedicated keypair,
#: #13060) are a different subject and are not matched by this path.
_SHARED_CERT_DIR = "/etc/autobot/certs"

_SHARED_TASK = "ensure_node_tls_cert.yml"
_GENERATES = re.compile(r"openssl\s+req")


def _role_files(role: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in role.rglob("*") if p.is_file()]


def _roles() -> list[pathlib.Path]:
    return sorted(p for p in _ROLES.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _classify() -> tuple[set[str], set[str]]:
    """(roles consuming the shared keypair, roles that ensure it exists)."""
    consumers: set[str] = set()
    provisioners: set[str] = set()
    for role in _roles():
        for path in _role_files(role):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _SHARED_CERT_DIR in text:
                consumers.add(role.name)
            if _SHARED_TASK in text or _GENERATES.search(text):
                provisioners.add(role.name)
    return consumers, provisioners


def test_every_shared_cert_consumer_ensures_the_cert_exists():
    """The defect, as a set comparison rather than a count.

    Two implementations can agree on how many roles touch TLS and disagree on
    which -- so this asserts the difference is empty, and names the roles when
    it is not.
    """
    consumers, provisioners = _classify()
    assert len(consumers) >= 4, (
        f"only {len(consumers)} roles found reading {_SHARED_CERT_DIR} -- the sweep "
        "collapsed and would report 'no gap' for the same reason a fixed tree does"
    )
    gap = sorted(consumers - provisioners)
    assert not gap, (
        f"these roles read {_SHARED_CERT_DIR} without ensuring it exists: {gap}. "
        f"Include ../../../_shared/tasks/{_SHARED_TASK} before the consuming task. "
        "A node whose role set happens to exclude a provisioner gets a service "
        "that can never start (#16020)."
    )


def test_nginx_ensures_the_cert_before_starting_the_service():
    """Ordering, not merely presence -- this is the instance that broke.

    The nginx role does three things: refresh apt, install, start. Starting was
    the only one that could fail for a reason outside itself, and it did.
    """
    tasks = (_ROLES / "nginx" / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert _SHARED_TASK in tasks, "the nginx role does not ensure the keypair it needs"
    assert tasks.index(_SHARED_TASK) < tasks.index("state: started"), (
        "the nginx role starts nginx before ensuring the certificate its config "
        "references exists; `nginx -t` runs in ExecStartPre, so the unit cannot start"
    )


def test_the_shared_task_delegates_rather_than_re_implementing_openssl():
    """Generation was already extracted once (#12181) and had a single consumer.

    A fifth hand-written openssl block would be the duplication this fixes,
    reintroduced by the fix.
    """
    shared = repo_root() / "autobot-slm-backend" / "ansible" / "_shared" / "tasks" / _SHARED_TASK
    text = shared.read_text(encoding="utf-8")
    assert "generate_self_signed_cert.yml" in text
    assert not _GENERATES.search(text), (
        "the shared ensure-task re-implements openssl instead of including the "
        "already-extracted generator"
    )
