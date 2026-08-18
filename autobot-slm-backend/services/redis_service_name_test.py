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


def _unparseable_files() -> list[str]:
    """Files the scan could not read at all.

    Review of #14516: the first version used `yaml.safe_load`, which raises
    `ComposerError` on a multi-document file -- `deploy-hybrid-docker.yml` has
    six `---` markers -- and the exception was swallowed, so the whole file was
    skipped in silence. A future `systemd: name: redis-server` in such a file
    would have passed this guard while the suite reported green. A guard that
    fails open is worse than no guard, so unreadable files are now surfaced.
    """
    broken = []
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (yaml.YAMLError, UnicodeDecodeError):
            broken.append(str(path.relative_to(_ANSIBLE)))
    return broken


def _service_task_names():
    """(file, unit) for every task managing a Redis-looking systemd unit."""
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue

        stack = list(documents)
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
    assert any(
        unit == canonical for _, unit in found
    ), f"the scan found Redis tasks but none naming {canonical!r} — it is no longer reading real unit names"


def test_no_playbook_manages_a_redis_unit_by_a_conflicting_literal():
    """The #14516 regression.

    A templated name is fine whatever it resolves to; a hardcoded one that is
    not the canonical unit is the defect.
    """
    canonical = _canonical_name()

    offenders = [
        f"{path} manages {unit!r}" for path, unit in _service_task_names() if "{{" not in unit and unit != canonical
    ]

    assert not offenders, (
        f"playbook(s) manage a Redis unit that is not {canonical!r}, so the task fails with "
        f"'Could not find the requested service' on a correctly installed host (#14516): " + "; ".join(offenders)
    )


def test_the_role_handler_reads_the_definition():
    """The role was already correct, but by coincidence rather than by wiring.

    It carried its own literal, so it agreed with group_vars only as long as
    nobody edited either. It now reads the variable (with the same default), so
    a rename moves both together.
    """
    handlers = (_ANSIBLE / "roles" / "redis" / "handlers" / "main.yml").read_text(encoding="utf-8")

    assert "redis_service_name" in handlers, "the redis role's handler no longer reads the canonical definition"
    assert re.search(rf"default\(\s*'{re.escape(_canonical_name())}'\s*\)", handlers), (
        "the handler's fallback no longer matches the canonical unit name"
    )


def test_every_playbook_is_actually_readable():
    """The scan must not skip files in silence.

    `deploy-hybrid-docker.yml` (six YAML documents) was invisible to the first
    version of this rule. If a file genuinely cannot be parsed, that is worth
    knowing rather than quietly narrowing the guard's reach.
    """
    broken = _unparseable_files()

    assert not broken, f"playbook(s) the Redis guard cannot read, so they are never checked: {broken}"


def _play_level_definitions():
    """(file, value) for every play-level `vars:` that redefines the name."""
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except (yaml.YAMLError, UnicodeDecodeError):
            continue
        for document in documents:
            for play in document if isinstance(document, list) else [document]:
                if not isinstance(play, dict):
                    continue
                value = (play.get("vars") or {}).get("redis_service_name") if isinstance(play.get("vars"), dict) else None
                if isinstance(value, str) and "{{" not in value:
                    yield path.relative_to(_ANSIBLE), value


def test_no_play_redefines_the_name_to_something_else():
    """A play-level `vars:` outranks group_vars, so it is a second definition.

    `configure-redis-service-management.yml` sets it locally and currently
    agrees, so nothing is broken today -- but it would keep the old value
    through a rename while every templated reference moved, and the literal
    scan cannot see it because the references are templated. Pinned so the two
    cannot diverge silently.
    """
    canonical = _canonical_name()

    offenders = [f"{path} sets {value!r}" for path, value in _play_level_definitions() if value != canonical]

    assert not offenders, (
        f"play-level redis_service_name disagrees with group_vars ({canonical!r}): " + "; ".join(offenders)
    )
