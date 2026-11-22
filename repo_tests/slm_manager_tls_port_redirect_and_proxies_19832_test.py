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


def _tasks() -> dict[str, dict]:
    return {t["name"]: t for t in yaml.safe_load(TASKS.read_text(encoding="utf-8")) if "name" in t}


def _task(fragment: str) -> dict:
    return next(t for n, t in _tasks().items() if fragment in n)


def _lookup(entry: str, out: str) -> dict:
    """One `getent ahosts` loop result: the entry and its stdout (empty and rc 2 when it did not resolve)."""
    return {"item": entry, "rc": 0 if out else 2, "stdout_lines": out.splitlines()}


def _getent(ip: str) -> str:
    return f"{ip:<15} STREAM name.test\n{ip:<15} DGRAM\n{ip:<15} RAW"


def _env() -> jinja2.Environment:
    env = _proxy_env()
    env.filters["flatten"] = lambda seq: [x for sub in seq for x in sub]
    env.filters["regex_replace"] = lambda v, pat, rep: re.sub(pat, rep, str(v))
    return env


def _resolved(results: list[dict]) -> str:
    raw = _task("trust the resolved frontend addresses")["ansible.builtin.set_fact"]["slm_trusted_frontend_resolved"]
    return _env().from_string(raw).render(_slm_frontend_lookup={"results": results}).strip()


def _assert_holds(addrs: str, results: list[dict]) -> tuple[bool, str]:
    task = _task("every frontend entry resolved")["ansible.builtin.assert"]
    env = _env()
    ctx = {"slm_trusted_frontend_addrs": addrs, "_slm_frontend_lookup": {"results": results}}
    ok = all(env.compile_expression(c)(**ctx) for c in task["that"])
    return ok, env.from_string(task["fail_msg"]).render(**ctx)


def test_the_lookup_runs_getent_with_argv_and_only_where_a_frontend_exists() -> None:
    task = _task("resolve the frontend trusted-proxy entries")
    assert task["ansible.builtin.command"]["argv"][:2] == ["getent", "ahosts"]
    assert "frontend_slm_remote" in task["when"] and "groups['frontend']" in task["when"]


def test_a_hostname_is_trusted_by_the_ip_it_resolves_to() -> None:
    assert _resolved([_lookup("fe.example.test", _getent("192.0.2.50"))]) == "192.0.2.50"
    assert _assert_holds("fe.example.test", [_lookup("fe.example.test", _getent("192.0.2.50"))])[0]


def test_an_ipv6_frontend_is_accepted() -> None:
    results = [_lookup("2001:db8::7", _getent("2001:db8::7")), _lookup("192.0.2.50", _getent("192.0.2.50"))]
    assert _resolved(results) == "2001:db8::7,192.0.2.50"
    assert _assert_holds("2001:db8::7,192.0.2.50", results)[0]


def test_an_unresolvable_entry_fails_and_is_named() -> None:
    results = [_lookup("192.0.2.50", _getent("192.0.2.50")), _lookup("gone.example.test", "")]
    ok, message = _assert_holds("192.0.2.50,gone.example.test", results)
    assert not ok
    assert "gone.example.test" in message and "192.0.2.50," not in message


def test_no_frontend_entry_at_all_fails() -> None:
    assert not _assert_holds("", [])[0]


def test_the_trusted_list_carries_the_resolved_addresses_not_the_names() -> None:
    raw = yaml.safe_load(GROUP_VARS.read_text(encoding="utf-8"))
    ctx = {
        "slm_loopback_ipv4": "127.0.0.1",
        "slm_loopback_ipv6": "::1",
        "slm_host": "192.0.2.10",
        "ansible_host": "192.0.2.10",
        "slm_trusted_frontend_addrs": "fe.example.test",
        "slm_trusted_frontend_resolved": "192.0.2.50,2001:db8::7",
    }
    got = _proxy_env().from_string(raw["slm_trusted_proxies"]).render(**ctx).split(",")
    assert {"192.0.2.50", "2001:db8::7"} <= set(got) and "fe.example.test" not in got


def test_the_unit_falls_back_to_the_addresses_before_the_play_resolves_them() -> None:
    raw = yaml.safe_load(GROUP_VARS.read_text(encoding="utf-8"))
    ctx = {"slm_loopback_ipv4": "a", "slm_loopback_ipv6": "b", "slm_trusted_frontend_addrs": "192.0.2.50"}
    got = _proxy_env().from_string(raw["slm_trusted_proxies"]).render(**ctx).split(",")
    assert "192.0.2.50" in got


def test_trusted_proxies_derive_from_the_frontend_address_list() -> None:
    raw = yaml.safe_load(GROUP_VARS.read_text(encoding="utf-8"))
    assert "groups['frontend']" in raw["slm_trusted_frontend_addrs"]
