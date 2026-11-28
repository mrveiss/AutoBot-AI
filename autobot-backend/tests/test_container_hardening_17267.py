# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Container hardening kwargs each Docker client passes to docker, before == after (#17267).

The expected dicts are the literals the two clients hard-coded before the builder
existed; the mock docker client captures what actually reaches ``create``/``run``.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

import services.docker_task_workspace as dtw
from autobot_shared.container_hardening import hardening_kwargs
from secure_sandbox_executor import SandboxConfig, SandboxSecurityLevel, SecureSandboxExecutor

_HARDENING_KEYS = (
    "network_mode",
    "read_only",
    "security_opt",
    "cap_drop",
    "cap_add",
    "mem_limit",
    "memswap_limit",
    "cpu_quota",
    "cpu_period",
    "pids_limit",
)


def _hardening(kwargs: dict) -> dict:
    return {k: kwargs[k] for k in _HARDENING_KEYS if k in kwargs}


def _sandbox_create_kwargs(config: SandboxConfig) -> dict:
    executor = object.__new__(SecureSandboxExecutor)
    executor.docker_client = MagicMock()
    executor.container_prefix = "autobot-sandbox-"
    executor.docker_client.containers.create(**executor._prepare_container_config(["echo", "hi"], config))
    return executor.docker_client.containers.create.call_args.kwargs


@pytest.mark.parametrize(
    ("level", "network", "cap_add"),
    [
        (SandboxSecurityLevel.HIGH, False, []),
        (SandboxSecurityLevel.MEDIUM, False, ["DAC_OVERRIDE", "CHOWN"]),
        (SandboxSecurityLevel.LOW, True, ["DAC_OVERRIDE", "CHOWN", "FOWNER", "SETUID", "SETGID"]),
    ],
)
def test_secure_sandbox_create_kwargs_are_unchanged(level, network, cap_add) -> None:
    cfg = SandboxConfig(security_level=level, enable_network=network, memory_limit="256m", cpu_limit=0.5)
    assert _hardening(_sandbox_create_kwargs(cfg)) == {
        "network_mode": "bridge" if network else "none",
        "read_only": True,
        "security_opt": ["no-new-privileges"],
        "cap_drop": ["ALL"],
        "cap_add": cap_add,
        "mem_limit": "256m",
        "memswap_limit": "256m",
        "cpu_quota": 50000,
        "cpu_period": 100000,
    }


@pytest.mark.parametrize("storage_quota", [False, True])
def test_workspace_run_kwargs_are_unchanged(monkeypatch, storage_quota) -> None:
    monkeypatch.setattr(dtw, "_DISK_QUOTA_ENABLED", storage_quota)
    manager = object.__new__(dtw.TaskWorkspaceManager)
    manager._docker = MagicMock()
    monkeypatch.setattr(manager, "_reap_container_by_name", lambda name: None, raising=False)
    monkeypatch.setattr(time, "time", lambda: 1.0)
    manager._start_container_sync("task-abc", "vol-abc", "img:1")
    kwargs = manager._docker.containers.run.call_args.kwargs
    assert _hardening(kwargs) == {
        "network_mode": "none",
        "read_only": False,
        "security_opt": ["no-new-privileges"],
        "cap_drop": ["ALL"],
        "cap_add": [],
        "mem_limit": dtw._WORKSPACE_MEMORY_LIMIT,
        "memswap_limit": dtw._WORKSPACE_MEMORY_LIMIT,
        "cpu_quota": dtw._WORKSPACE_CPU_QUOTA,
        "cpu_period": 100000,
        "pids_limit": dtw._WORKSPACE_PIDS_LIMIT,
    }


def test_builder_pids_limit_is_omitted_unless_given() -> None:
    base = {"network_mode": "none", "read_only": True, "memory_limit": "1m", "cpu_quota": 1}
    assert "pids_limit" not in hardening_kwargs(**base)
    assert hardening_kwargs(**base, pids_limit=7)["pids_limit"] == 7


def test_execution_builder_defaults_are_fully_hardened() -> None:
    from autobot_shared.container_hardening import (
        CONTAINER_PIDS_LIMIT,
        EXECUTION_MEMORY_LIMIT,
        EXECUTION_TMPFS_SIZE,
        execution_hardening_kwargs,
    )

    assert execution_hardening_kwargs() == {
        "network_mode": "none",
        "read_only": True,
        "tmpfs": {"/tmp": f"rw,noexec,nosuid,size={EXECUTION_TMPFS_SIZE}"},  # nosec B108
        "mem_limit": EXECUTION_MEMORY_LIMIT,
        "memswap_limit": EXECUTION_MEMORY_LIMIT,
        "security_opt": ["no-new-privileges"],
        "cap_drop": ["ALL"],
        "pids_limit": CONTAINER_PIDS_LIMIT,
    }


def test_execution_builder_opt_ins_are_named_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    from autobot_shared.container_hardening import execution_hardening_kwargs

    with caplog.at_level("WARNING"):
        net = execution_hardening_kwargs(memory_limit="64m", network_reason="pip-install")
        rw = execution_hardening_kwargs(writable_root_reason="code-workspace")
    assert net["network_mode"] == "bridge" and net["read_only"] is True
    assert net["mem_limit"] == net["memswap_limit"] == "64m"
    assert rw["network_mode"] == "none" and rw["read_only"] is False
    assert "reason=pip-install" in caplog.text and "reason=code-workspace" in caplog.text


@pytest.mark.parametrize("reason", ["", "  ", "x", "Has Spaces", 5])
def test_execution_builder_rejects_a_nameless_opt_out(reason: object) -> None:
    from autobot_shared.container_hardening import execution_hardening_kwargs

    with pytest.raises(ValueError, match="named reason"):
        execution_hardening_kwargs(network_reason=reason)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="named reason"):
        execution_hardening_kwargs(writable_root_reason=reason)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "key", sorted(__import__("autobot_shared.container_hardening", fromlist=["x"]).DENIED_RUN_KWARGS)
)
def test_each_denied_run_kwarg_is_refused(key: str) -> None:
    from autobot_shared.container_hardening import execution_hardening_kwargs

    with pytest.raises(ValueError, match="not allowed"):
        execution_hardening_kwargs(extra={key: True})


@pytest.mark.parametrize(
    "volumes",
    [
        {"/var/run/docker.sock": {"bind": "/s", "mode": "rw"}},
        {"/run/docker.sock": {"bind": "/s", "mode": "ro"}},
        {"/": {"bind": "/host", "mode": "ro"}},
        {"/var//run/../run": {"bind": "/h", "mode": "ro"}},
        {"//": {"bind": "/h", "mode": "ro"}},
        {"/proc/1/root": {"bind": "/h", "mode": "ro"}},
        {"/proc/self/root": {"bind": "/h", "mode": "ro"}},
        {"/run/containerd/containerd.sock": {"bind": "/h", "mode": "rw"}},
        {"/etc/shadow": {"bind": "/h", "mode": "ro"}},
        {"/sys/fs/cgroup": {"bind": "/h", "mode": "rw"}},
        {"/var/lib/docker/overlay2": {"bind": "/h", "mode": "ro"}},
        {"/root": {"bind": "/h", "mode": "ro"}},
        {"/boot/grub": {"bind": "/h", "mode": "ro"}},
        {"/srv/x.sock": {"bind": "/h", "mode": "rw"}},
        ["/:/host:ro"],
        ["/var/run/docker.sock:/var/run/docker.sock"],
    ],
)
def test_a_bind_of_the_docker_socket_or_host_root_is_refused(volumes: object) -> None:
    from autobot_shared.container_hardening import execution_hardening_kwargs

    with pytest.raises(ValueError, match="not allowed"):
        execution_hardening_kwargs(extra={"volumes": volumes})


@pytest.mark.parametrize(
    "path", ["/srv/work", "/home/sandbox/workspace/t1", "/var/lib/other", "namedvol", "/procfoo", "/etcetera"]
)
def test_a_legitimate_bind_path_still_passes(path: str) -> None:
    from autobot_shared.container_hardening import execution_hardening_kwargs

    assert execution_hardening_kwargs(extra={"volumes": {path: {"bind": "/w", "mode": "ro"}}})["volumes"]


def test_an_ordinary_bind_and_harmless_extras_pass_through_and_cannot_override() -> None:
    from autobot_shared.container_hardening import execution_hardening_kwargs

    out = execution_hardening_kwargs(
        extra={"volumes": {"/srv/work": {"bind": "/w", "mode": "ro"}}, "working_dir": "/w"}
    )
    assert out["volumes"] == {"/srv/work": {"bind": "/w", "mode": "ro"}} and out["working_dir"] == "/w"
    assert execution_hardening_kwargs(extra={"network_mode": "host", "read_only": False})["network_mode"] == "none"
