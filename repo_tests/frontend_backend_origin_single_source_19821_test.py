# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The GUI's backend port and protocol have one home, and every deploy surface derives from it (#19821).

**The one value.** The backend port is `AutoBotConfig.port.backend` in `autobot_shared/ssot_config.py`
(`Field(default=…, alias="AUTOBOT_BACKEND_PORT")`). Every other statement of it must equal it or
read it:

* `PORT_DEFAULTS.backend` in `autobot-frontend/src/config/ssot-config.ts` equals it (the GUI's
  fallback when `VITE_BACKEND_PORT` is unset);
* both env templates, `.env.example` and `autobot-frontend/.env.example`, set `VITE_BACKEND_PORT` to
  it and agree on `VITE_HTTP_PROTOCOL`;
* the Ansible inventory's `backend_port` equals it;
* no Ansible playbook, role, systemd unit or Docker file writes `VITE_BACKEND_PORT` as a number;
  each reads `{{ backend_port }}` or an `${AUTOBOT_BACKEND_PORT}` variable.

`AppConfig.js` holds no protocol or port literal: the backend's come from `getConfig()`, other
services' ports from `PORT_DEFAULTS` and their protocol from `INTERNAL_SERVICE_PROTOCOL`
(`constants/network.ts`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from repo_tests._paths import repo_root

_SSOT_PY = "autobot_shared/ssot_config.py"
_SSOT_TS = "autobot-frontend/src/config/ssot-config.ts"
_TEMPLATES = (".env.example", "autobot-frontend/.env.example")
_INVENTORY = "autobot-slm-backend/ansible/inventory/production.yml"
_APP_CONFIG = "autobot-frontend/src/config/AppConfig.js"
_DEPLOY_ROOTS = ("autobot-slm-backend/ansible", "autobot-infrastructure/shared/scripts/systemd", "docker")
_DEPLOY_SUFFIXES = {".yml", ".yaml", ".j2", ".service", ".env", ""}

_LITERAL_PORT = re.compile(r"""VITE_BACKEND_PORT\s*[=:]\s*["']?\d""")
_APP_LITERAL = re.compile(r"""['"](?:https?|\d{2,5})['"]""")


def _text(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def ssot_backend_port() -> int:
    """The default of the backend port field in the Python SSOT."""
    m = re.search(r'backend:\s*int\s*=\s*Field\(default=(\d+),\s*alias="AUTOBOT_BACKEND_PORT"\)', _text(_SSOT_PY))
    assert m, f"{_SSOT_PY} no longer declares the backend port field this guard reads"
    return int(m.group(1))


def env_value(text: str, key: str) -> str | None:
    """The last uncommented `KEY=value` in an env file."""
    found = re.findall(rf"^\s*{key}=([^\s#]*)", text, re.M)
    return found[-1] if found else None


def literal_port_writes(text: str) -> list[str]:
    """Lines that write `VITE_BACKEND_PORT` as a number, comment lines skipped."""
    return [
        line.strip()
        for line in text.splitlines()
        if _LITERAL_PORT.search(line) and not line.lstrip().startswith(("#", "//"))
    ]


def _deploy_files() -> list[Path]:
    root = repo_root()
    out = []
    for rel in _DEPLOY_ROOTS:
        for path in sorted((root / rel).rglob("*")):
            name_ok = path.suffix in _DEPLOY_SUFFIXES or path.name.startswith("Dockerfile")
            if path.is_file() and name_ok:
                out.append(path)
    return out


class TestTheDetectorsWork:
    def test_a_literal_port_write_is_found_in_each_form(self) -> None:
        text = '- VITE_BACKEND_PORT=8001\n  VITE_BACKEND_PORT: "8443"\nexport VITE_BACKEND_PORT=80\n'
        assert len(literal_port_writes(text)) == 3

    def test_a_derived_write_and_a_comment_are_not(self) -> None:
        text = (
            "- VITE_BACKEND_PORT={{ backend_port }}\n"
            '  VITE_BACKEND_PORT: "{{ backend_port }}"\n'
            "VITE_BACKEND_PORT=${AUTOBOT_BACKEND_PORT}\n"
            "# VITE_BACKEND_PORT=8001 is the default\n"
        )
        assert literal_port_writes(text) == []

    def test_env_value_reads_the_live_line(self) -> None:
        assert env_value("# VITE_BACKEND_PORT=1\nVITE_BACKEND_PORT=8001\n", "VITE_BACKEND_PORT") == "8001"


def test_the_gui_fallback_equals_the_ssot() -> None:
    m = re.search(r"export const PORT_DEFAULTS = \{\s*backend:\s*(\d+)", _text(_SSOT_TS))
    assert m and int(m.group(1)) == ssot_backend_port()


@pytest.mark.parametrize("rel", _TEMPLATES)
def test_each_env_template_sets_the_ssot_backend_port(rel: str) -> None:
    assert env_value(_text(rel), "VITE_BACKEND_PORT") == str(ssot_backend_port()), rel


def test_the_env_templates_agree_on_the_protocol() -> None:
    protocols = {rel: env_value(_text(rel), "VITE_HTTP_PROTOCOL") for rel in _TEMPLATES}
    assert len(set(protocols.values())) == 1 and None not in protocols.values(), protocols


def test_the_inventory_backend_port_is_the_ssot_one() -> None:
    m = re.search(r"^\s*backend_port:\s*(\d+)\s*$", _text(_INVENTORY), re.M)
    assert m and int(m.group(1)) == ssot_backend_port()


def test_no_deploy_file_writes_the_gui_backend_port_as_a_number() -> None:
    files = _deploy_files()
    assert len(files) > 50, f"only {len(files)} deploy files found; a moved folder reads as clean"
    offenders = {
        p.relative_to(repo_root()).as_posix(): w
        for p in files
        if (w := literal_port_writes(p.read_text(encoding="utf-8", errors="replace")))
    }
    assert (
        offenders == {}
    ), f"derive VITE_BACKEND_PORT from {{{{ backend_port }}}} or ${{AUTOBOT_BACKEND_PORT}}: {offenders}"


def test_app_config_holds_no_protocol_or_port_literal() -> None:
    lines = [ln.strip() for ln in _text(_APP_CONFIG).splitlines() if not ln.lstrip().startswith(("//", "*"))]
    found = [ln for ln in lines if _APP_LITERAL.search(ln)]
    assert found == [], found
