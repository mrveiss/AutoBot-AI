# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The split-host frontend site proxies ``/slm/api`` to a configurable SLM host (#19832).

Epic #19829 / ADR-011: the unified UI reaches the SLM backend on its own origin at
``/slm/api``. The split-host frontend site had no such location. These tests render
``nginx-frontend.conf.j2`` with plain jinja2 configured like the ``template`` module
(``trim_blocks=True``) and assert on the rendered text, for a co-located SLM (loopback)
and for an SLM on a separate node.

Limits, stated: plain jinja2 rather than Ansible's templar, and the variable values
are the ones the role's defaults resolve to when ``slm_host`` / ``slm_backend_port`` are
set -- no real two-host deployment is exercised here.
"""

from __future__ import annotations

import re

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "frontend"
TEMPLATE = ROLE / "templates" / "nginx-frontend.conf.j2"
DEFAULTS = ROLE / "defaults" / "main.yml"

# Neutral, non-routable test values: the point is that they, and nothing else, reach the output.
_SEPARATE = {"host": "slm-node.test.invalid", "port": "18000"}
_COLOCATED = {"host": "127.0.0.1", "port": "18000"}


def _render(host: str, port: str) -> str:
    env = jinja2.Environment(trim_blocks=True, undefined=jinja2.StrictUndefined)
    return env.from_string(TEMPLATE.read_text(encoding="utf-8")).render(
        ansible_host="backend.test.invalid",
        nginx_http_port=80,
        frontend_tls_port=443,
        frontend_tls_cert="/c.pem",
        frontend_tls_key="/k.pem",
        frontend_dist_dir="/dist",
        frontend_slm_backend_host=host,
        frontend_slm_backend_port=port,
        frontend_slm_backend_protocol="http",
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


@pytest.mark.parametrize("target", [_SEPARATE, _COLOCATED], ids=["separate-node", "co-located"])
def test_slm_api_proxies_to_the_configured_upstream(target: dict[str, str]) -> None:
    out = _render(target["host"], target["port"])
    assert f"server {target['host']}:{target['port']} " in _block(out, "upstream autobot_slm_backend")
    api = _block(out, "location /slm/api/ ")
    assert "proxy_pass http://autobot_slm_backend/api/;" in api
    assert "proxy_set_header Upgrade $http_upgrade;" in api
    assert "proxy_set_header Connection $connection_upgrade;" in api
    for header in ("Host $host", "X-Real-IP $remote_addr", "X-Forwarded-Proto $scheme"):
        assert f"proxy_set_header {header};" in api


def test_slm_websocket_location_upgrades_and_precedes_the_generic_block() -> None:
    out = _render(**_SEPARATE)
    ws = _block(out, "location /slm/api/ws/ ")
    assert "proxy_pass http://autobot_slm_backend/api/ws/;" in ws
    assert 'proxy_set_header Connection "upgrade";' in ws
    assert "proxy_read_timeout 86400;" in ws
    assert out.index("location /slm/api/ws/ ") < out.index("location /slm/api/ ")


def test_the_literal_host_and_port_are_not_in_the_template() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    upstream = _block(text, "upstream autobot_slm_backend")
    assert re.search(r"server \{\{ frontend_slm_backend_host \}\}:\{\{ frontend_slm_backend_port \}\}", upstream)
    for loc in ("location /slm/api/ws/ ", "location /slm/api/ "):
        assert not re.search(r"proxy_pass\s+\S*(\d+\.\d+\.\d+\.\d+|:\d+)", _block(text, loc))


def test_defaults_come_from_the_inventory_and_the_ssot_port() -> None:
    defaults = yaml.safe_load(DEFAULTS.read_text(encoding="utf-8"))
    assert "slm_host" in defaults["frontend_slm_backend_host"]
    assert "slm_backend_port" in defaults["frontend_slm_backend_port"]
    assert "firewall_service_ports.slm_backend" in defaults["frontend_slm_backend_port"]
    assert not re.search(r"\d{4}", defaults["frontend_slm_backend_port"])
