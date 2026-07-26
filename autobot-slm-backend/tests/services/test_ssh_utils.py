# Copyright 2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the canonical ssh-key usability gate (#11793).

``Path(SSH_KEY_PATH).exists()`` propagated PermissionError when the key's
parent directory was unreadable, crashing every ssh command build in
sync_orchestrator / code_distributor / nodes_execution / nodes / code_sync.
``_ssh_key_usable`` must degrade instead: False -> no ``-i`` flag (default
ssh identity), with a single actionable WARNING per path.
"""

import importlib
import logging
import sys
from unittest.mock import patch

import pytest

import services.ssh_utils as ssh_utils
from services.ssh_utils import _ssh_key_usable, build_ssh_base_cmd

# ── Load the REAL services.code_distributor (same pattern) ───────────────────
_CD_KEY = "services.code_distributor"
_orig_cd = sys.modules.get(_CD_KEY)
sys.modules.pop(_CD_KEY, None)
try:
    _cd_mod = importlib.import_module(_CD_KEY)
finally:
    if _orig_cd is not None:
        sys.modules[_CD_KEY] = _orig_cd
    else:
        sys.modules.pop(_CD_KEY, None)

CodeDistributor = _cd_mod.CodeDistributor

_LOGGER_NAME = "services.ssh_utils"


@pytest.fixture(autouse=True)
def _reset_warned_paths():
    """Each test starts with a clean warn-once ledger."""
    ssh_utils._WARNED_PATHS.clear()
    yield
    ssh_utils._WARNED_PATHS.clear()


def _warnings(caplog) -> list:
    return [r for r in caplog.records if r.name == _LOGGER_NAME and r.levelno == logging.WARNING]


# ── unit: _ssh_key_usable ─────────────────────────────────────────────────────


def test_readable_key_returns_true(tmp_path, caplog):
    key = tmp_path / "autobot_key"
    key.write_text("fake-key-material", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        assert _ssh_key_usable(str(key)) is True
    assert _warnings(caplog) == []


def test_missing_key_returns_false_without_warning(tmp_path, caplog):
    with caplog.at_level(logging.WARNING, logger=_LOGGER_NAME):
        assert _ssh_key_usable(str(tmp_path / "absent_key")) is False
    assert _warnings(caplog) == []


def test_permissionerror_returns_false_and_warns_once(caplog):
    """Unreadable parent dir (EACCES from Path.exists) -> False + ONE warning."""
    key = "/unreadable-dir/.ssh/autobot_key"
    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER_NAME),
        patch.object(ssh_utils, "Path") as mock_path,
    ):
        mock_path.return_value.exists.side_effect = PermissionError(13, "Permission denied")
        assert _ssh_key_usable(key) is False
        assert _ssh_key_usable(key) is False  # second call: no duplicate log

    warnings = _warnings(caplog)
    assert len(warnings) == 1
    message = warnings[0].getMessage()
    assert key in message
    assert "errno 13" in message
    assert "falling back to default ssh identity" in message


def test_os_access_error_returns_false_and_warns_once(tmp_path, caplog):
    """OSError from os.access itself is also degraded, not propagated."""
    key = tmp_path / "autobot_key"
    key.write_text("fake-key-material", encoding="utf-8")

    def _raise(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER_NAME),
        patch.object(ssh_utils.os, "access", _raise),
    ):
        assert _ssh_key_usable(str(key)) is False
        assert _ssh_key_usable(str(key)) is False

    assert len(_warnings(caplog)) == 1


def test_existing_unreadable_key_returns_false_and_warns(tmp_path, caplog):
    """Key exists but is not readable (os.access False) -> False + warning."""
    key = tmp_path / "autobot_key"
    key.write_text("fake-key-material", encoding="utf-8")
    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER_NAME),
        patch.object(ssh_utils.os, "access", lambda *_a, **_k: False),
    ):
        assert _ssh_key_usable(str(key)) is False

    warnings = _warnings(caplog)
    assert len(warnings) == 1
    assert "not readable" in warnings[0].getMessage()


def test_warn_once_is_per_path(caplog):
    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER_NAME),
        patch.object(ssh_utils, "Path") as mock_path,
    ):
        mock_path.return_value.exists.side_effect = PermissionError(13, "Permission denied")
        assert _ssh_key_usable("/dir-a/key") is False
        assert _ssh_key_usable("/dir-b/key") is False

    assert len(_warnings(caplog)) == 2


# ── integration: previously-crashing site degrades ────────────────────────────


def test_build_ssh_command_degrades_on_permissionerror(caplog):
    """The exact site from the #11793 traceback (now the shared
    ``build_ssh_base_cmd``, used by both api/nodes.py and
    services/sync_orchestrator.py since #12690) no longer raises: the command
    is built WITHOUT -i and a single WARNING is logged."""
    key = "/unreadable-home/.ssh/autobot_key"
    with (
        caplog.at_level(logging.WARNING, logger=_LOGGER_NAME),
        patch.object(ssh_utils, "Path") as mock_path,
    ):
        mock_path.return_value.exists.side_effect = PermissionError(13, "Permission denied")
        cmd = build_ssh_base_cmd("10.0.0.5", "autobot", 2222, key)

    assert "-i" not in cmd
    assert cmd[0] == "ssh"
    assert cmd[-1] == "autobot@10.0.0.5"
    assert len(_warnings(caplog)) == 1


def test_code_distributor_ssh_argv_is_wellformed(tmp_path):
    """Regression guard for the stray ``-o`` token fixed with #11793 (same
    class as #10277): every ``-o`` in CodeDistributor._build_ssh_command must
    be followed by a ``key=value`` token, and the ssh-key gate is the shared
    helper (degrades on a missing key)."""
    distributor = CodeDistributor.__new__(CodeDistributor)
    with patch.object(_cd_mod, "SSH_KEY_PATH", str(tmp_path / "absent_key")):
        cmd = distributor._build_ssh_command(2222)

    assert "-i" not in cmd
    for idx, token in enumerate(cmd):
        if token == "-o":
            assert idx + 1 < len(cmd), f"trailing -o with no argument: {cmd!r}"
            value = cmd[idx + 1]
            assert "=" in value and not value.startswith("-"), f"-o not followed by key=value: {value!r} in {cmd!r}"
