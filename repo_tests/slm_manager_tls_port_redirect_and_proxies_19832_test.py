# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM TLS port has one name, the port-80 redirect honours it, the frontend stays trusted (#19832).

Plain jinja2 stands in for Ansible's templar (the ``bool`` filter and ``intersect`` are registered
as Ansible would), and nginx is not run: assertions are on rendered text and parsed YAML.
"""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
ROLE = ANSIBLE / "roles" / "slm_manager"
VHOST = ROLE / "templates" / "autobot-slm.conf.j2"
TASKS = ROLE / "tasks" / "main.yml"
GROUP_VARS = ANSIBLE / "inventory" / "group_vars" / "all.yml"
_ROLE_REL = "autobot-slm-backend/ansible/roles/slm_manager"


def _scanned(root: Path) -> list[Path]:
    """The slm_manager task files and the SLM vhost: where a literal TLS port must not appear."""
    role = root / _ROLE_REL
    return (
        [*sorted((role / "tasks").glob("*.yml")), role / "templates" / "autobot-slm.conf.j2"] if role.is_dir() else []
    )


REACH = declare(
    "slm-manager-no-literal-tls-port-19832",
    discover=_scanned,
    floor=9,
    roots=(_ROLE_REL,),
    what="slm_manager task files plus the SLM vhost",
)


def test_no_literal_tls_port_in_slm_manager_tasks_or_vhost() -> None:
    """#19832: 443 appears nowhere in the role's tasks or the SLM vhost; slm_nginx_tls_port is the name."""
    for path in REACH.examined(repo_root()):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            assert not re.search(r"(?<![\w.])443(?![\w.])", line), f"{path.name}:{number}: {line.strip()}"


def test_the_ufw_https_rule_and_summary_read_the_tls_port() -> None:
    text = TASKS.read_text(encoding="utf-8")
    tasks = yaml.safe_load(text)
    ufw = next(t for t in tasks if t.get("name") == "SLM | Allow HTTPS")
    assert ufw["community.general.ufw"]["port"] == "{{ slm_nginx_tls_port }}"
    assert "Nginx: HTTPS on port {{ slm_nginx_tls_port }}" in text


def _redirect(tls_port: int) -> str:
    env = jinja2.Environment(trim_blocks=True, undefined=jinja2.StrictUndefined)
    env.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).strip().lower() == "true"
    env.globals["lookup"] = lambda kind, path: ""
    implicit = yaml.safe_load(GROUP_VARS.read_text(encoding="utf-8"))["slm_https_implicit_port"]
    src = VHOST.read_text(encoding="utf-8")
    head = src[: src.index("# HTTPS server")]
    out = env.from_string(head).render(
        slm_nginx_tls_port=tls_port, slm_https_implicit_port=implicit, slm_colocated_frontend=False
    )
    return re.search(r"return 301 [^;]+;", out).group(0)


def test_port_80_redirect_keeps_the_plain_form_on_443() -> None:
    assert _redirect(443) == "return 301 https://$host$request_uri;"


@pytest.mark.parametrize("port", [8443, 9443])
def test_port_80_redirect_carries_a_non_default_tls_port(port: int) -> None:
    assert _redirect(port) == f"return 301 https://$host:{port}$request_uri;"


def _proxy_env() -> jinja2.Environment:
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    env.tests["match"] = lambda v, pat: re.match(pat, str(v)) is not None
    env.tests["search"] = lambda v, pat: re.search(pat, str(v)) is not None
    env.filters["extract"] = lambda key, mapping, attr: mapping[key].get(attr, jinja2.Undefined())
    return env


def _resolve(expr_key: str, ctx: dict) -> object:
    raw = yaml.safe_load(GROUP_VARS.read_text(encoding="utf-8"))[expr_key]
    return _proxy_env().from_string(raw).render(**ctx)


def test_trusted_proxies_carry_the_frontend_group_and_frontend_host() -> None:
    ctx = {
        "groups": {"frontend": ["f1"]},
        "hostvars": {"f1": {"ansible_host": "192.0.2.50"}},
        "slm_host": "192.0.2.10",
        "ansible_host": "192.0.2.10",
        "frontend_host": "192.0.2.60",
        "slm_loopback_ipv4": "127.0.0.1",
        "slm_loopback_ipv6": "::1",
    }
    ctx["slm_trusted_frontend_addrs"] = _resolve("slm_trusted_frontend_addrs", ctx)
    got = _resolve("slm_trusted_proxies", ctx).split(",")
    assert {"192.0.2.50", "192.0.2.60"} <= set(got)
    assert _resolve("slm_trusted_frontend_addrs", {**ctx, "groups": {}, "frontend_host": ""}) == ""


def _assert_task() -> dict:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    return next(t for t in tasks if "frontend is among the trusted proxies" in t.get("name", ""))


def _holds(task: dict, addrs: list[str], proxies: str) -> bool:
    env = _proxy_env()
    addrs = ",".join(addrs)
    env.filters["intersect"] = lambda a, b: [x for x in a if x in b]
    ctx = {"slm_trusted_frontend_addrs": addrs, "slm_trusted_proxies": proxies}
    return all(env.compile_expression(c)(**ctx) for c in task["ansible.builtin.assert"]["that"])


def test_the_assert_fires_only_when_a_frontend_exists() -> None:
    task = _assert_task()
    when = task["when"]
    assert "frontend_slm_remote" in when and "groups['frontend']" in when
    assert "frontend" in task["ansible.builtin.assert"]["fail_msg"]


def test_the_assert_passes_with_a_frontend_entry_and_fails_without_one() -> None:
    task = _assert_task()
    assert _holds(task, ["192.0.2.50"], "127.0.0.1,192.0.2.10,192.0.2.50")
    assert not _holds(task, [], "127.0.0.1,192.0.2.10")
    assert not _holds(task, ["192.0.2.50"], "127.0.0.1,192.0.2.10")
    assert not _holds(task, ["fe.example.test"], "127.0.0.1,fe.example.test"), "a DNS name is never trusted"


def test_trusted_proxies_derive_from_the_frontend_address_list() -> None:
    raw = yaml.safe_load(GROUP_VARS.read_text(encoding="utf-8"))
    assert "slm_trusted_frontend_addrs" in raw["slm_trusted_proxies"]
    assert "groups['frontend']" in raw["slm_trusted_frontend_addrs"]
