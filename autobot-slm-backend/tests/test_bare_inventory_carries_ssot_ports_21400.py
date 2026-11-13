# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21400: a command that targets one host with a bare ``-i "<host>,"`` carries the SSOT backend ports.

A bare host-list inventory has no group_vars beside it, so the frontend role's proxy upstream and the
TLS probes would see ``backend_port`` / ``backend_nginx_port`` undefined. Every builder of such a command
goes through ``ansible_utils.bare_inventory_args``.
"""

import asyncio
import json
import re
from pathlib import Path

from autobot_shared.ssot_config import config
from autobot_shared.testfile_names import is_test_filename
from services import ansible_utils
from services.ansible_utils import bare_inventory_args
from services.deployment import DeploymentService

_ROOT = Path(__file__).resolve().parents[1]
# `"-i", "<host>,"`-shaped argv pairs; the one place allowed to spell one is the shared builder.
_BARE_LITERAL = re.compile(r"""["']-i["'],\s*f?["'][^"'\n]*,["']""")
# One fixed `localhost,` provisioning run of a role that reads neither port (python_interpreter): the file
# may spell exactly this many bare-inventory pairs, so a second one added there is still caught.
_FIXED_LOCALHOST = {"api/code_sync.py": 1}


def _ports_in(cmd: list[str]) -> dict:
    """The two port keys out of the command's JSON ``-e`` values (other JSON extra-vars are ignored)."""
    merged: dict = {}
    for i, tok in enumerate(cmd[:-1]):
        if tok == "-e" and cmd[i + 1].startswith("{"):
            merged.update(json.loads(cmd[i + 1]))
    missing = [key for key in _expected() if key not in merged]
    assert not missing, f"port extra-vars missing from the command: {missing}"
    return {key: merged[key] for key in _expected()}


def _service() -> DeploymentService:
    service = DeploymentService.__new__(DeploymentService)
    service._find_ansible_playbook = lambda: "ansible-playbook"
    return service


def _expected() -> dict:
    return {"backend_port": config.port.backend, "backend_nginx_port": config.tls.backend_tls_port}


def test_shared_builder_names_the_host_and_both_ports() -> None:
    cmd = bare_inventory_args("node-a")
    assert cmd[:2] == ["-i", "node-a,"]
    assert _ports_in(cmd) == _expected()


def test_frontend_role_deploy_command_carries_both_ports_from_the_ssot() -> None:
    cmd = _service()._build_ansible_base_command(Path("deploy.yml"), "node-a", ["frontend"])
    assert "target_roles=frontend" in cmd
    assert _ports_in(cmd) == _expected()


def test_enrollment_command_carries_both_ports_from_the_ssot() -> None:
    cmd = _service()._build_enrollment_command(Path("enroll-node.yml"), "node-a", "n1", "autobot", 22, "http://x")
    assert _ports_in(cmd) == _expected()


def test_single_host_playbook_command_carries_both_ports(monkeypatch, tmp_path) -> None:
    captured: list = []

    class _FakeProcess:
        returncode = 0

        async def communicate(self):
            return b"", None

    async def fake_exec(*argv, **_kw):
        captured.extend(argv)
        return _FakeProcess()

    monkeypatch.setattr(ansible_utils.asyncio, "create_subprocess_exec", fake_exec)
    # The empty output fails the recap check; only the argv handed to the subprocess matters here.
    result = asyncio.run(
        ansible_utils.run_single_host_playbook(tmp_path, tmp_path / "p.yml", "node-a", "u", 22, timeout=5)
    )
    assert result is not None
    assert captured[2:4] == ["-i", "node-a,"]
    assert _ports_in(captured) == _expected()


def test_no_command_builder_spells_a_bare_inventory_outside_the_shared_builder() -> None:
    """Matches the ``"-i", "<x>,"`` spelling in Python sources only; a bare inventory built another way is not seen."""
    offenders = []
    for path in sorted(_ROOT.rglob("*.py")):
        rel = path.relative_to(_ROOT).as_posix()
        if rel.startswith(("tests/", "venv/")) or "/tests/" in rel or is_test_filename(rel):
            continue
        if rel == "services/ansible_utils.py":
            continue
        found = [m.group(0) for m in _BARE_LITERAL.finditer(path.read_text(encoding="utf-8", errors="replace"))]
        if len(found) != _FIXED_LOCALHOST.get(rel, 0):
            offenders += [f"{rel}: {text}" for text in found] or [f"{rel}: expected {_FIXED_LOCALHOST[rel]}, found 0"]
    assert offenders == [], f"bare `-i host,` built outside bare_inventory_args: {offenders}"
