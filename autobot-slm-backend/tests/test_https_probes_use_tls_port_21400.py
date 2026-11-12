# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21400: `backend_port` is the plain uvicorn port; an https URL reads the nginx TLS port.

The registry inventory now defines `backend_port` (plain http). A probe that built an https URL from it
(formerly via ``backend_port | default(8443)``) would hit TLS on the plain port.
"""

import re
from pathlib import Path
from types import SimpleNamespace

from autobot_shared.ssot_config import config
from services.inventory_builder import _build_hostvars, build_registry_inventory

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PORT = re.compile(r"\bbackend_port\b")
# Play-level `backend_port: 8443` means the play itself pins the TLS port as its backend_port; the
# lines below are the plays whose https URL reads that pin. Each is fixed by its own vars block.
_ALLOWED: dict = {}


def _https_lines_using_backend_port():
    for path in sorted(_ANSIBLE.rglob("*")):
        if path.suffix not in {".yml", ".yaml", ".j2", ".sh"} or not path.is_file():
            continue
        rel = path.relative_to(_ANSIBLE).as_posix()
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if "https" in line.lower() and _PORT.search(line) and not line.lstrip().startswith("#"):
                yield f"{rel}:{no}"


def test_no_https_url_is_built_from_the_plain_backend_port() -> None:
    offenders = [site for site in _https_lines_using_backend_port() if site not in _ALLOWED]
    assert offenders == [], f"https built from backend_port (use backend_nginx_port): {offenders}"


def test_registry_inventory_carries_both_ports_from_the_ssot() -> None:
    all_vars = build_registry_inventory([], lambda _ip: False)["all"]["vars"]
    assert all_vars["backend_port"] == config.port.backend
    assert all_vars["backend_nginx_port"] == config.tls.backend_tls_port


def test_no_port_is_carried_per_node_so_the_all_vars_never_shadow_a_node_value() -> None:
    """One port value per install, from the SSOT, under ``all.vars`` only.

    Ansible lets host vars beat group ``all`` vars. The builder writes no port into a node's host vars (a node
    record has no backend port; its only port is ``ssh_port``, emitted as ``ansible_port``), so there is no
    node-level value the ``all`` vars could override. If a per-node backend port is ever added, it lands in
    host vars and wins by precedence; this test then fails and must be updated with it.
    """
    node = SimpleNamespace(
        node_id="n1", ip_address="192.0.2.10", ssh_user="autobot", ssh_port=22, roles=["backend"], detected_roles=[]
    )
    hostvars = _build_hostvars(node, lambda _ip: False)
    assert not {k for k in hostvars if "port" in k} - {"ansible_port"}
