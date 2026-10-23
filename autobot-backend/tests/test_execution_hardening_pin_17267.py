# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every ``containers.run`` in the execution backends: full kwargs per site (#17267).

Option (b): each site carries the whole shared execution hardening (memory cap with equal
swap cap, no network, read-only root with a noexec tmpfs, privilege floor). The mock
collection only records the call; ``run`` takes ``**kwargs``, so the pins assert exact dicts.
"""

from __future__ import annotations

from unittest.mock import MagicMock, create_autospec, patch

import pytest

# The docker SDK is a declared CI dependency (requirements-ci/utilities.txt); a guard in
# repo_tests/container_hardening_single_source_17267_test.py fails if it stops being
# declared, so this skip can only fire in a local interpreter that lacks the SDK, never
# silently in CI.
docker = pytest.importorskip("docker", reason="docker SDK not installed in this interpreter")
ContainerCollection = pytest.importorskip("docker.models.containers").ContainerCollection

import services.execution.docker_backend as db
from services.execution.base_backend import ExecutionTask, ResourceLimits
from services.execution.container_pool import WarmContainerPool

_FLOOR = {"security_opt": ["no-new-privileges"], "cap_drop": ["ALL"]}


def _hardened(memory: str = "512m", *, network: str = "none", read_only: bool = True) -> dict:
    from autobot_shared.container_hardening import CONTAINER_PIDS_LIMIT, EXECUTION_TMPFS_SIZE

    return {
        **_FLOOR,
        "pids_limit": CONTAINER_PIDS_LIMIT,
        "network_mode": network,
        "read_only": read_only,
        "tmpfs": {"/tmp": f"rw,noexec,nosuid,size={EXECUTION_TMPFS_SIZE}"},  # nosec B108
        "mem_limit": memory,
        "memswap_limit": memory,
    }


def _client():
    client = MagicMock(spec=docker.DockerClient)
    client.containers = create_autospec(ContainerCollection, instance=True)
    container = MagicMock()
    container.id = "cid"
    container.short_id = "cid"
    container.wait.return_value = {"StatusCode": 0}
    container.logs.return_value = b"ok"
    client.containers.run.return_value = container
    return client


def _backend(client):
    with patch.object(db.docker, "from_env", return_value=client):
        return db.DockerBackend(use_pool=False, snapshot_index=MagicMock())


@pytest.mark.asyncio
async def test_cold_start_run_kwargs() -> None:
    client = _client()
    task = ExecutionTask(task_id="t1", code="print(1)", language="python", env_vars={"AUTOBOT_X": "1"})
    await _backend(client)._execute_cold(task, "python:3.10-slim")
    args, kwargs = client.containers.run.call_args
    assert args[0] == "python:3.10-slim"
    assert kwargs == {
        "detach": True,
        "nano_cpus": 1_000_000_000,
        "environment": kwargs["environment"],
        "remove": False,
        **_hardened("512m"),
    }
    assert "volumes" not in kwargs


@pytest.mark.asyncio
async def test_snapshot_restore_run_kwargs() -> None:
    client = _client()
    backend = _backend(client)
    backend._snapshot_index.get.return_value = MagicMock(user_id="", image_name="snap:1", session_id="s")
    await backend.restore("snap-id", "anyone")
    args, kwargs = client.containers.run.call_args
    assert args == ("snap:1", "sleep infinity")
    assert kwargs == {"detach": True, "remove": False, **_hardened()}


@pytest.mark.asyncio
async def test_warm_pool_run_kwargs() -> None:
    client = _client()
    pool = WarmContainerPool(docker_client=client, image="python:3.10-slim", pool_size=1)
    await pool._create_warm_container()
    args, kwargs = client.containers.run.call_args
    assert args == ("python:3.10-slim", ["sleep", "infinity"])
    assert kwargs == {"detach": True, "remove": False, **_hardened()}


@pytest.mark.asyncio
async def test_cold_start_memory_follows_the_task_and_swap_matches() -> None:
    client = _client()
    task = ExecutionTask(task_id="t2", code="x", resource_limits=ResourceLimits(memory_mb=128))
    await _backend(client)._execute_cold(task, "i")
    kwargs = client.containers.run.call_args.kwargs
    assert kwargs["mem_limit"] == kwargs["memswap_limit"] == "128m"


@pytest.mark.asyncio
async def test_warm_pool_caller_kwargs_survive_but_cannot_weaken_the_hardening() -> None:
    client = _client()
    caller = {"working_dir": "/w", "network_mode": "bridge", "read_only": False, "cap_drop": [], "mem_limit": "9g"}
    pool = WarmContainerPool(docker_client=client, image="i", pool_size=1, container_kwargs=caller)
    await pool._create_warm_container()
    kwargs = client.containers.run.call_args.kwargs
    assert kwargs["working_dir"] == "/w"
    assert kwargs == {"detach": True, "remove": False, "working_dir": "/w", **_hardened()}


@pytest.mark.asyncio
async def test_warm_pool_named_opt_ins_are_the_only_way_to_drop_a_default() -> None:
    client = _client()
    pool = WarmContainerPool(
        docker_client=client,
        image="i",
        pool_size=1,
        network_reason="pip-install",
        writable_root_reason="code-workspace",
    )
    await pool._create_warm_container()
    kwargs = client.containers.run.call_args.kwargs
    assert kwargs == {"detach": True, "remove": False, **_hardened(network="bridge", read_only=False)}


def test_a_nameless_opt_in_fails_before_any_container_is_started() -> None:
    client = _client()
    pool = WarmContainerPool(docker_client=client, image="i", pool_size=1, network_reason="")
    with pytest.raises(ValueError, match="named reason"):
        pool._run_kwargs()
    client.containers.run.assert_not_called()


@pytest.mark.asyncio
async def test_warm_pool_refuses_a_privileged_caller_kwarg_and_the_error_propagates() -> None:
    client = _client()
    pool = WarmContainerPool(docker_client=client, image="i", pool_size=1, container_kwargs={"privileged": True})
    with pytest.raises(ValueError, match="not allowed"):
        pool._run_kwargs()
    with pytest.raises(ValueError, match="not allowed"):
        await pool._create_warm_container()
    client.containers.run.assert_not_called()


#: Keys ``ContainerCollection.run`` consumes itself before building the create/host config.
_RUN_ONLY_KWARGS = frozenset({"detach", "remove", "stdout", "stderr"})


def _accepted_by_docker_py() -> set[str]:
    from docker.models.containers import RUN_CREATE_KWARGS, RUN_HOST_CONFIG_KWARGS

    return set(RUN_CREATE_KWARGS) | set(RUN_HOST_CONFIG_KWARGS) | _RUN_ONLY_KWARGS


@pytest.mark.asyncio
async def test_every_run_site_passes_only_kwargs_docker_py_accepts() -> None:
    client = _client()
    backend = _backend(client)
    await backend._execute_cold(ExecutionTask(task_id="t", code="x"), "i")
    cold = set(client.containers.run.call_args.kwargs)
    backend._snapshot_index.get.return_value = MagicMock(user_id="", image_name="s:1", session_id="s")
    await backend.restore("sid", "anyone")
    restore = set(client.containers.run.call_args.kwargs)
    pool = WarmContainerPool(docker_client=client, image="i", pool_size=1)
    await pool._create_warm_container()
    warm = set(client.containers.run.call_args.kwargs)
    accepted = _accepted_by_docker_py()
    for label, keys in (("cold", cold), ("restore", restore), ("pool", warm)):
        assert keys <= accepted, f"{label}: docker-py would raise TypeError on {sorted(keys - accepted)}"


@pytest.mark.asyncio
async def test_cold_start_cpu_limit_is_nano_cpus_not_cpus() -> None:
    client = _client()
    task = ExecutionTask(task_id="t", code="x", resource_limits=ResourceLimits(cpu_cores=0.5))
    await _backend(client)._execute_cold(task, "i")
    kwargs = client.containers.run.call_args.kwargs
    assert kwargs["nano_cpus"] == 500_000_000 and "cpus" not in kwargs


@pytest.mark.asyncio
async def test_warm_pool_start_raises_on_a_refused_kwarg_instead_of_warming_nothing() -> None:
    client = _client()
    pool = WarmContainerPool(docker_client=client, image="i", pool_size=2, container_kwargs={"cap_add": ["SYS_ADMIN"]})
    with pytest.raises(ValueError, match="not allowed"):
        await pool.start()
    client.containers.run.assert_not_called()
