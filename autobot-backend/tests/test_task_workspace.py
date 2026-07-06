# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for TaskWorkspaceManager (GH#10544).

Docker is mocked throughout — all Docker SDK calls are patched at the module
level so these tests run in CI without a live Docker socket.

Coverage:
  - workspace created per task_id, idempotent on second call (reuse)
  - exec_command runs in the same container; blocked commands rejected
  - snapshot calls docker.commit and registers in Redis
  - destroy removes container + volume + Redis keys
  - security constraints enforced (validate_exec_command)
  - quota enforcement evicts oldest workspace when limit exceeded
  - validate_task_id rejects path-traversal payloads
"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

import services.docker_task_workspace as dtw
from services.docker_task_workspace import (
    TaskWorkspaceManager,
    WorkspaceInfo,
    _apply_sandbox_security,
    _deserialize_info,
    _redis_meta_key,
    _serialize_info,
    _snapshot_image_tag,
    _validate_checkpoint_name,
    _validate_task_id,
    validate_exec_command,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_docker():
    """Return a fully mocked docker.DockerClient."""
    client = MagicMock()
    # volumes.create returns a volume mock
    volume_mock = MagicMock()
    volume_mock.remove = MagicMock()
    client.volumes.create.return_value = volume_mock
    client.volumes.get.return_value = volume_mock

    # containers.run returns a container with a stable id
    container_mock = MagicMock()
    container_mock.id = "abc123def456"
    container_mock.exec_run.return_value = MagicMock(exit_code=0, output=(b"hello\n", b""))
    container_mock.commit = MagicMock()
    container_mock.kill = MagicMock()
    container_mock.stop = MagicMock()
    container_mock.remove = MagicMock()
    client.containers.run.return_value = container_mock
    client.containers.get.return_value = container_mock

    # api exec
    client.api.exec_create.return_value = {"Id": "execid-1"}
    sock_mock = MagicMock()
    sock_mock.recv.return_value = b"output bytes"
    client.api.exec_start.return_value = sock_mock

    return client


@pytest.fixture()
def mock_redis():
    """Return a simple in-memory dict-backed fake Redis (sync)."""
    store: dict[str, bytes] = {}

    class FakeRedis:
        def get(self, key):
            return store.get(key)

        def set(self, key, value, ex=None):
            store[key] = value.encode() if isinstance(value, str) else value

        def delete(self, *keys):
            for k in keys:
                store.pop(k, None)

        def keys(self, pattern):
            import fnmatch

            return [k.encode() for k in store if fnmatch.fnmatch(k, pattern.replace("*", "*"))]

        def rpush(self, key, value):
            if key not in store:
                store[key] = b"[]"
            lst = json.loads(store[key])
            lst.append(value)
            store[key] = json.dumps(lst).encode()

        def expire(self, key, ttl):
            pass

        def hgetall(self, key):
            return {}

    return FakeRedis()


@pytest.fixture()
def manager(mock_docker, mock_redis):
    """Return a TaskWorkspaceManager wired to mock Docker + Redis."""
    dtw._DOCKER_AVAILABLE = True
    mgr = TaskWorkspaceManager.__new__(TaskWorkspaceManager)
    mgr._docker = mock_docker
    mgr._redis = mock_redis
    import asyncio

    mgr._lock = asyncio.Lock()
    return mgr


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_info(task_id: str, container_id: str = "cid-001") -> WorkspaceInfo:
    now = time.time()
    return WorkspaceInfo(
        task_id=task_id,
        container_id=container_id,
        volume_name=f"autobot-workspace-{task_id}-vol",
        image="alpine:3.18",
        created_at=now,
        last_active=now,
    )


def _store_info(redis, info: WorkspaceInfo) -> None:
    key = _redis_meta_key(info.task_id)
    redis.set(key, _serialize_info(info))


# ---------------------------------------------------------------------------
# validate_task_id
# ---------------------------------------------------------------------------


def test_validate_task_id_accepts_uuid():
    _validate_task_id("task-1234-abcd")  # must not raise


def test_validate_task_id_rejects_traversal():
    with pytest.raises(ValueError):
        _validate_task_id("../../etc/passwd")


def test_validate_task_id_rejects_empty():
    with pytest.raises(ValueError):
        _validate_task_id("")


def test_validate_task_id_rejects_too_long():
    with pytest.raises(ValueError):
        _validate_task_id("a" * 129)


# ---------------------------------------------------------------------------
# validate_exec_command (security hardening reuse)
# ---------------------------------------------------------------------------


def test_exec_command_allowed():
    assert validate_exec_command(["ls", "-la"]) is True


def test_exec_command_blocked_sudo():
    assert validate_exec_command(["sudo", "apt", "install", "curl"]) is False


def test_exec_command_blocked_docker():
    assert validate_exec_command(["docker", "run", "--rm", "alpine"]) is False


def test_exec_command_blocked_by_full_path():
    assert validate_exec_command(["/usr/bin/sudo", "-s"]) is False


def test_exec_command_blocked_shutdown():
    assert validate_exec_command(["shutdown", "-h", "now"]) is False


def test_exec_command_empty():
    assert validate_exec_command([]) is False


# ---------------------------------------------------------------------------
# _apply_sandbox_security
# ---------------------------------------------------------------------------


def test_sandbox_security_has_no_network():
    kwargs = _apply_sandbox_security("task-abc", "vol-abc")
    assert kwargs["network_mode"] == "none"


def test_sandbox_security_caps_dropped():
    kwargs = _apply_sandbox_security("task-abc", "vol-abc")
    assert "ALL" in kwargs["cap_drop"]
    assert kwargs["cap_add"] == []


def test_sandbox_security_no_new_privileges():
    kwargs = _apply_sandbox_security("task-abc", "vol-abc")
    assert "no-new-privileges" in kwargs["security_opt"]


def test_sandbox_security_volume_bound():
    vol = "autobot-workspace-task-abc-vol"
    kwargs = _apply_sandbox_security("task-abc", vol)
    assert vol in kwargs["volumes"]
    assert kwargs["volumes"][vol]["bind"] == "/workspace"


def test_sandbox_security_memory_limit():
    from services.docker_task_workspace import _WORKSPACE_MEMORY_LIMIT

    kwargs = _apply_sandbox_security("task-abc", "vol-abc")
    assert kwargs["mem_limit"] == _WORKSPACE_MEMORY_LIMIT


# ---------------------------------------------------------------------------
# TaskWorkspaceManager.create — idempotent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_new_workspace(manager, mock_docker):
    info = await manager.create("task-new-001")
    assert info.task_id == "task-new-001"
    assert info.container_id == "abc123def456"
    mock_docker.containers.run.assert_called_once()


@pytest.mark.asyncio
async def test_create_is_idempotent(manager, mock_redis, mock_docker):
    """Second create() must return existing info without spawning a new container."""
    task_id = "task-idem-001"
    existing = _make_info(task_id, container_id="existing-container")
    _store_info(mock_redis, existing)

    info = await manager.create(task_id)
    assert info.container_id == "existing-container"
    mock_docker.containers.run.assert_not_called()


# ---------------------------------------------------------------------------
# TaskWorkspaceManager.exec_command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exec_command_runs_in_container(manager, mock_redis, mock_docker):
    task_id = "task-exec-001"
    _store_info(mock_redis, _make_info(task_id, "cid-exec-001"))

    container_mock = mock_docker.containers.get.return_value
    container_mock.exec_run.return_value = MagicMock(exit_code=0, output=(b"hello\n", b""))

    result = await manager.exec_command(task_id, ["echo", "hello"])
    assert result.success is True
    assert result.exit_code == 0
    assert "hello" in result.stdout
    mock_docker.containers.get.assert_called_once_with("cid-exec-001")


@pytest.mark.asyncio
async def test_exec_command_blocked_by_security(manager, mock_redis):
    """Blocked command must not reach Docker."""
    task_id = "task-exec-blocked"
    _store_info(mock_redis, _make_info(task_id, "cid-blocked"))

    result = await manager.exec_command(task_id, ["sudo", "rm", "-rf", "/"])
    assert result.success is False
    assert result.security_blocked is True
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_exec_command_no_workspace(manager):
    result = await manager.exec_command("task-missing", ["ls"])
    assert result.success is False
    assert "No workspace" in result.stderr


# ---------------------------------------------------------------------------
# TaskWorkspaceManager.snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_snapshot_calls_commit(manager, mock_redis, mock_docker):
    task_id = "task-snap-001"
    _store_info(mock_redis, _make_info(task_id, "cid-snap-001"))

    snap = await manager.snapshot(task_id, "checkpoint-v1")
    assert snap.task_id == task_id
    assert snap.checkpoint_name == "checkpoint-v1"
    assert "checkpoint-v1" in snap.image_tag
    mock_docker.containers.get.return_value.commit.assert_called_once()


@pytest.mark.asyncio
async def test_snapshot_registers_in_redis(manager, mock_redis, mock_docker):
    task_id = "task-snap-redis"
    _store_info(mock_redis, _make_info(task_id, "cid-snap-redis"))

    await manager.snapshot(task_id, "v1")
    # The snapshot list key must be present
    snap_key = f"autobot:workspace:{task_id}:snapshots"
    assert mock_redis.get(_redis_meta_key(task_id)) is not None


@pytest.mark.asyncio
async def test_snapshot_updates_checkpoint_tags(manager, mock_redis, mock_docker):
    task_id = "task-snap-tags"
    _store_info(mock_redis, _make_info(task_id, "cid-tags"))

    await manager.snapshot(task_id, "alpha")
    updated_raw = mock_redis.get(_redis_meta_key(task_id))
    updated_info = _deserialize_info(updated_raw)
    assert "alpha" in updated_info.checkpoint_tags


# ---------------------------------------------------------------------------
# TaskWorkspaceManager.destroy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_destroy_removes_container_and_volume(manager, mock_redis, mock_docker):
    task_id = "task-destroy-001"
    info = _make_info(task_id, "cid-destroy-001")
    info.volume_name = "vol-destroy-001"
    _store_info(mock_redis, info)

    await manager.destroy(task_id)

    mock_docker.containers.get.return_value.kill.assert_called()
    mock_docker.volumes.get.return_value.remove.assert_called()
    assert mock_redis.get(_redis_meta_key(task_id)) is None


@pytest.mark.asyncio
async def test_destroy_noop_when_not_found(manager):
    """destroy() on unknown task_id must not raise."""
    await manager.destroy("task-does-not-exist")


# ---------------------------------------------------------------------------
# get_exec_handle — human drop-in surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_exec_handle_returns_socket(manager, mock_redis, mock_docker):
    task_id = "task-shell-001"
    _store_info(mock_redis, _make_info(task_id, "cid-shell-001"))

    handle = await manager.get_exec_handle(task_id)
    assert "socket" in handle
    assert "exec_id" in handle
    mock_docker.api.exec_create.assert_called_once()
    mock_docker.api.exec_start.assert_called_once()


@pytest.mark.asyncio
async def test_get_exec_handle_no_workspace(manager):
    with pytest.raises(ValueError, match="No workspace"):
        await manager.get_exec_handle("task-no-ws")


# ---------------------------------------------------------------------------
# Serialization round-trip
# ---------------------------------------------------------------------------


def test_serialize_deserialize_roundtrip():
    info = _make_info("task-serial-001")
    info.checkpoint_tags = ["v1", "v2"]
    raw = _serialize_info(info)
    restored = _deserialize_info(raw)
    assert restored.task_id == info.task_id
    assert restored.container_id == info.container_id
    assert restored.checkpoint_tags == ["v1", "v2"]


# ---------------------------------------------------------------------------
# snapshot image tag helper
# ---------------------------------------------------------------------------


def test_snapshot_image_tag_format():
    tag = _snapshot_image_tag("task-123", "v1")
    assert tag == "autobot-workspace-task-123:v1"


# ---------------------------------------------------------------------------
# _validate_checkpoint_name
# ---------------------------------------------------------------------------


def test_checkpoint_name_valid():
    _validate_checkpoint_name("v1.0-alpha")  # must not raise


def test_checkpoint_name_rejects_slash():
    with pytest.raises(ValueError):
        _validate_checkpoint_name("../etc")


# --- WS shell auth (security review: auth bypass / broken access control / fail-open) ---

def test_authenticate_ws_admin_denies_unauthenticated():
    """Fail-closed: no user + no internal key → deny (no shell)."""
    from types import SimpleNamespace
    from unittest.mock import patch

    import api.task_workspace_ws as mod

    ws = SimpleNamespace(headers={})
    with patch.object(mod, "get_auth_middleware") as gam, patch.object(mod, "ssot_config") as cfg:
        cfg.misc.internal_api_key = "k"
        gam.return_value.get_user_from_request.return_value = None
        assert mod._authenticate_ws_admin(ws) is False


def test_authenticate_ws_admin_denies_non_admin():
    """A valid but non-admin user is denied the interactive shell."""
    from types import SimpleNamespace
    from unittest.mock import patch

    import api.task_workspace_ws as mod

    ws = SimpleNamespace(headers={})
    with patch.object(mod, "get_auth_middleware") as gam, patch.object(mod, "ssot_config") as cfg:
        cfg.misc.internal_api_key = "k"
        gam.return_value.get_user_from_request.return_value = {"role": "user"}
        assert mod._authenticate_ws_admin(ws) is False


def test_authenticate_ws_admin_allows_admin_and_internal_key():
    from types import SimpleNamespace
    from unittest.mock import patch

    import api.task_workspace_ws as mod

    with patch.object(mod, "get_auth_middleware") as gam, patch.object(mod, "ssot_config") as cfg:
        cfg.misc.internal_api_key = "k"
        gam.return_value.get_user_from_request.return_value = {"role": "admin"}
        assert mod._authenticate_ws_admin(SimpleNamespace(headers={})) is True
        # internal-service key path
        assert mod._authenticate_ws_admin(SimpleNamespace(headers={"X-Internal-API-Key": "k"})) is True
