# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The NPU worker config path must not depend on CWD (#12857).

`NPUWorkerManager` defaulted to `Path("config/npu_workers.yaml")` and writes a
bootstrap config during initialize. Because the path was CWD-relative, that
write landed wherever the process happened to be running:

    api/websockets.py:776  npu_workers_websocket_endpoint
      -> _send_initial_worker_list
        -> async_initializable.initialize
          -> NPUWorkerManager.save_worker_config()
            -> writes ./config/npu_workers.yaml

Under pytest that was the repo working tree, leaving an untracked file that
blocked `git worktree remove`. In production it depends on the unit's
WorkingDirectory, which is worse: the same code writes somewhere different.
"""

import os
from pathlib import Path

import pytest

from constants.path_constants import PATH
from services.npu_worker_manager import NPUWorkerManager


def test_default_config_path_is_absolute():
    """A relative default means the target depends on where the process started."""
    mgr = NPUWorkerManager()

    assert mgr.config_file.is_absolute(), (
        f"default config path {mgr.config_file} is relative — a bootstrap write "
        "would land wherever CWD happens to be"
    )


def test_default_config_path_is_stable_across_cwd(tmp_path, monkeypatch):
    """The whole bug: the same manager resolved to different files per CWD."""
    first = NPUWorkerManager().config_file

    monkeypatch.chdir(tmp_path)
    second = NPUWorkerManager().config_file

    assert first == second, "config path changed with CWD"


def test_default_config_path_keeps_the_conventional_location():
    """Anchoring must not relocate the file — existing installs read <backend>/config/."""
    mgr = NPUWorkerManager()

    assert mgr.config_file == PATH.BACKEND_DIR / "config" / "npu_workers.yaml"


def test_explicit_config_file_is_still_honoured(tmp_path):
    """Callers and tests must still be able to point it somewhere else."""
    target = tmp_path / "custom.yaml"

    assert NPUWorkerManager(config_file=target).config_file == target


def test_instantiating_from_a_foreign_cwd_does_not_target_that_directory(tmp_path, monkeypatch):
    """Guards the specific symptom: a stray write must not land in the caller's CWD."""
    monkeypatch.chdir(tmp_path)
    mgr = NPUWorkerManager()

    assert Path(os.getcwd()) not in mgr.config_file.parents
    assert not str(mgr.config_file).startswith(str(tmp_path))


@pytest.mark.parametrize(
    "test_file",
    [
        "services/npu_worker_manager_pulse_test.py",
        "services/test_npu_worker_events.py",
        "services/test_npu_worker_config_load_12526.py",
    ],
)
def test_no_test_names_the_real_repo_config(test_file):
    """A unit test must never name a config file it could overwrite."""
    source = (PATH.BACKEND_DIR / test_file).read_text(encoding="utf-8")

    assert 'Path("config/npu_workers.yaml")' not in source, (
        f"{test_file} points a manager at the real repo config; a save would "
        "write into the working tree"
    )
