# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19868: one declared proxy upload cap feeds the fleet templates and the Docker config."""

from __future__ import annotations

import re
from pathlib import Path

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root

_ANSIBLE = "autobot-slm-backend/ansible"
_HOME = f"{_ANSIBLE}/_shared/files/upload-cap.conf"
_TEMPLATES = [
    f"{_ANSIBLE}/roles/frontend/templates/nginx-frontend.conf.j2",
    f"{_ANSIBLE}/roles/slm_manager/templates/autobot-slm.conf.j2",
]
_LOOKUP = "{{ lookup('file', proxy_upload_cap_file) }}"
_MOUNT = f"./{_HOME}:/etc/nginx/upload-cap.conf:ro"


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


_SLM_CAP = "client_max_body_size {{ slm_client_max_body_size }};"


def _location_cap_lines(rel: str) -> list[str]:
    """Literal caps at location depth (8 spaces); the slm template's 10m server default is at 4.

    The frontend's /slm/api locations take the SLM's single cap home (#19832), never a literal.
    """
    return [
        ln.strip()
        for ln in _read(rel).splitlines()
        if ln.startswith("        ") and "client_max_body_size" in ln and ln.strip() != _SLM_CAP
    ]


def test_the_frontend_slm_locations_take_the_slm_cap_home() -> None:
    text = _read(_TEMPLATES[0])
    assert text.count(_SLM_CAP) == 2, "/slm/api/ and /slm/api/ws/ each read slm_client_max_body_size"
    assert "frontend_slm_client_max_body_size" not in text


def test_the_home_declares_exactly_the_cap() -> None:
    assert re.fullmatch(r"client_max_body_size \d+[kKmMgG];\n", _read(_HOME))


@pytest.mark.parametrize("role", ["frontend", "slm_manager"])
def test_the_lookup_path_reaches_the_home_from_each_role(role: str) -> None:
    assert (repo_root() / _ANSIBLE / "roles" / role / "../../_shared/files/upload-cap.conf").resolve().is_file()


@pytest.mark.parametrize("template", _TEMPLATES)
def test_each_fleet_upload_location_reads_the_home(template: str) -> None:
    text = _read(template)
    assert text.count(_LOOKUP) == 1
    assert not _location_cap_lines(template)


def _api_location() -> str:
    text = _read("docker/nginx/nginx-locations.conf")
    assert "proxy_request_buffering off;" in text
    return re.search(r"location /api/ \{(.*?)\n\}", text, re.S).group(1)


def test_docker_applies_it_at_the_upload_location_only() -> None:
    assert "include /etc/nginx/upload-cap.conf;" in _api_location()
    common = _read("docker/nginx/nginx-common.conf")
    assert "upload-cap.conf" not in common and re.search(r"^client_max_body_size 100m;$", common, re.M)
    slm = _read("docker/nginx/nginx-slm-locations.conf")
    assert "upload-cap.conf" not in slm and "client_max_body_size" not in slm


def test_each_container_serving_that_location_gets_the_cap() -> None:
    compose = yaml.safe_load(_read("docker-compose.yml"))
    mounting = [
        s for s in compose["services"].values() if any("nginx-locations.conf" in str(v) for v in s.get("volumes", []))
    ]
    assert mounting and all(_MOUNT in s["volumes"] for s in mounting)
    assert f"COPY {_HOME} /etc/nginx/upload-cap.conf" in _read("docker/frontend/Dockerfile")


def test_the_unread_group_var_is_gone() -> None:
    assert "client_max_body_size" not in _read(f"{_ANSIBLE}/inventory/group_vars/frontend.yml")


def _render_cap_path(expr: str, **variables: str) -> str:
    """Evaluate the group_vars expression the way ansible does: a jinja2 render with the play's variables."""
    return jinja2.Environment(undefined=jinja2.Undefined).from_string(expr).render(**variables)


def _cap_path_problem(expr: str) -> str | None:
    """Why the declared path expression is unsafe in a play or a role, or None when it resolves in both."""
    ansible = repo_root() / _ANSIBLE
    contexts = {
        "role": {"role_path": str(ansible / "roles" / "x")},
        "play": {"playbook_dir": str(ansible / "playbooks")},
    }
    for name, variables in contexts.items():
        rendered = _render_cap_path(expr, **variables)
        if not rendered or rendered.startswith("/upload-cap"):
            return f"{name}: renders to a bare or empty path {rendered!r}"
        if Path(rendered).resolve() != (ansible / "_shared/files/upload-cap.conf").resolve():
            return f"{name}: resolves outside _shared/files: {rendered!r}"
    return None


def _template_problem(text: str) -> str | None:
    """A template rendered from a play (provision-fleet-roles.yml Phase 4c) has no role_path."""
    if "role_path" in text:
        return "reads role_path"
    return None if _LOOKUP in text else "does not use the proxy_upload_cap_file lookup"


_BARE_ROLE_PATH = "{{ role_path }}/../../_shared/files/upload-cap.conf"
_OUTSIDE_FALLBACK = (
    "{{ (role_path ~ '/../../_shared/files') if role_path is defined "
    "else (playbook_dir ~ '/../files') }}/upload-cap.conf"
)


def test_the_path_detector_rejects_a_bare_role_path() -> None:
    assert _cap_path_problem(_BARE_ROLE_PATH) is not None


def test_the_path_detector_rejects_a_fallback_outside_the_home() -> None:
    assert _cap_path_problem(_OUTSIDE_FALLBACK) is not None


def test_the_path_detector_accepts_the_configured_expression() -> None:
    group_vars = yaml.safe_load(_read(f"{_ANSIBLE}/inventory/group_vars/all.yml"))
    assert _cap_path_problem(group_vars["proxy_upload_cap_file"]) is None


def test_the_template_detector_rejects_role_path() -> None:
    assert _template_problem("{{ lookup('file', role_path ~ '/x') }}") is not None


def test_the_template_detector_accepts_the_lookup_alone() -> None:
    assert _template_problem(f"server {{\n    {_LOOKUP}\n}}") is None


@pytest.mark.parametrize("template", _TEMPLATES)
def test_no_fleet_template_reads_role_path(template: str) -> None:
    assert _template_problem(_read(template)) is None
