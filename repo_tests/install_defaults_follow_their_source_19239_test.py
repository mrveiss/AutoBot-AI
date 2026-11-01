# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""install.sh's pinned defaults equal their sources of truth, and its IP cache cannot be planted (#19239).

The installer runs before the code is checked out, so it pins two values instead of reading
them: the minimum Node.js (autobot-frontend/package.json engines.node) and the SLM backend port
(slm_backend_port in the ansible inventory group_vars/all.yml). These tests fail the moment either side moves alone.
It also cached the detected IP in /tmp, where any local user can create the file first, and
reused it unvalidated; the cache is now root-only and reused only while the address is still
assigned to an interface here.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_INSTALL = _ROOT / "install.sh"


def _readonly(name: str) -> str:
    m = re.search(rf'\b{name}="([^"]+)"', _INSTALL.read_text(encoding="utf-8"))
    assert m, f"install.sh no longer pins {name}"
    return m.group(1)


def test_the_node_minimum_is_the_frontends_engines_floor() -> None:
    engines = json.loads((_ROOT / "autobot-frontend" / "package.json").read_text(encoding="utf-8"))["engines"]["node"]
    assert engines == f">={_readonly('NODE_MIN_VERSION')}", engines


def test_the_backend_port_is_the_roles_slm_backend_port() -> None:
    defaults = _ROOT / "autobot-slm-backend/ansible/inventory/group_vars/all.yml"  # #19832: the one authority
    port = yaml.safe_load(defaults.read_text(encoding="utf-8"))["slm_backend_port"]
    assert str(port) == _readonly("SLM_BACKEND_PORT")
    assert "127.0.0.1:8000" not in _INSTALL.read_text(encoding="utf-8"), "a literal backend port is back"


def test_the_ip_cache_is_not_world_writable() -> None:
    assert _readonly("IP_CACHE_FILE").startswith("/run/"), "the IP cache moved back to a world-writable place"
    assert "/tmp/.autobot_detected_ip" not in _INSTALL.read_text(encoding="utf-8")


def _detect(tmp_path: Path, cached: str, assigned: str) -> subprocess.CompletedProcess:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")
    text = _INSTALL.read_text(encoding="utf-8")
    fn = re.search(r"^detect_local_ip\(\) \{.*?^\}$", text, re.M | re.S)
    assert fn, "install.sh no longer defines detect_local_ip()"
    cache = tmp_path / "ip-cache"
    cache.write_text(cached + "\n", encoding="utf-8")
    script = "\n".join(
        [
            "set -euo pipefail",
            f'IP_CACHE_FILE="{cache}" REINSTALL=false YELLOW="" CYAN="" NC=""',
            # one interface carrying *assigned*, in `ip -4 -o addr show` shape
            f"ip() {{ echo '2: eth0    inet {assigned}/24 brd x scope global eth0'; }}",
            'success() { :; }; fatal() { echo "FATAL: $*"; exit 1; }',
            fn.group(0),
            "detect_local_ip",
        ]
    )
    return subprocess.run([bash, "-c", script], capture_output=True, text=True, timeout=30)


def test_a_cached_ip_still_on_an_interface_is_reused(tmp_path: Path) -> None:
    out = _detect(tmp_path, "192.0.2.10", "192.0.2.10")
    assert out.returncode == 0 and out.stdout.strip() == "192.0.2.10", out.stderr


def test_a_stale_or_planted_cached_ip_is_not_reused(tmp_path: Path) -> None:
    out = _detect(tmp_path, "198.51.100.66", "192.0.2.10")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "192.0.2.10", "an address on no interface here was reused from the cache"
