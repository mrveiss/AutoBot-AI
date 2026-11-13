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
_BARE_LITERAL = re.compile(r"""["']-i["'],\s*f?["']([^"'\n]*),["']""")
# One fixed `localhost,` provisioning run of a role that reads neither port (python_interpreter): the file
# may spell exactly these bare-inventory hosts, so a second one, or one naming another host, is still caught.
_FIXED_LOCALHOST = {"api/code_sync.py": ["localhost"]}


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


def _bare_offenders(rel: str, text: str) -> list[str]:
    """The bare ``-i "<host>,"`` spellings in *text* beyond the file's permitted hosts (host and count)."""
    unmatched = list(_FIXED_LOCALHOST.get(rel, []))
    offenders = []
    for match in _BARE_LITERAL.finditer(text):
        if match.group(1) in unmatched:
            unmatched.remove(match.group(1))
        else:
            offenders.append(f"{rel}: {match.group(0)}")
    return offenders + [f"{rel}: expected a bare inventory for {host!r}, found none" for host in unmatched]


def test_no_command_builder_spells_a_bare_inventory_outside_the_shared_builder() -> None:
    """Matches the ``"-i", "<x>,"`` spelling in Python sources only; a bare inventory built another way is not seen."""
    offenders = []
    for path in sorted(_ROOT.rglob("*.py")):
        rel = path.relative_to(_ROOT).as_posix()
        if rel.startswith(("tests/", "venv/")) or "/tests/" in rel or is_test_filename(rel):
            continue
        if rel == "services/ansible_utils.py":
            continue
        offenders += _bare_offenders(rel, path.read_text(encoding="utf-8", errors="replace"))
    assert offenders == [], f"bare `-i host,` built outside bare_inventory_args: {offenders}"


def test_contrast_the_permitted_localhost_run_passes_and_any_other_host_or_a_second_is_rejected() -> None:
    local = 'cmd += ["--tags", "x", "-i", "localhost,", "--connection", "local"]'
    assert _bare_offenders("api/code_sync.py", local) == []
    remote = 'cmd += ["-i", "10.0.0.5,"]'
    assert _bare_offenders("api/code_sync.py", local + remote) != []
    assert _bare_offenders("api/code_sync.py", remote) != [], "a remote host takes the place of the permitted one"
    assert _bare_offenders("api/code_sync.py", local + local) != [], "a second localhost run is still caught"
    assert _bare_offenders("api/other.py", local) != [], "the exemption belongs to the one file"
    assert _bare_offenders("api/code_sync.py", 'cmd += ["-i", f"{host},"]') != []
