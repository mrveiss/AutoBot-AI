# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""An inventory must not carry shell placeholders Ansible never expands (#14528).

`ansible/inventory.yml` and `inventory/hosts.yml` contained:

    ansible_host: ${AUTOBOT_BACKEND_HOST}

Ansible does not substitute `${VAR}` in YAML inventory, and nothing in the repo
expanded it. Every `ansible_host` on those paths was the literal string
`${AUTOBOT_...}`, so `api/tls.py` — which runs `ansible-playbook -i inventory.yml`
— could not reach any host. Four other playbooks document that same `-i` in their
usage headers.

It came from #3226, which replaced hardcoded `172.16.168.x` addresses with
placeholders and never added an expansion step, and went unnoticed because the
files still parse, still list plausible hosts, and only fail when actually used.

`inventory/slm-nodes.yml` had the correct idiom all along:

    ansible_host: "{{ lookup('env', 'AUTOBOT_BACKEND_HOST') | default('127.0.0.1', true) }}"

The default matters beyond syntax: the fleet topology is per-install — one
operator runs ten distributed nodes, another puts every role on a single host —
so an unset variable must degrade to localhost rather than to a broken name.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parent.parent / "ansible"

#: `${VAR}` / `$VAR` — shell syntax Ansible leaves untouched in YAML.
_SHELL_PLACEHOLDER = re.compile(r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")


def _inventory_files():
    """Tracked inventory YAML: the top-level file plus inventory/*.yml."""
    top = _ANSIBLE / "inventory.yml"
    if top.is_file():
        yield top
    inv_dir = _ANSIBLE / "inventory"
    if inv_dir.is_dir():
        for path in sorted(inv_dir.glob("*.yml")):
            yield path


def _host_values(path: Path):
    """(host, value) for every `ansible_host` anywhere in the file."""
    stack = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d is not None]
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key == "ansible_host":
                yield path.name, value
            elif isinstance(value, (dict, list)):
                stack.append(value)


def test_the_scan_finds_inventories_and_hosts():
    """An empty scan reads exactly like a clean one."""
    files = list(_inventory_files())

    assert files, "no inventory files found — this rule is pinned to the wrong path"

    hosts = [v for f in files for v in _host_values(f)]

    assert hosts, f"no ansible_host entries parsed from {[f.name for f in files]}"


def test_no_ansible_host_carries_a_shell_placeholder():
    """The #14528 defect.

    A `${VAR}` here is not a variable — it is a hostname that happens to look
    like one, and the failure only appears when someone actually runs against
    the file.
    """
    offenders = [
        f"{name}: {value!r}"
        for path in _inventory_files()
        for name, value in _host_values(path)
        if isinstance(value, str) and "{{" not in value and _SHELL_PLACEHOLDER.search(value)
    ]

    assert not offenders, (
        "ansible_host carries shell syntax Ansible does not expand — use "
        "\"{{ lookup('env', 'VAR') | default('127.0.0.1', true) }}\" instead (#14528): " + "; ".join(offenders)
    )


def test_env_backed_hosts_degrade_to_localhost():
    """Topology is per-install, so an unset variable must not break the host.

    One operator deploys ten distributed nodes; another co-locates every role on
    a single machine. An `ansible_host` that resolves to empty on the second
    shape is the same defect in a different costume.
    """
    missing_default = [
        f"{name}: {value!r}"
        for path in _inventory_files()
        for name, value in _host_values(path)
        if isinstance(value, str) and "lookup('env'" in value and "default(" not in value
    ]

    assert not missing_default, (
        "env-backed ansible_host without a default — an all-in-one install would "
        "resolve it to nothing (#14528): " + "; ".join(missing_default)
    )


def test_the_live_inventory_does_not_default_to_localhost():
    """`ansible/inventory.yml` is the sole inventory for POST /api/tls/enable.

    That endpoint writes `.env`, opens firewall ports and restarts services. A
    `default('127.0.0.1', true)` here would point all of that at the SLM manager
    whenever an AUTOBOT_*_HOST is unset on a distributed install — and return
    200. A wrong host is worse than no host.

    `inventory/slm-nodes.yml` does default to localhost, and that is fine: it
    documents itself as a legacy static fallback behind the registry-driven
    inventory. This rule is deliberately scoped to the primary file.
    """
    live = _ANSIBLE / "inventory.yml"
    if not live.is_file():
        pytest.skip("ansible/inventory.yml is gone; nothing to constrain")

    offenders = [
        f"{name}: {value!r}"
        for name, value in _host_values(live)
        if isinstance(value, str) and "127.0.0.1" in value
    ]

    assert not offenders, (
        "ansible/inventory.yml defaults a host to localhost — an unset env var would "
        "silently target the SLM manager for a mutating TLS run (#14528): " + "; ".join(offenders)
    )


def test_the_tls_playbook_asserts_its_hosts_resolved():
    """The counterpart: empty is only safe because the play refuses to proceed."""
    playbook = _ANSIBLE / "enable-tls.yml"
    text = playbook.read_text(encoding="utf-8")

    assert "Verify inventory hosts resolved" in text, (
        "enable-tls.yml no longer asserts that ansible_host resolved; with the empty default "
        "it would run against an unresolved host instead of failing (#14528)"
    )
