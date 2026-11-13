# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21400: the frontend's backend upstream port is the one the proxy scheme listens on.

nginx-frontend.conf.j2 proxies with ``backend_protocol`` (default https) to ``server host:<port>``. Once an inventory
(the bare ``-i host,`` extra vars, or the registry inventory) defined ``backend_port`` as the plain uvicorn listener,
reading it alone rendered ``:8001`` under ``proxy_pass https://`` - TLS to a plain port. The role now derives the port
from the scheme (``frontend_upstream_backend_port``). These tests render that variable the way the role does.
"""

from pathlib import Path

import pytest
import yaml

from autobot_shared.ssot_config import config
from services.ansible_extra_vars import port_vars

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_ROLE = _ANSIBLE / "roles" / "frontend"
_SHARED_VARS = "_shared/vars/backend_scheme_port.yml"


def _render(expression: str, **variables) -> str:
    import jinja2

    return jinja2.Environment().from_string(expression).render(**variables)


def _upstream_port(**variables) -> str:
    """What the frontend role renders: its default reads the shared variable, which is rendered from its file."""
    shared = yaml.safe_load((_ANSIBLE / _SHARED_VARS).read_text(encoding="utf-8"))["backend_scheme_port"]
    default = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert default["frontend_upstream_backend_port"] == "{{ backend_scheme_port }}"
    return _render(shared, **variables)


def _scheme(**variables) -> str:
    return _render("{{ backend_protocol | default('https') }}", **variables)


def _pairs(rendered_port: str, scheme: str, ssot: dict) -> bool:
    """Whether the port listens for the scheme: TLS port for https, plain port for http."""
    return rendered_port == str(ssot["backend_nginx_port" if scheme == "https" else "backend_port"])


_SSOT = port_vars(config)


@pytest.mark.parametrize(
    ("label", "variables", "expected"),
    [
        ("main bare run: nothing defined", {}, "8443"),
        ("branch bare run / registry inventory: both SSOT ports", dict(_SSOT), str(_SSOT["backend_nginx_port"])),
        ("the SSOT ports with an http scheme", {**_SSOT, "backend_protocol": "http"}, str(_SSOT["backend_port"])),
        ("static inventory defining only backend_port (as on main)", {"backend_port": 8001}, "8001"),
        ("a playbook pinning port and scheme together", {"backend_port": 8443, "backend_protocol": "http"}, "8443"),
    ],
)
def test_the_upstream_port_follows_the_scheme_and_keeps_what_main_rendered(label, variables, expected) -> None:
    assert _upstream_port(**variables) == expected, label


@pytest.mark.parametrize("scheme", [{}, {"backend_protocol": "http"}, {"backend_protocol": "https"}])
def test_with_the_ssot_ports_the_rendered_pair_is_consistent(scheme) -> None:
    variables = {**_SSOT, **scheme}
    assert _pairs(_upstream_port(**variables), _scheme(**variables), _SSOT)


def test_contrast_the_old_expression_renders_a_mismatched_pair() -> None:
    """The control: ``backend_port | default(8443)`` alone, with the SSOT ports and the default scheme, is the bug."""
    old = _render("{{ backend_port | default(8443) }}", **_SSOT)
    assert not _pairs(old, _scheme(**_SSOT), _SSOT)


def test_the_template_and_the_summary_read_the_paired_variable_and_the_scheme_default_is_unchanged() -> None:
    template = (_ROLE / "templates" / "nginx-frontend.conf.j2").read_text(encoding="utf-8")
    assert ":{{ frontend_upstream_backend_port }} max_fails=" in template
    assert template.count("proxy_pass {{ backend_protocol | default('https') }}://autobot_backend;") >= 1
    assert "{{ backend_port | default(8443) }} max_fails=" not in template


def _health_url(**variables) -> str:
    plays = yaml.safe_load((_ANSIBLE / "playbooks" / "rotate-service-keys.yml").read_text(encoding="utf-8"))
    play = next(p for p in plays if p.get("name", "").startswith("Phase 3"))
    assert play["vars_files"] == ["../" + _SHARED_VARS]
    url = play["vars"]["backend_health_url"]
    assert "{{ backend_scheme_port }}" in url and "backend_nginx_port" not in url and "backend_port" not in url
    return _render(url, ansible_host="h", backend_scheme_port=_upstream_port(**variables), **variables)


@pytest.mark.parametrize(
    ("label", "variables", "expected"),
    [
        ("nothing defined (main)", {}, "https://h:8443/api/health"),
        ("the SSOT ports", dict(_SSOT), f"https://h:{_SSOT['backend_nginx_port']}/api/health"),
        (
            "production.yml's backend group: plain port paired with http (main rendered :8001)",
            {**_SSOT, "backend_protocol": "http"},
            f"http://h:{_SSOT['backend_port']}/api/health",
        ),
    ],
)
def test_the_key_rotation_health_url_pairs_its_port_with_its_scheme(label, variables, expected) -> None:
    assert _health_url(**variables) == expected, label
