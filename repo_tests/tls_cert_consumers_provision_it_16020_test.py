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

**The first version of this control had the defect it was written to catch.**
It classified a role as provisioning the shared keypair if the text `openssl
req` appeared anywhere in it. `roles/vnc` runs openssl twice -- once for the
shared pair and once for the dedicated VNC pair (#13060) at `vnc-cert.pem` in
the same directory -- so the role counted as a provisioner on the strength of a
call that creates a different file. The fix landed in `roles/nginx` and
`roles/redis`, both of which were already correct, and missed `roles/vnc`,
which owns nginx on a VNC node. This file was green throughout; the node was
down for two days and auto-remediation gave up six times.

So the classifier now resolves the `-out` path through the role's own defaults
and compares it to the shared certificate, per task rather than per file. That
also surfaced `roles/frontend` and `roles/slm_manager`, which the bare match
had been crediting for the same reason. Both do provision it -- through
variables -- and both now verify as such rather than by coincidence.

Three roles still carry their own openssl block for this keypair instead of
including the shared task. Consolidating them is the point of the shared task
and is tracked separately; this control only requires that the guarantee is
*held*, not yet that it is held in one place.
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

#: An `openssl req` counts as provisioning THIS keypair only when it writes to
#: it. The first version of this guard matched `openssl req` anywhere in the
#: role, and that is what let #16020 through a second time: `roles/vnc` runs
#: openssl twice -- once for the shared pair, once for the dedicated VNC pair
#: (#13060) that Xvnc and websockify read from `{{ vnc_tls_cert }}`. Remove the
#: shared block and the dedicated one still matched, so the role went on
#: counting as a provisioner of a keypair it no longer created, while nginx on
#: that node could not start. The docstring already carved the dedicated pair
#: out of the CONSUMER side; the provisioner side needed the same carve-out.
_GENERATES = re.compile(r"openssl\s+req")
_SHARED_CERT = f"{_SHARED_CERT_DIR}/server-cert.pem"

# `{{ frontend_tls_cert }}` contains spaces, so a bare `\S+` captures `{{` and
# the path is never resolved -- the role then reads as not provisioning what it
# plainly provisions. Match a Jinja expression before falling back to a token.
_OUT = re.compile(r"-out\s+(\{\{[^}]*\}\}|\S+)")
_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SCALAR = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*[\"']?([^\"'#\n]+?)[\"']?\s*$")
_TASK_START = re.compile(r"^\s*-\s+name:", re.MULTILINE)


def _role_scalars(role: pathlib.Path) -> dict[str, str]:
    """Top-level scalar vars from the role's defaults and vars.

    Enough to resolve `{{ slm_tls_cert }}` -> `{{ slm_certs_dir }}/server-cert.pem`
    -> the shared path. Not a Jinja engine, and it does not need to be: every
    cert path in these roles is a plain chain of role-level scalars.
    """
    values: dict[str, str] = {}
    for group in ("defaults", "vars"):
        path = role / group / "main.yml"
        if not path.is_file():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            match = _SCALAR.match(line)
            if match:
                values[match.group(1)] = match.group(2)
    return values


def _resolve(value: str, values: dict[str, str]) -> str:
    for _ in range(5):
        expanded = _VAR.sub(lambda m: values.get(m.group(1), m.group(0)), value)
        if expanded == value:
            break
        value = expanded
    return value


def _provisions_shared_keypair(text: str, values: dict[str, str]) -> bool:
    """Includes the shared task, or generates the shared pair itself.

    Split per task, because a role may run openssl for more than one keypair
    and only some of them are this one. `roles/vnc` is exactly that: the
    dedicated VNC pair (#13060) resolves to `vnc-cert.pem` in the same
    directory, which is why matching the DIRECTORY, or matching bare
    `openssl req`, both answer the wrong question.
    """
    if _SHARED_TASK in text:
        return True
    for block in _TASK_START.split(text):
        if not _GENERATES.search(block):
            continue
        if any(_resolve(target, values) == _SHARED_CERT for target in _OUT.findall(block)):
            return True
    return False


def _role_files(role: pathlib.Path) -> list[pathlib.Path]:
    return [p for p in role.rglob("*") if p.is_file()]


def _roles() -> list[pathlib.Path]:
    return sorted(p for p in _ROLES.iterdir() if p.is_dir() and not p.name.startswith("_"))


def _classify() -> tuple[set[str], set[str]]:
    """(roles consuming the shared keypair, roles that ensure it exists)."""
    consumers: set[str] = set()
    provisioners: set[str] = set()
    for role in _roles():
        scalars = _role_scalars(role)
        for path in _role_files(role):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if _SHARED_CERT_DIR in text:
                consumers.add(role.name)
            if _provisions_shared_keypair(text, scalars):
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


def test_an_unrelated_openssl_call_does_not_count_as_provisioning_this_keypair():
    """The known positive for the classifier, taken from the role that broke it.

    `roles/vnc` generates a SECOND keypair at `{{ vnc_tls_cert }}` for Xvnc and
    websockify (#13060). That call is real, correct, and about a different file.
    Asserted against the role's own text with the shared include removed, so it
    fails if the classifier ever goes back to matching bare `openssl req` --
    which is the state in which #16020's node was down and this file was green.
    """
    vnc = (_ROLES / "vnc" / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert _SHARED_TASK in vnc, "the vnc role must include the shared ensure-task"
    assert _GENERATES.search(vnc), "expected the dedicated VNC keypair's openssl call to still be here"

    without_include = vnc.replace(_SHARED_TASK, "")
    assert not _provisions_shared_keypair(without_include, _role_scalars(_ROLES / "vnc")), (
        "the dedicated VNC keypair alone makes the role read as a provisioner of "
        "the SHARED keypair -- the exact blind spot that kept this guard green "
        "while nginx on a VNC node could not start (#16020)"
    )


def test_a_role_that_writes_the_shared_pair_itself_still_counts():
    """The other direction: hand-rolled generation of THIS pair is provisioning.

    `roles/backend` writes `/etc/autobot/certs/server-cert.pem` with its own
    openssl block rather than including the shared task. That is duplication
    worth removing, but it is not the defect this guard is for -- and a
    classifier that called it a gap would be wrong in the opposite direction.
    """
    backend = (_ROLES / "backend" / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert _provisions_shared_keypair(backend, _role_scalars(_ROLES / "backend")), (
        "roles/backend generates the shared keypair at the shared path and must "
        "classify as a provisioner"
    )
    assert _SHARED_TASK not in backend, (
        "roles/backend now includes the shared task -- delete this assertion and "
        "the duplication note in the docstring, the consolidation is complete"
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
