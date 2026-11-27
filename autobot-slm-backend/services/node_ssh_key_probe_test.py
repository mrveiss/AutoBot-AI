# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The key probe and its key-only ssh argv: the SLM's own key and nothing else (#20046, #22033).

The probe is loaded with the REAL ``ssh_utils`` argv builder and a fake ``spawn_ssh``. The identity checks use a
fake ssh that offers what OpenSSH would: every ``-i`` key, plus an ``IdentityFile`` from ssh_config unless ``-F``
points at the null device. Each check has its contrast: the SLM key that passes, the other identity that must not.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_OTHER_IDENTITY = "~/.ssh/other_identity"


def _load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, _ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _node() -> SimpleNamespace:
    return SimpleNamespace(node_id="node-a", ip_address="192.0.2.10", ssh_user="autobot", ssh_port=22)


@pytest.fixture
def slm_key(tmp_path) -> str:
    key = tmp_path / "slm_key"
    key.write_text("key", encoding="utf-8")
    return str(key)


def _load_probe(spawn, key: str):
    """The probe module wired to the real argv builder, a fake ``spawn_ssh`` and *key* as the SLM key."""
    with patch.dict(sys.modules):
        real_utils = _load("ssh_utils_under_key_probe_test", "services/ssh_utils.py")
        sys.modules["services.ssh_utils"] = real_utils
        sys.modules["services.orchestrator_ssh"] = SimpleNamespace(spawn_ssh=spawn)
        probe = _load("node_ssh_key_probe_under_key_probe_test", "services/node_ssh_key_probe.py")
    probe.ssot_config = SimpleNamespace(path=SimpleNamespace(ssh_key=key))
    return probe


def _node_accepting(accepted: str):
    """A fake ssh to a node that accepts only *accepted*; it offers what OpenSSH would offer for the argv."""

    async def spawn(argv, **_kw):
        offered = {argv[i + 1] for i, part in enumerate(argv) if part == "-i"}
        config_dropped = "-F" in argv and argv[argv.index("-F") + 1] == os.devnull
        if not config_dropped:
            offered.add(_OTHER_IDENTITY)  # an IdentityFile an ssh_config could add for this host
        return (0 if accepted in offered else 255), b"", b""

    return spawn


async def test_a_node_that_rejects_the_slm_key_fails_even_if_another_identity_would_pass(slm_key) -> None:
    probe = _load_probe(_node_accepting(_OTHER_IDENTITY), slm_key)
    assert await probe.key_auth_and_sudo_work(_node()) is False


async def test_a_node_that_accepts_only_the_slm_key_passes(slm_key) -> None:
    probe = _load_probe(_node_accepting(slm_key), slm_key)
    assert await probe.key_auth_and_sudo_work(_node()) is True


async def test_an_unusable_slm_key_fails_without_falling_back_to_default_identities(tmp_path) -> None:
    spawn = AsyncMock(return_value=(0, b"", b""))
    probe = _load_probe(spawn, str(tmp_path / "missing_key"))
    assert await probe.key_auth_and_sudo_work(_node()) is False
    spawn.assert_not_awaited()
    with pytest.raises(probe.SlmKeyUnusable):
        probe.key_only_ssh_command(_node())


async def test_the_probe_runs_a_key_only_passwordless_sudo_check(slm_key) -> None:
    spawn = AsyncMock(return_value=(0, b"", b""))
    probe = _load_probe(spawn, slm_key)
    assert await probe.key_auth_and_sudo_work(_node()) is True
    argv = spawn.await_args.args[0]
    assert {"BatchMode=yes", "PasswordAuthentication=no", "IdentitiesOnly=yes"} <= set(argv) and argv[
        -1
    ] == "sudo -n -k /bin/sh -c true"
    assert {"ControlMaster=no", "ControlPath=none"} <= set(argv)  # a live master must not vouch for the key
    assert spawn.await_args.kwargs["timeout"] == probe.KEY_PROBE_TIMEOUT_SECONDS <= 60
    assert "sshpass" not in argv and "autobot@192.0.2.10" in argv
    assert argv[argv.index("-i") + 1] == slm_key and argv[argv.index("-F") + 1] == os.devnull
    assert "StrictHostKeyChecking=accept-new" in argv  # the host-key options of the builder are kept


@pytest.mark.parametrize("outcome", [(255, b"", b"denied"), (1, b"", b""), TimeoutError(), OSError("no ssh")])
async def test_the_probe_fails_closed(outcome, slm_key) -> None:
    spawn = AsyncMock(side_effect=outcome) if isinstance(outcome, Exception) else AsyncMock(return_value=outcome)
    assert await _load_probe(spawn, slm_key).key_auth_and_sudo_work(_node()) is False
