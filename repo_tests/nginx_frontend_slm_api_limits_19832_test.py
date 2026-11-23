# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The ``/slm/api`` locations match the SLM vhost's limits and share one port name (#19832).

Companion to ``nginx_frontend_slm_api_proxy_19832_test.py``. Covers the request-body cap
(nginx's 1m default otherwise rejects SLM uploads); the one-name SLM port is owned by
``slm_backend_port_one_name_test.py``.

Limits, stated: plain jinja2 rather than Ansible's templar; the ``ansible_facts`` shape is the
one ``gather_facts`` produces, not a live host.
"""

from __future__ import annotations

import re

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_text

ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
ROLE = ANSIBLE / "roles" / "frontend"
TEMPLATE = ROLE / "templates" / "nginx-frontend.conf.j2"
DEFAULTS = ROLE / "defaults" / "main.yml"
GROUP_VARS_ALL = ANSIBLE / "inventory" / "group_vars" / "all.yml"
VHOST = ANSIBLE / "roles" / "slm_manager" / "templates" / "autobot-slm.conf.j2"


def _render(cap: str) -> str:
    env = jinja2.Environment(trim_blocks=True, undefined=jinja2.StrictUndefined)
    env.filters["bool"] = bool
    # main's nginx-frontend.conf.j2 inlines the upload cap via lookup(); the file content is not
    # under test here.
    env.globals["lookup"] = lambda kind, path: ""
    env.globals["role_path"] = "/role"
    return env.from_string(TEMPLATE.read_text(encoding="utf-8")).render(
        ansible_host="backend.test.invalid",
        nginx_http_port=80,
        frontend_tls_port=443,
        frontend_tls_cert="/c.pem",
        frontend_tls_key="/k.pem",
        frontend_dist_dir="/dist",
        frontend_upstream_backend_port="8443",
        frontend_slm_backend_host="127.0.0.1",
        frontend_slm_backend_port="18000",
        frontend_slm_backend_protocol="http",
        frontend_slm_backend_remote=False,
        frontend_slm_upstream_prefix="/api/",
        frontend_slm_ca_cert="/ca.pem",
        frontend_slm_refused_routes=yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))["frontend_slm_refused_routes"],
        slm_client_max_body_size=cap,
    )


def _block(text: str, header: str) -> str:
    start = text.index(header)
    depth, i = 0, text.index("{", start)
    begin = i
    while True:
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        i += 1
        if depth == 0:
            return text[begin:i]


@pytest.mark.parametrize("loc", ["location ^~ /slm/api/ws/ ", "location ^~ /slm/api/ "])
def test_slm_locations_carry_the_slm_body_cap(loc: str) -> None:
    assert "client_max_body_size 7m;" in _block(_render("7m"), loc)


def _active_caps(text: str) -> list[str]:
    """Values of the uncommented `client_max_body_size` directives."""
    code = code_text(text, name="vhost.conf", strip_trailing=True)  # the shared comment stripper (#17941)
    return re.findall(r"^\s*client_max_body_size\s+(.+?);", code, re.M)


def _literal_caps(text: str) -> list[str]:
    """Active cap directives whose value is not the shared variable (#22055)."""
    return [v for v in _active_caps(text) if v != "{{ slm_client_max_body_size }}"]


def test_the_literal_cap_detector_has_a_contrast_pair() -> None:
    assert _literal_caps("    client_max_body_size 10m;\n") == ["10m"]
    assert _literal_caps("    client_max_body_size 0;\n") == ["0"]
    assert _literal_caps("    client_max_body_size {{ slm_client_max_body_size }};\n") == []
    assert _literal_caps("    # client_max_body_size 10m;\n") == []


def test_the_slm_vhost_and_the_frontend_read_one_body_cap() -> None:
    vhost = VHOST.read_text(encoding="utf-8")
    assert not _literal_caps(vhost), "the SLM vhost carries a literal client_max_body_size"
    assert _active_caps(vhost), "the SLM vhost carries no active body cap"
    assert set(_active_caps(vhost)) == {"{{ slm_client_max_body_size }}"}
    assert not re.search(r"client_max_body_size\s+10m", vhost), "the SLM cap has a second literal"
    assert yaml.safe_load(GROUP_VARS_ALL.read_text(encoding="utf-8"))["slm_client_max_body_size"] == "10m"
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    assert "frontend_slm_client_max_body_size" not in defaults, "the SLM cap has one home, no alias"
    assert "slm_client_max_body_size" not in defaults


COMMON_DEFAULTS = ANSIBLE / "roles" / "common" / "defaults" / "main.yml"


_TLS_VAR = "{{ slm_nginx_tls_port }}"


def _tls_listens(text: str) -> list[str]:
    """The address part of every active `listen ... ssl` directive."""
    code = code_text(text, name="vhost.conf", strip_trailing=True)
    return re.findall(r"^\s*listen\s+(.+?)\s+ssl\b", code, re.M)


def _literal_tls_listens(text: str) -> list[str]:
    """TLS listens whose port is not the shared variable (a bare number, with or without `[::]:`)."""
    return [listen for listen in _tls_listens(text) if not listen.endswith(_TLS_VAR)]


@pytest.mark.parametrize("listen", ["listen 443 ssl;", "listen [::]:443 ssl;", "listen 8443 ssl http2;"])
def test_the_tls_listen_detector_trips_on_a_literal_port(listen: str) -> None:
    assert _literal_tls_listens(f"    {listen}\n")


@pytest.mark.parametrize(
    "listen",
    [
        "listen {{ slm_nginx_tls_port }} ssl;",
        "listen [::]:{{ slm_nginx_tls_port }} ssl;",
        "# listen 443 ssl;",
        # Only the comment stripper saves this one: unstripped, the lazy `(.+?)\\s+ssl` capture would run into
        # the trailing `# ssl` and read `{{ slm_nginx_tls_port }};  #` as a literal port. A Jinja `{# #}` comment
        # is not covered: the shared stripper has no Jinja support yet (#22099).
        "listen {{ slm_nginx_tls_port }};  # ssl is set by the include",
    ],
)
def test_the_tls_listen_detector_passes_the_variable_and_comments(listen: str) -> None:
    assert not _literal_tls_listens(f"    {listen}\n")


def test_the_slm_vhost_and_firewall_read_one_tls_port_name() -> None:
    """#22055: the vhost's IPv4 and IPv6 listens and `slm_frontend` all derive from slm_nginx_tls_port."""
    vhost = VHOST.read_text(encoding="utf-8")
    listens = _tls_listens(vhost)
    assert len(listens) >= 2, "the IPv4 and the IPv6 TLS listen are both expected"
    assert not _literal_tls_listens(vhost), "a literal TLS port reappeared in the SLM vhost"
    assert yaml.safe_load(GROUP_VARS_ALL.read_text(encoding="utf-8"))["slm_nginx_tls_port"] == 443
    ports = yaml.safe_load(COMMON_DEFAULTS.read_text(encoding="utf-8"))["firewall_service_ports"]
    assert ports["slm_frontend"] == "{{ slm_nginx_tls_port }}"
