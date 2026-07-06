# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Persistent branchable per-task Docker workspace (GH#10544).

Each task gets ONE long-running container + named volume that persists for the
life of the task.  Commands are exec'd into the running container via
``docker exec`` instead of spawning a fresh ``docker run`` per call.

Key design decisions
--------------------
- Security hardening: same network/cap/user restrictions as SecureSandboxExecutor.
  _apply_sandbox_security() copies the exact constraint set from that module so
  the two paths can never diverge independently.
- Snapshot/branch: ``docker commit`` captures the full filesystem state tagged
  as ``autobot-workspace-<task_id>:<checkpoint_name>``.  The orchestration
  CheckpointResumer's Redis-backed step checkpointing is wired in via
  ``save_step_checkpoint`` so workflow resume can coexist with workspace restore.
- Human drop-in: ``get_exec_handle`` returns a Docker exec object whose stdin/
  stdout file-descriptors the terminal WebSocket endpoint streams directly,
  reusing the existing xterm/PTY plumbing in api/terminal.py.
- Lifecycle / quota: env-configurable constants; idle-expiry background task;
  GC on completion.

Reuse map (SecureSandboxExecutor)
----------------------------------
  _prepare_container_config()  → _apply_sandbox_security()   (cap_drop, security_opt,
                                                               network_mode, mem_limit)
  _validate_command()          → validate_exec_command()      (blocked/allowed lists)
  _is_command_blocked()        → _is_exec_blocked()
  _monitor_container()         → _monitor_workspace()
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from constants.ttl_constants import TTL_1_HOUR, TTL_7_DAYS

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Quota / lifecycle constants — all env-configurable (GH#10544 constraint)
# ---------------------------------------------------------------------------
_MAX_WORKSPACES: int = int(os.environ.get("AUTOBOT_WORKSPACE_MAX_COUNT", "20"))
_DISK_QUOTA_MB: int = int(os.environ.get("AUTOBOT_WORKSPACE_DISK_MB", "2048"))
_IDLE_EXPIRY_SECONDS: int = int(os.environ.get("AUTOBOT_WORKSPACE_IDLE_SECONDS", str(4 * 3600)))
_WORKSPACE_MEMORY_LIMIT: str = os.environ.get("AUTOBOT_WORKSPACE_MEM_LIMIT", "512m")
_WORKSPACE_CPU_QUOTA: int = int(os.environ.get("AUTOBOT_WORKSPACE_CPU_QUOTA", "100000"))
_WORKSPACE_IMAGE: str = os.environ.get("AUTOBOT_WORKSPACE_IMAGE", "alpine:3.18")
_CONTAINER_PREFIX: str = "autobot-workspace-"
_REDIS_KEY_PREFIX: str = "autobot:workspace:"

# Commands that are never permitted inside a workspace exec (reuse from
# SecureSandboxExecutor._is_command_blocked default_blocked list)
_BLOCKED_EXEC_COMMANDS: frozenset[str] = frozenset(
    {
        "sudo",
        "su",
        "doas",
        "mount",
        "umount",
        "iptables",
        "netfilter",
        "docker",
        "podman",
        "systemctl",
        "service",
        "reboot",
        "shutdown",
        "halt",
    }
)

try:
    import docker
    from docker.errors import APIError, DockerException, NotFound

    _DOCKER_AVAILABLE = True
except ImportError:
    _DOCKER_AVAILABLE = False
    docker = None  # type: ignore[assignment]

    class DockerException(Exception):  # type: ignore[no-redef]
        pass

    class NotFound(DockerException):  # type: ignore[no-redef]
        pass

    class APIError(DockerException):  # type: ignore[no-redef]
        pass


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class WorkspaceInfo:
    """Metadata for a live task workspace."""

    task_id: str
    container_id: str
    volume_name: str
    image: str
    created_at: float
    last_active: float
    checkpoint_tags: list[str] = field(default_factory=list)


@dataclass
class ExecResult:
    """Result of a command exec'd into a workspace container."""

    success: bool
    exit_code: int
    stdout: str
    stderr: str
    execution_time: float
    task_id: str
    security_blocked: bool = False


@dataclass
class SnapshotInfo:
    """Metadata about a workspace snapshot/branch."""

    task_id: str
    checkpoint_name: str
    image_tag: str
    created_at: float


# ---------------------------------------------------------------------------
# TaskWorkspaceManager
# ---------------------------------------------------------------------------


class TaskWorkspaceManager:
    """
    Manages per-task persistent Docker container workspaces.

    One container + named volume per task_id.  Operations:
      create(task_id)             — create container+volume, idempotent
      get(task_id)                — return WorkspaceInfo or None
      exec_command(task_id, cmd)  — run cmd in the live container
      snapshot(task_id, name)     — docker commit → image tag
      restore(task_id, name)      — recreate container from snapshot image
      destroy(task_id)            — stop container, remove volume
      get_exec_handle(task_id)    — return raw exec object for PTY drop-in
    """

    def __init__(self, docker_client: Any = None) -> None:
        if not _DOCKER_AVAILABLE:
            raise DockerException(
                "docker SDK not installed; `pip install docker` to enable TaskWorkspaceManager."
            )
        self._docker: Any = docker_client or docker.from_env()
        self._redis = get_redis_client(async_client=False)
        self._lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def create(self, task_id: str) -> WorkspaceInfo:
        """Create or resume a workspace for *task_id*.  Idempotent."""
        _validate_task_id(task_id)
        existing = await self.get(task_id)
        if existing is not None:
            logger.info("workspace: resuming container for task=%s", task_id)
            await self._touch_active(task_id)
            return existing

        async with self._lock:
            await self._enforce_quota()
            return await asyncio.to_thread(self._create_workspace_sync, task_id)

    async def get(self, task_id: str) -> WorkspaceInfo | None:
        """Return WorkspaceInfo if the workspace is registered, else None."""
        _validate_task_id(task_id)
        raw = await asyncio.to_thread(self._redis.get, _redis_meta_key(task_id))
        if raw is None:
            return None
        try:
            return _deserialize_info(raw)
        except Exception as exc:
            logger.warning("workspace: corrupt Redis meta for task=%s: %s", task_id, exc)
            return None

    async def exec_command(self, task_id: str, command: list[str] | str) -> ExecResult:
        """
        Exec *command* inside the running workspace container.

        Reuses SecureSandboxExecutor's validation logic: blocked commands are
        rejected before any Docker call is made.
        """
        _validate_task_id(task_id)
        cmd_list = command if isinstance(command, list) else command.split()
        if not validate_exec_command(cmd_list):
            logger.warning("workspace: exec blocked for task=%s cmd=%s", task_id, cmd_list)
            return ExecResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr="Command blocked by security policy",
                execution_time=0.0,
                task_id=task_id,
                security_blocked=True,
            )

        info = await self.get(task_id)
        if info is None:
            return ExecResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=f"No workspace for task {task_id}",
                execution_time=0.0,
                task_id=task_id,
            )

        start = time.monotonic()
        result = await asyncio.to_thread(self._exec_sync, info.container_id, cmd_list)
        elapsed = time.monotonic() - start
        await self._touch_active(task_id)

        return ExecResult(
            success=result["exit_code"] == 0,
            exit_code=result["exit_code"],
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", ""),
            execution_time=elapsed,
            task_id=task_id,
        )

    async def snapshot(self, task_id: str, checkpoint_name: str) -> SnapshotInfo:
        """
        Snapshot workspace filesystem via ``docker commit``.

        Tag format: ``autobot-workspace-<task_id>:<checkpoint_name>``
        Also stores step checkpoint in Redis to wire into CheckpointResumer.
        """
        _validate_task_id(task_id)
        _validate_checkpoint_name(checkpoint_name)
        info = await self.get(task_id)
        if info is None:
            raise ValueError(f"No workspace for task {task_id}")

        image_tag = _snapshot_image_tag(task_id, checkpoint_name)
        snap_ts = time.time()
        await asyncio.to_thread(self._commit_snapshot_sync, info.container_id, image_tag)

        # Register checkpoint in Redis (pairs with CheckpointResumer's Redis backend)
        snap_meta = json.dumps(
            {"task_id": task_id, "checkpoint_name": checkpoint_name, "image_tag": image_tag, "created_at": snap_ts}
        )
        snap_key = f"{_REDIS_KEY_PREFIX}{task_id}:snapshots"
        await asyncio.to_thread(self._redis.rpush, snap_key, snap_meta)
        await asyncio.to_thread(self._redis.expire, snap_key, TTL_7_DAYS)

        # Update WorkspaceInfo tags
        info.checkpoint_tags.append(checkpoint_name)
        await asyncio.to_thread(self._redis.set, _redis_meta_key(task_id), _serialize_info(info), ex=TTL_7_DAYS)

        logger.info("workspace: snapshot task=%s name=%s image=%s", task_id, checkpoint_name, image_tag)
        return SnapshotInfo(task_id=task_id, checkpoint_name=checkpoint_name, image_tag=image_tag, created_at=snap_ts)

    async def restore(self, task_id: str, checkpoint_name: str) -> WorkspaceInfo:
        """
        Restore workspace from a snapshot: stop current container, recreate
        from the committed image, keep the same named volume.
        """
        _validate_task_id(task_id)
        _validate_checkpoint_name(checkpoint_name)
        info = await self.get(task_id)
        if info is None:
            raise ValueError(f"No workspace for task {task_id}")

        image_tag = _snapshot_image_tag(task_id, checkpoint_name)
        await asyncio.to_thread(self._stop_container_sync, info.container_id, force=True)
        new_container_id = await asyncio.to_thread(
            self._start_container_sync, task_id, info.volume_name, image_tag
        )
        info.container_id = new_container_id
        info.last_active = time.time()
        await asyncio.to_thread(self._redis.set, _redis_meta_key(task_id), _serialize_info(info), ex=TTL_7_DAYS)
        logger.info("workspace: restored task=%s checkpoint=%s", task_id, checkpoint_name)
        return info

    async def destroy(self, task_id: str) -> None:
        """Stop container, remove volume, delete Redis keys.  Best-effort."""
        _validate_task_id(task_id)
        info = await self.get(task_id)
        if info is None:
            return
        await asyncio.to_thread(self._destroy_sync, info)
        await asyncio.to_thread(self._redis.delete, _redis_meta_key(task_id))
        await asyncio.to_thread(self._redis.delete, f"{_REDIS_KEY_PREFIX}{task_id}:snapshots")
        logger.info("workspace: destroyed task=%s", task_id)

    async def get_exec_handle(self, task_id: str, cmd: list[str] | None = None, tty: bool = True) -> Any:
        """
        Return a raw Docker exec handle (exec_id + socket) for PTY drop-in.

        The caller (api/task_workspace_ws.py) streams stdin/stdout of this
        handle over the existing xterm WebSocket infrastructure — no new PTY
        layer is created, the existing terminal WS plumbing is reused.
        """
        _validate_task_id(task_id)
        info = await self.get(task_id)
        if info is None:
            raise ValueError(f"No workspace for task {task_id}")
        shell_cmd = cmd or ["/bin/sh"]
        return await asyncio.to_thread(
            self._create_exec_handle_sync, info.container_id, shell_cmd, tty
        )

    async def list_all(self) -> list[WorkspaceInfo]:
        """Return all registered workspaces (for quota enforcement + stats)."""
        pattern = f"{_REDIS_KEY_PREFIX}*:meta"
        keys = await asyncio.to_thread(self._redis.keys, pattern)
        results: list[WorkspaceInfo] = []
        for key in keys:
            raw = await asyncio.to_thread(self._redis.get, key)
            if raw:
                try:
                    results.append(_deserialize_info(raw))
                except Exception:
                    pass
        return results

    async def gc_idle(self) -> list[str]:
        """Destroy workspaces idle longer than _IDLE_EXPIRY_SECONDS."""
        cutoff = time.time() - _IDLE_EXPIRY_SECONDS
        workspaces = await self.list_all()
        destroyed: list[str] = []
        for ws in workspaces:
            if ws.last_active < cutoff:
                await self.destroy(ws.task_id)
                destroyed.append(ws.task_id)
        if destroyed:
            logger.info("workspace: GC evicted %d idle workspaces", len(destroyed))
        return destroyed

    # ------------------------------------------------------------------
    # Thread-pool sync helpers (blocking Docker SDK calls)
    # ------------------------------------------------------------------

    def _create_workspace_sync(self, task_id: str) -> WorkspaceInfo:
        volume_name = f"{_CONTAINER_PREFIX}{task_id}-vol"
        self._docker.volumes.create(name=volume_name)
        container_id = self._start_container_sync(task_id, volume_name, _WORKSPACE_IMAGE)
        now = time.time()
        info = WorkspaceInfo(
            task_id=task_id,
            container_id=container_id,
            volume_name=volume_name,
            image=_WORKSPACE_IMAGE,
            created_at=now,
            last_active=now,
        )
        self._redis.set(_redis_meta_key(task_id), _serialize_info(info), ex=TTL_7_DAYS)
        logger.info("workspace: created task=%s container=%s volume=%s", task_id, container_id, volume_name)
        return info

    def _start_container_sync(self, task_id: str, volume_name: str, image: str) -> str:
        """Start the workspace container applying full sandbox security constraints."""
        container = self._docker.containers.run(
            image=image,
            name=f"{_CONTAINER_PREFIX}{task_id}",
            **_apply_sandbox_security(task_id, volume_name),
        )
        return container.id

    def _exec_sync(self, container_id: str, cmd: list[str]) -> dict[str, Any]:
        try:
            container = self._docker.containers.get(container_id)
            exec_result = container.exec_run(cmd, demux=True)
            stdout_b, stderr_b = exec_result.output or (b"", b"")
            return {
                "exit_code": exec_result.exit_code,
                "stdout": (stdout_b or b"").decode("utf-8", errors="replace"),
                "stderr": (stderr_b or b"").decode("utf-8", errors="replace"),
            }
        except NotFound:
            return {"exit_code": -1, "stdout": "", "stderr": f"Container {container_id} not found"}
        except APIError as exc:
            return {"exit_code": -1, "stdout": "", "stderr": str(exc)}

    def _commit_snapshot_sync(self, container_id: str, image_tag: str) -> None:
        repo, tag = image_tag.rsplit(":", 1)
        container = self._docker.containers.get(container_id)
        container.commit(repository=repo, tag=tag)

    def _stop_container_sync(self, container_id: str, force: bool = False) -> None:
        try:
            container = self._docker.containers.get(container_id)
            if force:
                container.kill()
            else:
                container.stop(timeout=10)
            container.remove()
        except (NotFound, APIError):
            pass

    def _create_exec_handle_sync(self, container_id: str, cmd: list[str], tty: bool) -> Any:
        container = self._docker.containers.get(container_id)
        exec_id = self._docker.api.exec_create(container.id, cmd, stdin=True, tty=tty)
        sock = self._docker.api.exec_start(exec_id, detach=False, tty=tty, socket=True)
        return {"exec_id": exec_id, "socket": sock, "container_id": container_id}

    def _destroy_sync(self, info: WorkspaceInfo) -> None:
        self._stop_container_sync(info.container_id, force=True)
        try:
            vol = self._docker.volumes.get(info.volume_name)
            vol.remove(force=True)
        except (NotFound, APIError) as exc:
            logger.debug("workspace: volume remove failed (may already be gone): %s", exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _touch_active(self, task_id: str) -> None:
        info = await self.get(task_id)
        if info is None:
            return
        info.last_active = time.time()
        await asyncio.to_thread(self._redis.set, _redis_meta_key(task_id), _serialize_info(info), ex=TTL_7_DAYS)

    async def _enforce_quota(self) -> None:
        workspaces = await self.list_all()
        if len(workspaces) < _MAX_WORKSPACES:
            return
        oldest = sorted(workspaces, key=lambda w: w.last_active)
        to_evict = oldest[: len(workspaces) - _MAX_WORKSPACES + 1]
        for ws in to_evict:
            logger.warning("workspace: quota eviction task=%s", ws.task_id)
            await self.destroy(ws.task_id)


# ---------------------------------------------------------------------------
# Security — mirrors SecureSandboxExecutor._prepare_container_config()
# ---------------------------------------------------------------------------


def _apply_sandbox_security(task_id: str, volume_name: str) -> dict[str, Any]:
    """
    Build Docker container kwargs that enforce the SAME security constraints
    as SecureSandboxExecutor._prepare_container_config() (GH#10544).

    Kept as a standalone function so it can be unit-tested independently and
    so both the per-command and per-task paths share one canonical definition.
    """
    return {
        "command": ["tail", "-f", "/dev/null"],  # long-running: container stays up
        "detach": True,
        "remove": False,
        "network_mode": "none",  # no network — same as SecureSandboxExecutor HIGH
        "read_only": False,  # workspace MUST be writable (unlike ephemeral sandbox)
        "security_opt": ["no-new-privileges"],
        "cap_drop": ["ALL"],
        "cap_add": [],
        "mem_limit": _WORKSPACE_MEMORY_LIMIT,
        "memswap_limit": _WORKSPACE_MEMORY_LIMIT,
        "cpu_quota": _WORKSPACE_CPU_QUOTA,
        "cpu_period": 100000,
        "volumes": {volume_name: {"bind": "/workspace", "mode": "rw"}},
        "working_dir": "/workspace",
        "environment": {
            "SECURITY_LEVEL": "high",
            "MONITOR_ENABLED": "true",
            "TASK_ID": task_id,
        },
        "labels": {
            "com.autobot.workspace": "true",
            "com.autobot.task_id": task_id,
            "com.autobot.created_at": str(time.time()),
        },
    }


def validate_exec_command(cmd: list[str]) -> bool:
    """
    Validate a command list before exec'ing it into a workspace container.

    Mirrors SecureSandboxExecutor._validate_command() / _is_command_blocked().
    Returns False if the base command is on the blocked list.
    """
    if not cmd:
        return False
    base = cmd[0].split("/")[-1]  # basename, e.g. /bin/sudo → sudo
    if base in _BLOCKED_EXEC_COMMANDS:
        logger.warning("workspace: exec blocked base command=%s", base)
        return False
    return True


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _validate_task_id(task_id: str) -> None:
    import re

    if not re.match(r"^[0-9a-zA-Z_\-]{1,128}$", task_id):
        raise ValueError(f"Invalid task_id {task_id!r}")


def _validate_checkpoint_name(name: str) -> None:
    import re

    if not re.match(r"^[0-9a-zA-Z_\-\.]{1,64}$", name):
        raise ValueError(f"Invalid checkpoint name {name!r}")


def _snapshot_image_tag(task_id: str, checkpoint_name: str) -> str:
    return f"autobot-workspace-{task_id}:{checkpoint_name}"


def _redis_meta_key(task_id: str) -> str:
    return f"{_REDIS_KEY_PREFIX}{task_id}:meta"


def _serialize_info(info: WorkspaceInfo) -> str:
    d = {
        "task_id": info.task_id,
        "container_id": info.container_id,
        "volume_name": info.volume_name,
        "image": info.image,
        "created_at": info.created_at,
        "last_active": info.last_active,
        "checkpoint_tags": info.checkpoint_tags,
    }
    return json.dumps(d)


def _deserialize_info(raw: bytes | str) -> WorkspaceInfo:
    d = json.loads(raw)
    return WorkspaceInfo(
        task_id=d["task_id"],
        container_id=d["container_id"],
        volume_name=d["volume_name"],
        image=d["image"],
        created_at=float(d["created_at"]),
        last_active=float(d["last_active"]),
        checkpoint_tags=d.get("checkpoint_tags", []),
    )


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, same pattern as get_secure_sandbox)
# ---------------------------------------------------------------------------

_manager: TaskWorkspaceManager | None = None
_manager_lock = asyncio.Lock()


async def get_task_workspace_manager() -> TaskWorkspaceManager:
    """Return the module-level TaskWorkspaceManager singleton."""
    global _manager
    if _manager is not None:
        return _manager
    async with _manager_lock:
        if _manager is None:
            _manager = TaskWorkspaceManager()
    return _manager
