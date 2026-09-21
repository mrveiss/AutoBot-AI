# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The nginx role provisions the TLS keypair BEFORE apt installs nginx (#17172).

#16020 moved the role's explicit `systemd: state=started` after the keypair task,
because every AutoBot vhost carries `ssl_certificate
/etc/autobot/certs/server-cert.pem` and `nginx -t` runs in `ExecStartPre` -- a
missing cert is a unit that can never come up, not a degraded start.

**That reorder was not sufficient.** `apt: state=present` runs the package's own
postinst, which starts nginx itself, and that start is not ours to reorder. On a
re-provision of a node whose `sites-enabled` vhost already references the cert,
a missing keypair makes the postinst's `nginx -t` fail and the package fail to
configure:

    apt-get ... install 'nginx=1.24.0-2ubuntu7.18' failed:
    E: Sub-process /usr/bin/dpkg returned an error code (1)

A fresh host never hits it -- stock nginx config references no certificate -- so
this passes on most nodes and fails only on a re-provisioned one, which is the
shape that makes it survive a green run.

CI does not execute Ansible, so ordering is not otherwise observable before a
fleet node hits it. This asserts the relative order of two tasks in one file;
it deliberately does not try to prove the failure, which needs a host.

Mutation check: move the keypair include back below the apt task and this goes
red naming both line numbers.
"""

from __future__ import annotations

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_ROLE_TASKS = (
    repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "nginx" / "tasks" / "main.yml"
)
_CERT_INCLUDE = "_shared/tasks/ensure_node_tls_cert.yml"


def _tasks() -> list[dict]:
    assert _ROLE_TASKS.is_file(), f"{_ROLE_TASKS} is missing; move this guard with the role."
    loaded = yaml.safe_load(_ROLE_TASKS.read_text(encoding="utf-8"))
    assert isinstance(loaded, list) and loaded, "expected a non-empty Ansible task list"
    return [t for t in loaded if isinstance(t, dict)]


def _index_of(pred, what: str) -> int:
    tasks = _tasks()
    hits = [i for i, t in enumerate(tasks) if pred(t)]
    assert hits, (
        f"no task in roles/nginx/tasks/main.yml {what}. This guard is now watching nothing -- "
        "if the role was restructured, re-point it rather than deleting it."
    )
    return hits[0]


def test_the_keypair_is_provisioned_before_apt_installs_nginx() -> None:
    """apt's postinst starts nginx, so the cert must exist before the install, not just before us."""
    cert_at = _index_of(
        lambda t: _CERT_INCLUDE in str(t.get("ansible.builtin.include_tasks", "")),
        f"includes {_CERT_INCLUDE}",
    )
    install_at = _index_of(
        lambda t: t.get("ansible.builtin.apt", {}).get("name") == "nginx",
        "installs the nginx package",
    )
    assert cert_at < install_at, (
        "roles/nginx/tasks/main.yml installs nginx (task index "
        f"{install_at}) BEFORE provisioning the TLS keypair (task index {cert_at}). "
        "apt's postinst starts nginx during that install, and on a node whose vhost already "
        "references /etc/autobot/certs/server-cert.pem the start fails `nginx -t` and dpkg "
        "returns 1 (#17172). The keypair include must come first."
    )


def test_the_explicit_start_still_follows_the_keypair() -> None:
    """#16020's original ordering must survive this reorder, not be traded for it."""
    cert_at = _index_of(
        lambda t: _CERT_INCLUDE in str(t.get("ansible.builtin.include_tasks", "")),
        f"includes {_CERT_INCLUDE}",
    )
    start_at = _index_of(
        lambda t: str(t.get("ansible.builtin.systemd", {}).get("state", "")) == "started",
        "starts the nginx service",
    )
    assert cert_at < start_at, (
        f"the keypair task (index {cert_at}) no longer precedes the explicit service start "
        f"(index {start_at}). That is #16020's invariant and it still holds independently of "
        "#17172's apt-postinst one."
    )
