# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No playbook may manage a Redis unit by a name that disagrees with the SSOT (#14516).

Live failure, during a co-located role deploy on the manager::

    TASK [Verify Redis service]
    fatal: Could not find the requested service redis-server: host

The platform installs redis-stack, whose unit is ``redis-stack-server``. The
role's own handlers and its ``dpkg -l redis-stack-server`` check had that right
all along; three playbooks carried the literal ``redis-server`` -- the plain
Debian package, never installed here -- and could not succeed on a correct host.

The expected name is READ from ``group_vars/all.yml`` rather than repeated here.
A test asserting the literal would be a fourth copy of the thing that drifted.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parent.parent / "ansible"
_GROUP_VARS = _ANSIBLE / "inventory" / "group_vars" / "all.yml"

# Modules that take a systemd/service unit name.
_SERVICE_MODULES = ("ansible.builtin.systemd", "ansible.builtin.service", "systemd", "service")

# Unit names that mean "the Redis server itself". Matched exactly rather than by
# substring: a first draft of this rule used `"redis" in unit`, which flagged
# `redisinsight` -- a different service entirely -- and would have failed the
# build over a correct playbook. `redis_exporter` is the same trap.
_REDIS_SERVER_UNITS = frozenset({"redis-server", "redis", "redis-stack-server"})


def _is_redis_server_unit(unit: str) -> bool:
    """True only for a LITERAL naming the Redis server.

    Templated names are excluded deliberately: a `{{ var }}` cannot be a wrong
    literal, and including them made this scan match every templated service in
    the tree (82 tasks, nearly all unrelated) -- which would let the
    "did the scan find anything" check pass on services that have nothing to do
    with Redis.
    """
    return unit in _REDIS_SERVER_UNITS


def _canonical_name() -> str:
    data = yaml.safe_load(_GROUP_VARS.read_text(encoding="utf-8"))
    name = (data or {}).get("redis_service_name")
    assert name, "redis_service_name is not defined in group_vars/all.yml — the SSOT this rule reads is gone"
    return name


def _service_task_names():
    """(file, unit) for every task managing a Redis-looking systemd unit."""
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            docs = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue

        stack = [docs]
        while stack:
            item = stack.pop()
            if isinstance(item, list):
                stack.extend(item)
                continue
            if not isinstance(item, dict):
                continue
            stack.extend(v for v in item.values() if isinstance(v, (list, dict)))
            for module in _SERVICE_MODULES:
                spec = item.get(module)
                if not isinstance(spec, dict):
                    continue
                unit = str(spec.get("name", ""))
                if _is_redis_server_unit(unit):
                    yield path.relative_to(_ANSIBLE), unit


def test_the_sources_this_rule_reads_exist():
    """An empty scan reads exactly like a clean one.

    Asserting on the CANONICAL name specifically: a scan that found only
    templated or unrelated tasks would satisfy a bare non-empty check while
    seeing no real Redis unit at all.
    """
    canonical = _canonical_name()
    found = list(_service_task_names())

    assert found, "no Redis service tasks found at all — this rule is pinned to the wrong shape"
    assert any(unit == canonical for _, unit in found), (
        f"the scan found Redis tasks but none naming {canonical!r} — it is no longer reading real unit names"
    )


def test_no_playbook_manages_a_redis_unit_by_a_conflicting_literal():
    """The #14516 regression.

    A templated name is fine whatever it resolves to; a hardcoded one that is
    not the canonical unit is the defect.
    """
    canonical = _canonical_name()

    offenders = [
        f"{path} manages {unit!r}"
        for path, unit in _service_task_names()
        if "{{" not in unit and unit != canonical
    ]

    assert not offenders, (
        f"playbook(s) manage a Redis unit that is not {canonical!r}, so the task fails with "
        f"'Could not find the requested service' on a correctly installed host (#14516): " + "; ".join(offenders)
    )


def test_the_role_handler_and_the_ssot_agree():
    """The role was already right; pin the two together so neither drifts alone."""
    handlers = (_ANSIBLE / "roles" / "redis" / "handlers" / "main.yml").read_text(encoding="utf-8")

    assert re.search(rf"name:\s*{re.escape(_canonical_name())}\b", handlers), (
        "the redis role's handler no longer names the canonical unit"
    )
