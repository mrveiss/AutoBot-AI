# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``/slm/api`` proxy: same machine vs separate SLM node, and the refused open routes (#19832).

Resolves the frontend role's defaults with plain jinja2 (the ``bool`` filter registered as in
Ansible), renders ``nginx-frontend.conf.j2`` with the result, and asserts on the text. Limits,
stated: plain jinja2 rather than Ansible's templar, and nginx itself is not run, so a refused
route is asserted as rendered config, not as a live 403.
"""

from __future__ import annotations

import re

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
ROLE = ANSIBLE / "roles" / "frontend"
TEMPLATE = ROLE / "templates" / "nginx-frontend.conf.j2"
GROUP_VARS = yaml.safe_load((ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8"))
DEFAULTS = yaml.safe_load((ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))

_THIS_NODE = ["192.0.2.10", "10.0.0.1"]


def _env() -> jinja2.Environment:
    env = jinja2.Environment(trim_blocks=True, undefined=jinja2.StrictUndefined)
    env.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).strip().lower() == "true"
    env.tests["match"] = lambda v, pat: re.match(pat, str(v)) is not None
    # main's nginx-frontend.conf.j2 inlines the upload cap via lookup(); the file content is not
    # under test here.
    env.globals["lookup"] = lambda kind, path: ""
    env.globals["role_path"] = "/role"
    return env


def _resolve(slm_host: str | None) -> dict:
    """Resolve the role defaults the way Ansible does: lazily, each against the same context."""
    env = _env()
    ctx: dict = {k: v for k, v in GROUP_VARS.items() if not (isinstance(v, str) and "{{" in v)}
    ctx["ansible_facts"] = {"all_ipv4_addresses": _THIS_NODE}
    ctx["inventory_hostname"] = "node-a"
    ctx["ansible_host"] = _THIS_NODE[0]
    ctx["autobot_tls_remote_cert_dir"] = "/etc/c"
    if slm_host is not None:
        ctx["slm_host"] = slm_host
    pending = {k: v for k, v in DEFAULTS.items() if k.startswith(("frontend_slm_", "frontend_tls_cert_dir"))}
    for _ in range(len(pending) + 1):
        for key, raw in list(pending.items()):
            if not isinstance(raw, str) or ("{{" not in raw and "{%" not in raw):
                ctx[key] = raw
                del pending[key]
                continue
            try:
                ctx[key] = env.from_string(raw).render(**ctx).strip()
                del pending[key]
            except jinja2.UndefinedError:
                continue
    assert not pending, f"unresolved defaults: {sorted(pending)}"
    return ctx


def _render(slm_host: str | None) -> str:
    ctx = _resolve(slm_host)
    ctx.update(
        ansible_host="backend.test.invalid",
        nginx_http_port=80,
        frontend_tls_port=443,
        frontend_tls_cert="/c.pem",
        frontend_tls_key="/k.pem",
        frontend_dist_dir="/dist",
    )
    return _env().from_string(TEMPLATE.read_text(encoding="utf-8")).render(**ctx)


def _block(text: str, header: str) -> str:
    start = text.index(header)
    depth, i = 0, text.index("{", start)
    begin = i
    while True:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
        if depth == 0:
            return text[begin:i]


@pytest.mark.parametrize(
    "slm_host", ["192.0.2.10", "127.0.0.1", None], ids=["lan-address-of-this-node", "loopback", "unset"]
)
def test_same_machine_stays_on_loopback_uvicorn(slm_host: str | None) -> None:
    out = _render(slm_host)
    assert "server 127.0.0.1:8000 " in _block(out, "upstream autobot_slm_backend")
    api = _block(out, "location /slm/api/ ")
    assert "proxy_pass http://autobot_slm_backend/api/;" in api
    assert "proxy_ssl" not in api


def test_separate_node_proxies_https_to_the_slm_nginx_keeping_the_path() -> None:
    out = _render("198.51.100.7")
    assert "server 198.51.100.7:443 " in _block(out, "upstream autobot_slm_backend")
    for loc, upstream in (("location /slm/api/ ", "/slm/api/;"), ("location /slm/api/ws/ ", "/slm/api/ws/;")):
        block = _block(out, loc)
        assert f"proxy_pass https://autobot_slm_backend{upstream}" in block
        assert "proxy_ssl_server_name on;" in block
        assert "proxy_ssl_name 198.51.100.7;" in block
        assert "proxy_ssl_verify on;" in block
        assert "proxy_ssl_verify off" not in block
        assert "proxy_ssl_trusted_certificate /etc/c/ca-cert.pem;" in block
        assert "proxy_set_header Host $host;" in block or loc.endswith("ws/ ")


def test_the_remote_proxy_never_turns_verification_off() -> None:
    assert (
        "proxy_ssl_verify off"
        not in _render("198.51.100.7").split("location /slm/api/ws/")[1].split("location /api/voice")[0]
    )


def test_ports_come_from_the_group_vars_not_the_template() -> None:
    assert GROUP_VARS["slm_nginx_tls_port"] == 443
    vhost = (ANSIBLE / "roles/slm_manager/templates/autobot-slm.conf.j2").read_text(encoding="utf-8")
    assert "listen {{ slm_nginx_tls_port }} ssl http2;" in vhost
    assert "listen 443 ssl" not in vhost


REFUSED = ["health/database", "ready", "live", "recovery", "metrics/prometheus", "ready/"]


def test_open_health_and_metrics_routes_are_refused_on_the_main_origin() -> None:
    out = _render("192.0.2.10")
    refusal = _block(out, "location ~ ^/slm/api/(")
    assert "return 403;" in refusal
    header = out[out.index("location ~ ^/slm/api/(") : out.index("{", out.index("location ~ ^/slm/api/("))]
    pattern = header.split("location ~ ")[1].strip()
    rx = re.compile(pattern)
    for path in REFUSED:
        assert rx.match(f"/slm/api/{path}"), path
    # What the unified UI calls stays reachable (useSlmWebSocket.ts, APISettings.vue, useFleetMetrics.ts).
    for path in ("health", "nodes", "auth/login", "performance/metrics/prometheus", "monitoring/health"):
        assert not rx.match(f"/slm/api/{path}"), path


def test_the_refusal_outranks_the_generic_prefix_in_nginx_matching() -> None:
    """A regex location beats a plain prefix; the refusal must not be an exact/prefix block either."""
    out = _render("192.0.2.10")
    assert "location ~ ^/slm/api/(" in out
    assert "location ^~ /slm/api/" not in out
