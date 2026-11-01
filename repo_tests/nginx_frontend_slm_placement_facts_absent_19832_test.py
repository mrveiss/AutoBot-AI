# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM placement is decided without gathered facts, and the SLM trusts its frontend proxies (#19832).

``update-all-nodes.yml`` Play 2 runs ``gather_facts: false``, so ``ansible_facts`` is empty on that
path. Resolves ``roles/frontend/defaults`` and ``roles/slm_manager/defaults`` with plain jinja2
(Ansible's ``bool``/``match``/``extract`` registered as stand-ins) and asserts the verdicts. Limits,
stated: plain jinja2 rather than Ansible's templar; the CA-presence step that settles an
``ambiguous`` verdict is a task, asserted here only as present in ``code_only.yml``.
"""

from __future__ import annotations

import re

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
FRONTEND = ANSIBLE / "roles" / "frontend"
SLM = ANSIBLE / "roles" / "slm_manager"
GROUP_VARS = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8"))
FRONTEND_DEFAULTS = yaml.safe_load((FRONTEND / "defaults" / "main.yml").read_text(encoding="utf-8"))
SLM_DEFAULTS = yaml.safe_load((SLM / "defaults" / "main.yml").read_text(encoding="utf-8"))

# Documentation-range addresses and reserved names only.
THIS_NODE_LAN = "192.0.2.10"
OTHER_NODE = "198.51.100.7"


def _env(hostvars: dict | None = None) -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.Undefined)
    env.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).strip().lower() == "true"
    env.tests["match"] = lambda v, pat: re.match(pat, str(v)) is not None
    hv = hostvars or {}
    env.filters["extract"] = lambda key, mapping, attr: mapping.get(key, {}).get(attr, jinja2.Undefined())
    env.globals["hostvars"] = hv
    return env


def _resolve(defaults: dict, prefix: tuple[str, ...], ctx: dict) -> dict:
    env = _env(ctx.get("hostvars"))
    ctx = dict(ctx)
    pending = {k: v for k, v in defaults.items() if k.startswith(prefix)}
    for _ in range(len(pending) + 1):
        for key, raw in list(pending.items()):
            if not isinstance(raw, str) or "{{" not in raw and "{%" not in raw:
                ctx[key] = raw
                del pending[key]
                continue
            ctx[key] = env.from_string(raw).render(**ctx).strip()
            del pending[key]
    return ctx


def _placement(slm_host, ansible_host, inventory_hostname="node-a", facts=None, connection="ssh"):
    ctx = {"ansible_host": ansible_host, "inventory_hostname": inventory_hostname, "ansible_facts": facts or {}}
    if slm_host is not None:
        ctx["slm_host"] = slm_host
    if connection:
        ctx["ansible_connection"] = connection
    out = _resolve(FRONTEND_DEFAULTS, ("frontend_slm_",), {**GROUP_VARS, **ctx, "hostvars": {}})
    return out["frontend_slm_placement"], out["frontend_slm_backend_remote"]


# Facts ABSENT (Play 2 of update-all-nodes.yml): every row.
@pytest.mark.parametrize(
    ("slm_host", "ansible_host", "inventory_hostname", "verdict"),
    [
        # co-located on a LAN IP: slm_host is this node's own ansible_host
        (THIS_NODE_LAN, THIS_NODE_LAN, "node-a", "local"),
        # co-located on a hostname: slm_host equals the inventory name or the connect name
        ("slm.example.test", "192.0.2.10", "slm.example.test", "local"),
        ("slm.example.test", "slm.example.test", "node-a", "local"),
        # loopback / unset
        ("127.0.0.1", THIS_NODE_LAN, "node-a", "local"),
        (None, THIS_NODE_LAN, "node-a", "local"),
        # truly remote: two different IP literals
        (OTHER_NODE, THIS_NODE_LAN, "node-a", "remote"),
        # cannot tell: a hostname that is not any known identity, a loopback connect address
        ("slm.example.test", THIS_NODE_LAN, "node-a", "ambiguous"),
        (OTHER_NODE, "127.0.0.1", "node-a", "ambiguous"),
        (OTHER_NODE, "node-a.example.test", "node-a", "ambiguous"),
    ],
    ids=[
        "colocated-lan-ip",
        "colocated-hostname-inventory-name",
        "colocated-hostname-connect-name",
        "loopback",
        "unset",
        "remote",
        "unknown-hostname-ambiguous",
        "loopback-connect-ambiguous",
        "hostname-connect-ambiguous",
    ],
)
def test_placement_without_gathered_facts(slm_host, ansible_host, inventory_hostname, verdict) -> None:
    got, remote = _placement(slm_host, ansible_host, inventory_hostname)
    assert got == verdict
    assert remote.strip() == str(verdict == "remote")


def test_local_connection_is_ambiguous_not_remote() -> None:
    assert _placement(OTHER_NODE, THIS_NODE_LAN, connection="local")[0] == "ambiguous"


def test_gathered_facts_make_a_foreign_ip_certainly_remote_and_an_own_ip_local() -> None:
    facts = {"all_ipv4_addresses": ["10.0.0.1", THIS_NODE_LAN]}
    assert _placement(OTHER_NODE, "127.0.0.1", facts=facts)[0] == "remote"
    assert _placement(THIS_NODE_LAN, "node-a.example.test", facts=facts)[0] == "local"


def test_an_explicit_colocation_flag_wins() -> None:
    ctx = {"ansible_host": THIS_NODE_LAN, "inventory_hostname": "n", "ansible_facts": {}}
    ctx.update(slm_host=OTHER_NODE, slm_colocated_frontend=True)
    out = _resolve(FRONTEND_DEFAULTS, ("frontend_slm_",), {**GROUP_VARS, **ctx, "hostvars": {}})
    assert out["frontend_slm_placement"] == "local"


def test_only_a_certain_remote_can_fail_the_update() -> None:
    """The CA assert fires on 'remote' only; 'ambiguous' is settled from the CA's presence, no failure."""
    tasks = yaml.safe_load((FRONTEND / "tasks" / "code_only.yml").read_text(encoding="utf-8"))
    by_name = {t["name"]: t for t in tasks if "name" in t}
    assert_task = next(t for n, t in by_name.items() if "Refuse to proxy to a remote SLM" in n)
    assert "frontend_slm_placement == 'remote'" in assert_task["when"]
    settle = next(t for n, t in by_name.items() if "Settle an ambiguous SLM placement" in n)
    assert "ambiguous" in settle["ansible.builtin.set_fact"]["frontend_slm_backend_remote"]
    assert "ansible_facts" not in " ".join(map(str, assert_task["when"]))


def _proxies(hostvars: dict, groups: dict, **extra) -> list[str]:
    ctx = {**GROUP_VARS, "groups": groups, "hostvars": hostvars, **extra}
    out = _resolve(SLM_DEFAULTS, ("slm_trusted_proxies",), ctx)
    return out["slm_trusted_proxies"].split(",")


def test_trusted_proxies_cover_loopback_slm_and_every_frontend_node() -> None:
    frontend_a, frontend_b = "203.0.113.5", "203.0.113.6"
    got = _proxies(
        {"fe-a": {"ansible_host": frontend_a}, "fe-b": {"ansible_host": frontend_b}, "fe-c": {}},
        {"frontend": ["fe-a", "fe-b", "fe-c"]},
        slm_host=OTHER_NODE,
        ansible_host=THIS_NODE_LAN,
    )
    assert got[:2] == ["127.0.0.1", "::1"]
    assert {OTHER_NODE, THIS_NODE_LAN, frontend_a, frontend_b} <= set(got)
    assert "" not in got
    assert len(got) == len(set(got))


def test_trusted_proxies_without_a_frontend_group_or_hosts_still_include_loopback_and_slm() -> None:
    got = _proxies({}, {}, slm_host=OTHER_NODE)
    assert got == ["127.0.0.1", "::1", OTHER_NODE]


def test_the_backend_unit_sets_the_variable_from_the_role_default() -> None:
    unit = (SLM / "templates" / "autobot-slm-backend.service.j2").read_text(encoding="utf-8")
    assert 'Environment="SLM_TRUSTED_PROXIES={{ slm_trusted_proxies }}"' in unit
    env_file_line = unit.index("EnvironmentFile=-{{ slm_credentials_dir }}")
    assert unit.index("SLM_TRUSTED_PROXIES") < env_file_line
