# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one container-hardening constraint set for Docker clients (#17267).

Every client that creates a sandbox/workspace container takes its security kwargs
from `hardening_kwargs`, so the constraint set cannot drift between copies. What a
client may legitimately vary is an explicit named parameter; everything else
(``cap_drop=ALL``, ``no-new-privileges``, the CPU period) is fixed here.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from typing import Any

from autobot_shared.env_utils import env_int, env_str
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Process cap for hardened containers (Linux pids cgroup), so a fork-bomb cannot
#: exhaust host PIDs (GH#11059). One env-backed value shared by every client.
CONTAINER_PIDS_LIMIT: int = env_int("AUTOBOT_WORKSPACE_PIDS_LIMIT", 512)

#: Memory (and, equal to it, swap) cap for execution/pool containers that do not size their own.
EXECUTION_MEMORY_LIMIT: str = env_str("AUTOBOT_EXECUTION_MEMORY_LIMIT", "512m")

#: Size of the scratch tmpfs a read-only execution container writes to.
EXECUTION_TMPFS_SIZE: str = env_str("AUTOBOT_EXECUTION_TMPFS_SIZE", "64m")

#: Where the scratch tmpfs is mounted inside an execution container.
EXECUTION_SCRATCH_PATH = "/tmp"  # nosec B108  # container-internal mount point, not a host path

#: CFS period paired with every ``cpu_quota`` (microseconds).
CPU_PERIOD_US = 100000


def baseline_hardening_kwargs(*, pids_limit: int | None = CONTAINER_PIDS_LIMIT) -> dict[str, Any]:
    """The non-behavioural subset: ``cap_drop=ALL``, ``no-new-privileges`` and a pids cap.

    Changes no network, filesystem, mount, memory or user behaviour, so a client that
    cannot yet take the full set (``hardening_kwargs``) still gets the privilege floor.
    ``pids_limit=None`` omits the cap.
    """
    kwargs: dict[str, Any] = {"security_opt": ["no-new-privileges"], "cap_drop": ["ALL"]}
    if pids_limit is not None:
        kwargs["pids_limit"] = pids_limit
    return kwargs


def hardening_kwargs(
    *,
    network_mode: str,
    read_only: bool,
    memory_limit: str,
    cpu_quota: int,
    pids_limit: int | None = None,
) -> dict[str, Any]:
    """Docker create/run kwargs enforcing the shared constraint set.

    Args:
        network_mode: ``"none"`` unless the caller is explicitly allowed network.
        read_only: root filesystem read-only (False only for persistent workspaces).
        memory_limit: Docker memory string; also used as the swap cap (no swap).
        cpu_quota: CFS quota in microseconds per ``CPU_PERIOD_US``.
        pids_limit: process cap; omitted from the kwargs when None.
    """
    kwargs: dict[str, Any] = {
        "network_mode": network_mode,
        "read_only": read_only,
        **baseline_hardening_kwargs(pids_limit=None),
        "cap_add": [],
        "mem_limit": memory_limit,
        "memswap_limit": memory_limit,
        "cpu_quota": cpu_quota,
        "cpu_period": CPU_PERIOD_US,
    }
    if pids_limit is not None:
        kwargs["pids_limit"] = pids_limit
    return kwargs


_REASON_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{2,63}$")


def _audited_reason(flag: str, reason: str | None) -> str | None:
    """Return a validated opt-in reason (logged), or None when the flag is not opted out.

    A reason is a short lowercase slug naming the workload (e.g. ``pip-install-backend``).
    Passing a blank or non-slug reason raises, so a default cannot be dropped anonymously.
    """
    if reason is None:
        return None
    if not isinstance(reason, str) or not _REASON_RE.match(reason):
        raise ValueError(f"container hardening opt-out '{flag}' needs a named reason slug, got {reason!r}")
    logger.warning("container hardening default dropped: %s (reason=%s)", flag, reason)
    return reason


#: Run/create kwargs that widen the container's reach beyond the hardened set. Merging the
#: builder last only overrides the builder's own keys; these pass through unless refused.
DENIED_RUN_KWARGS: frozenset[str] = frozenset(
    {
        "privileged",
        "cap_add",
        "devices",
        "device_requests",
        "device_cgroup_rules",
        "pid_mode",
        "ipc_mode",
        "uts_mode",
        "userns_mode",
        "cgroupns",
        "network",
        "security_opt",
        "sysctls",
        "volumes_from",
        "mounts",
        "cgroup_parent",
        "runtime",
        "oom_kill_disable",
        "volume_driver",
    }
)

#: Host paths a bind mount may never expose: each one itself, and anything beneath it.
_DENIED_HOST_PATHS = ("/", "/proc", "/sys", "/dev", "/etc", "/run", "/var/run", "/var/lib/docker", "/root", "/boot")


def _bind_host_paths(volumes: Any) -> list[str]:
    if isinstance(volumes, Mapping):
        return [str(k) for k in volumes]
    if isinstance(volumes, (list, tuple)):
        return [str(v).split(":", 1)[0] for v in volumes]
    return [str(volumes)]


def _is_denied_host_path(host_path: str) -> bool:
    """True for a path equal to or beneath a denied root, or any ``*.sock`` file.

    Leading slashes are collapsed first (dockerd reads ``//`` as ``/``). ``/`` is denied
    only as the root itself (``/srv/work`` passes); the other roots also deny their subtrees.
    A named volume (no leading ``/``) is not a host path and passes.
    """
    if not host_path.startswith("/"):
        return False
    norm = "/" + posixpath.normpath(host_path).lstrip("/")
    if posixpath.basename(norm).endswith(".sock"):
        return True
    return any(norm == root or (root != "/" and norm.startswith(root + "/")) for root in _DENIED_HOST_PATHS)


def reject_escalating_kwargs(extra: Mapping[str, Any]) -> None:
    """Raise ValueError when caller-supplied run kwargs would widen the container's reach."""
    bad = sorted(DENIED_RUN_KWARGS & set(extra))
    if bad:
        raise ValueError(f"container run kwargs not allowed on a hardened execution container: {bad}")
    for host_path in _bind_host_paths(extra.get("volumes", {})) if "volumes" in extra else []:
        if _is_denied_host_path(host_path):
            raise ValueError(f"container bind mount of host path {host_path!r} is not allowed")


def execution_hardening_kwargs(
    *,
    memory_limit: str | None = None,
    network_reason: str | None = None,
    writable_root_reason: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Full hardening for pooled and execution containers (#17267, option b).

    Defaults: ``network_mode="none"``, read-only root with a size-limited
    ``noexec,nosuid`` tmpfs scratch, ``mem_limit`` with ``memswap_limit`` equal to it
    (no swap), plus the privilege floor (``cap_drop=ALL``, ``no-new-privileges``, pids cap).

    Args:
        memory_limit: Docker memory string; default ``AUTOBOT_EXECUTION_MEMORY_LIMIT``.
        network_reason: slug naming the workload that needs network; enables ``bridge``.
        writable_root_reason: slug naming the workload that needs a writable root.
        extra: caller kwargs to merge beneath the hardening; any key in
            ``DENIED_RUN_KWARGS`` or a bind of the docker socket / host root raises ValueError.
    """
    reject_escalating_kwargs(extra or {})
    memory = memory_limit or EXECUTION_MEMORY_LIMIT
    networked = _audited_reason("network", network_reason) is not None
    writable = _audited_reason("writable_root", writable_root_reason) is not None
    return {
        **(extra or {}),
        "network_mode": "bridge" if networked else "none",
        "read_only": not writable,
        "tmpfs": {EXECUTION_SCRATCH_PATH: f"rw,noexec,nosuid,size={EXECUTION_TMPFS_SIZE}"},
        "mem_limit": memory,
        "memswap_limit": memory,
        **baseline_hardening_kwargs(),
    }
