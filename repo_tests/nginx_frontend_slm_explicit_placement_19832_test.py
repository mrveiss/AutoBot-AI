# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SLM placement is one explicit variable, and the SLM trusts its frontend proxies (#19832).

``update-all-nodes.yml`` Play 2 runs ``gather_facts: false``, so ``ansible_facts`` is empty on that
path. Resolves ``roles/frontend/defaults`` and ``roles/slm_manager/defaults`` with plain jinja2
(Ansible's ``bool``/``match``/``extract`` registered as stand-ins) and asserts both values of
``frontend_slm_remote`` with facts absent. Limits, stated: plain jinja2 rather than Ansible's
templar; the CA assert is a task, checked here by its ``when`` and message, not executed.
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
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
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
            try:
                ctx[key] = env.from_string(raw).render(**ctx).strip()
            except jinja2.UndefinedError:
                continue  # a dependency is not resolved yet; retry after the others
            del pending[key]
    assert not pending, f"unresolved defaults (a dependency is missing from the context): {sorted(pending)}"
    return ctx


def _remote(**ctx) -> dict:
    # An inventory value outranks the role default, so it replaces the default here.
    defaults = {**FRONTEND_DEFAULTS, **{k: v for k, v in ctx.items() if k.startswith("frontend_slm_")}}
    return _resolve(defaults, ("frontend_slm_", "frontend_tls_cert_dir"), {**GROUP_VARS, **ctx, "hostvars": {}})


# Facts ABSENT throughout (Play 2 of update-all-nodes.yml): ansible_facts is empty, and no address,
# hostname or connection type changes the verdict. Only frontend_slm_remote does.
@pytest.mark.parametrize(
    ("ansible_host", "slm_host"),
    [
        (THIS_NODE_LAN, THIS_NODE_LAN),
        (THIS_NODE_LAN, OTHER_NODE),
        ("127.0.0.1", OTHER_NODE),
        ("node-a.example.test", "slm.example.test"),
        (THIS_NODE_LAN, None),
    ],
    ids=["same-address", "different-address", "loopback-connect", "hostnames", "slm-host-unset"],
)
def test_unset_means_loopback_whatever_the_addresses_say(ansible_host, slm_host) -> None:
    ctx = {"ansible_host": ansible_host, "inventory_hostname": "node-a", "ansible_facts": {}}
    if slm_host is not None:
        ctx["slm_host"] = slm_host
    out = _remote(**ctx)
    assert FRONTEND_DEFAULTS["frontend_slm_remote"] is False
    assert str(out["frontend_slm_backend_remote"]) == "False"
    assert out["frontend_slm_backend_protocol"] == "http"
    assert out["frontend_slm_backend_host"] == GROUP_VARS["slm_loopback_ipv4"]
    assert out["frontend_slm_upstream_prefix"] == "/api/"


@pytest.mark.parametrize("ansible_host", [THIS_NODE_LAN, "127.0.0.1", "node-a.example.test"])
def test_explicit_remote_means_https_to_slm_host_whatever_the_addresses_say(ansible_host) -> None:
    out = _remote(
        ansible_host=ansible_host,
        inventory_hostname="node-a",
        ansible_facts={},
        slm_host=OTHER_NODE,
        frontend_slm_remote=True,
    )
    assert str(out["frontend_slm_backend_remote"]) == "True"
    assert out["frontend_slm_backend_protocol"] == "https"
    assert out["frontend_slm_backend_host"] == OTHER_NODE
    assert out["frontend_slm_upstream_prefix"] == "/slm/api/"


def test_slm_colocated_frontend_does_not_decide_the_proxy() -> None:
    """That flag is the SLM host's own 'serves the user frontend' switch, not this node's placement."""
    out = _remote(ansible_host=THIS_NODE_LAN, inventory_hostname="n", slm_host=OTHER_NODE, slm_colocated_frontend=True)
    assert str(out["frontend_slm_backend_remote"]) == "False"


def test_nothing_is_inferred_and_only_explicit_remote_can_fail_the_update() -> None:
    defaults_text = (FRONTEND / "defaults" / "main.yml").read_text(encoding="utf-8")
    assert "frontend_slm_placement" not in defaults_text
    assert "ansible_facts" not in "".join(
        line for line in defaults_text.splitlines() if line.startswith("frontend_slm_")
    )
    tasks_text = (FRONTEND / "tasks" / "code_only.yml").read_text(encoding="utf-8")
    assert "frontend_slm_placement" not in tasks_text
    assert "Settle an ambiguous" not in tasks_text
    tasks = yaml.safe_load(tasks_text)
    by_name = {t["name"]: t for t in tasks if "name" in t}
    for needle in ("Stat the fleet CA", "Refuse to proxy to a remote SLM"):
        task = next(t for n, t in by_name.items() if needle in n)
        assert "frontend_slm_backend_remote | bool" in task["when"], "the effective mode, as the template reads it"
        assert "slm_colocated_frontend" in task["when"], "a co-located host skips the site, so its preflight"
    assert_task = next(t for n, t in by_name.items() if "Refuse to proxy to a remote SLM" in n)
    assert "fleet CA" in assert_task["ansible.builtin.assert"]["fail_msg"]


def _proxies(hostvars: dict, groups: dict, **extra) -> list[str]:
    ctx = {**GROUP_VARS, "groups": groups, "hostvars": hostvars, **extra}
    out = _resolve(GROUP_VARS, ("slm_trusted_",), ctx)
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


def _preflight_holds(host: str, ca: dict) -> bool:
    """Evaluate the CA assertion's `that` list the way Ansible would, for one host and CA stat result."""
    tasks = yaml.safe_load((FRONTEND / "tasks" / "code_only.yml").read_text(encoding="utf-8"))
    task = next(t for t in tasks if "Refuse to proxy to a remote SLM" in t.get("name", ""))
    env = _env()
    ctx = {"frontend_slm_backend_host": host, "_frontend_slm_ca_stat": {"stat": ca}}
    return all(env.compile_expression(cond)(**ctx) for cond in task["ansible.builtin.assert"]["that"])


@pytest.mark.parametrize(
    ("host", "ca", "ok"),
    [
        (OTHER_NODE, {"exists": True, "isreg": True}, True),
        ("slm.example.test", {"exists": True, "isreg": True}, True),
        (OTHER_NODE, {"exists": True, "isreg": False}, False),  # a dangling link or a directory
        (OTHER_NODE, {"exists": False}, False),
        ("127.0.0.2", {"exists": True, "isreg": True}, False),  # loopback range, not just 127.0.0.1
        ("localhost", {"exists": True, "isreg": True}, False),
        ("2001:db8::7", {"exists": True, "isreg": True}, False),  # unbracketed in `server` and proxy_ssl_name
        ("", {"exists": True, "isreg": True}, False),
    ],
)
def test_the_remote_preflight_checks_the_effective_host_and_a_regular_ca_file(host, ca, ok) -> None:
    assert _preflight_holds(host, ca) is ok


def test_the_ca_stat_follows_symlinks() -> None:
    tasks = yaml.safe_load((FRONTEND / "tasks" / "code_only.yml").read_text(encoding="utf-8"))
    stat = next(t for t in tasks if "Stat the fleet CA" in t.get("name", ""))
    assert stat["ansible.builtin.stat"]["follow"] is True
