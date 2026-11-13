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
from services.inventory_builder import build_registry_inventory

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_PORT = re.compile(r"\bbackend_port\b")
# Play-level `backend_port: 8443` means the play itself pins the TLS port as its backend_port; the
# lines below are the plays whose https URL reads that pin. Each is fixed by its own vars block.
_ALLOWED: dict = {}


_HTTPS_URL = re.compile(r"https://", re.IGNORECASE)


def _url_span(text: str, start: int) -> str:
    """The URL (or URL template) beginning at *start*: up to the first space or quote outside a ``{{ ... }}``.

    A Jinja expression may hold spaces and newlines, so ``https://{{ host }}:{{\\n backend_port }}/x`` is one URL.
    """
    depth, i = 0, start
    while i < len(text):
        if text.startswith("{{", i):
            depth, i = depth + 1, i + 2
        elif text.startswith("}}", i):
            depth, i = max(0, depth - 1), i + 2
        elif depth == 0 and (text[i].isspace() or text[i] in "\"'"):
            break
        else:
            i += 1
    return text[start:i]


def https_lines_using_backend_port(text: str) -> list[int]:
    """Lines (1-based) that build an https URL from ``backend_port``: the line carries both, or a URL template
    that spans several lines does. The reported line is where the URL starts."""
    lines = text.splitlines()
    hits = {
        no
        for no, line in enumerate(lines, 1)
        if "https" in line.lower() and _PORT.search(line) and not line.lstrip().startswith("#")
    }
    for match in _HTTPS_URL.finditer(text):
        no = text.count("\n", 0, match.start()) + 1
        if not lines[no - 1].lstrip().startswith("#") and _PORT.search(_url_span(text, match.start())):
            hits.add(no)
    return sorted(hits)


def _https_lines_using_backend_port():
    for path in sorted(_ANSIBLE.rglob("*")):
        if path.suffix not in {".yml", ".yaml", ".j2", ".sh"} or not path.is_file():
            continue
        rel = path.relative_to(_ANSIBLE).as_posix()
        for no in https_lines_using_backend_port(path.read_text(encoding="utf-8")):
            yield f"{rel}:{no}"


def test_contrast_a_template_split_across_lines_is_read_whole() -> None:
    split = 'url: "https://{{ host }}:{{\n  backend_port }}/api/health"\n'
    assert https_lines_using_backend_port(split) == [1]
    assert https_lines_using_backend_port(split.replace("backend_port", "backend_nginx_port")) == []
    assert https_lines_using_backend_port('url: "https://{{ host }}:{{ backend_port | default(8443) }}/x"') == [1]
    assert https_lines_using_backend_port('url: "http://{{ host }}:{{\n  backend_port }}/x"') == []
    assert https_lines_using_backend_port("# https://{{ host }}:{{\n#  backend_port }}") == []


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
    # The stand-in carries every attribute the builder reads for a node (node_id, ip_address, ssh_user,
    # ssh_port, roles, detected_roles), the way tests/services/test_inventory_builder_node_roles.py builds one.
    node = SimpleNamespace(
        node_id="n1",
        ip_address="192.0.2.10",
        ssh_user="autobot",
        ssh_port=22,
        roles=["backend"],
        detected_roles=[],
    )
    hostvars = build_registry_inventory([node], lambda _ip: False)["all"]["hosts"]["n1"]
    assert hostvars["ansible_host"] == "192.0.2.10"
    assert not {k for k in hostvars if "port" in k} - {"ansible_port"}
