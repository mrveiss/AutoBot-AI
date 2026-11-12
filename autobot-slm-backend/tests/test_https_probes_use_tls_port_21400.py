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

from autobot_shared.ssot_config import config
from services.inventory_builder import build_registry_inventory

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
