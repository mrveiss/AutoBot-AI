# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM backend port has ONE ansible name and ONE literal (#20600).

``slm_backend_port`` lives only in ``inventory/group_vars/all.yml``; the retired ``slm_port``
(which carried a second ``8000`` in the inventory and a ``default(8000)`` in two readers) is gone.
``enroll-local.yml`` runs against localhost without the inventory's group_vars, so it loads the
file itself.

Limits, stated: plain jinja2 rather than Ansible's templar; ``--syntax-check`` of the playbooks is
a separate manual step and not part of this test.
"""

from __future__ import annotations

import re

import jinja2
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
GROUP_VARS_ALL = ANSIBLE / "inventory" / "group_vars" / "all.yml"
_SUFFIXES = {".yml", ".yaml", ".j2"}

REACH_ANSIBLE_FILES = declare(
    "ansible-files-scanned-for-slm-port",
    discover=lambda root: [
        p.relative_to(root).as_posix()
        for p in (root / "autobot-slm-backend" / "ansible").rglob("*")
        if p.suffix in _SUFFIXES and p.is_file()
    ],
    roots=("autobot-slm-backend/ansible",),
    floor=442,  # mid-window: population 462 when measured, growth 40
    growth=40,
    skips=0,
    what="ansible YAML and template files scanned for the retired slm_port name",
)


def _ansible_texts():
    for path in ANSIBLE.rglob("*"):
        if path.suffix in _SUFFIXES and path.is_file():
            yield path, path.read_text(encoding="utf-8", errors="replace")


def test_slm_port_is_gone() -> None:
    for path, text in _ansible_texts():
        assert not re.search(r"\bslm_port\b", text), f"{path.relative_to(ANSIBLE)} still names slm_port"


def test_slm_backend_port_is_assigned_in_exactly_one_file() -> None:
    assigned = [
        path.relative_to(ANSIBLE).as_posix()
        for path, text in _ansible_texts()
        if re.search(r"^\s*slm_backend_port\s*:", text, re.MULTILINE)
    ]
    assert assigned == ["inventory/group_vars/all.yml"], assigned


def test_enroll_local_resolves_the_port_without_the_inventory() -> None:
    play = yaml.safe_load((ANSIBLE / "playbooks" / "enroll-local.yml").read_text(encoding="utf-8"))[0]
    assert "../inventory/group_vars/all.yml" in play["vars_files"]
    port = yaml.safe_load(GROUP_VARS_ALL.read_text(encoding="utf-8"))["slm_backend_port"]
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.globals["lookup"] = lambda kind, name: ""
    url = env.from_string(play["vars"]["slm_admin_url"]).render(slm_backend_port=port)
    assert url == f"http://127.0.0.1:{port}"
