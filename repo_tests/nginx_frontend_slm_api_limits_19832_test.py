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
        frontend_slm_client_max_body_size=cap,
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


@pytest.mark.parametrize("loc", ["location /slm/api/ws/ ", "location /slm/api/ "])
def test_slm_locations_carry_the_slm_body_cap(loc: str) -> None:
    assert "client_max_body_size 7m;" in _block(_render("7m"), loc)


def test_the_slm_vhost_and_the_frontend_read_one_body_cap() -> None:
    vhost = VHOST.read_text(encoding="utf-8")
    assert "client_max_body_size {{ slm_client_max_body_size }};" in vhost
    assert not re.search(r"client_max_body_size\s+10m", vhost), "the SLM cap has a second literal"
    assert yaml.safe_load(GROUP_VARS_ALL.read_text(encoding="utf-8"))["slm_client_max_body_size"] == "10m"
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    assert defaults["frontend_slm_client_max_body_size"] == "{{ slm_client_max_body_size }}"
