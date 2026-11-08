# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pid whose identity differs from the run's stamp is logged, not silently COMPLETED (GH#20466)."""

import logging
from unittest.mock import patch

import psutil

from llc.adapters.subprocess_support import probe_pid_identity
from llc.models.enums import LLCRunStatus

_SRC = "llc.adapters.subprocess_support"


def test_identity_mismatch_logs_warning_with_pid_expected_and_actual(caplog) -> None:
    with patch(f"{_SRC}._start_stamp", return_value=222.5), caplog.at_level(logging.WARNING, logger=_SRC):
        status = probe_pid_identity(4242, 111.5)
    assert status.status is LLCRunStatus.COMPLETED
    msgs = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(msgs) == 1
    assert "4242" in msgs[0] and "111.5" in msgs[0] and "222.5" in msgs[0]


def test_matching_identity_logs_nothing(caplog) -> None:
    with patch(f"{_SRC}._start_stamp", return_value=111.5), caplog.at_level(logging.DEBUG, logger=_SRC):
        assert probe_pid_identity(4242, 111.5).status is LLCRunStatus.RUNNING
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_vanished_pid_is_a_normal_exit_without_warning(caplog) -> None:
    with (
        patch(f"{_SRC}._start_stamp", side_effect=psutil.NoSuchProcess(4242)),
        caplog.at_level(logging.WARNING, logger=_SRC),
    ):
        assert probe_pid_identity(4242, 111.5).status is LLCRunStatus.COMPLETED
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
