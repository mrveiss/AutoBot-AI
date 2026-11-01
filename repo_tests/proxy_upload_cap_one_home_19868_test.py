# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19868: one declared proxy upload cap feeds the fleet templates and the Docker config."""

from __future__ import annotations

import re

import pytest
import yaml
from repo_tests._paths import repo_root

_ANSIBLE = "autobot-slm-backend/ansible"
_HOME = f"{_ANSIBLE}/_shared/files/upload-cap.conf"
_TEMPLATES = [
    f"{_ANSIBLE}/roles/frontend/templates/nginx-frontend.conf.j2",
    f"{_ANSIBLE}/roles/slm_manager/templates/autobot-slm.conf.j2",
]
_LOOKUP = "{{ lookup('file', role_path ~ '/../../_shared/files/upload-cap.conf') }}"
_MOUNT = f"./{_HOME}:/etc/nginx/upload-cap.conf:ro"


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def _location_cap_lines(rel: str) -> list[str]:
    """Literal caps at location depth (8 spaces); the slm template's 10m server default is at 4."""
    return [ln.strip() for ln in _read(rel).splitlines() if ln.startswith("        ") and "client_max_body_size" in ln]


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
    return re.search(r"location /api/ \{(.*?)\n\}", text, re.S).group(1)


def test_docker_applies_it_at_the_upload_location_only() -> None:
    assert "include /etc/nginx/upload-cap.conf;" in _api_location()
    common = _read("docker/nginx/nginx-common.conf")
    assert "upload-cap.conf" not in common and re.search(r"^client_max_body_size 10m;$", common, re.M)
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
