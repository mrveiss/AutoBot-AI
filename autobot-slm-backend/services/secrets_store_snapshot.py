# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Ciphertext-only backup of the backend's secrets store (#18281).

Owner decision (2026-10-12): the artifact is a consistent SQLite online-backup
snapshot of the *encrypted* ``secrets.db``. The key (``secrets.key`` /
``AUTOBOT_SECRETS_KEY``) is never part of it, so a restore only works on a host
holding the same key. Key escrow is a separate decision (#16406).

This is a ``BackupServiceType`` run by the existing :class:`BackupService`
over its existing SSH path, not a parallel mechanism. It only READS the store:
the snapshot is made into a temp file next to nothing the backend uses, copied
to SLM storage, checksummed, and the temp file removed. No crypto lives here.

Where the store is: the backend role writes ``AUTOBOT_DATA_DIR`` from the
ansible variable ``backend_data_dir`` (roles/backend/defaults/main.yml,
``/var/lib/autobot``), and ``SecretsService`` puts ``secrets.db`` directly in
that directory. The SLM has no other registry of the backend's data path, so
``SLM_BACKEND_DATA_DIR`` carries it here with the same default (pinned to the
ansible default by a test). The node is the one the backup row names, and it
must carry a backend role.
"""

from __future__ import annotations

import asyncio
import copy
import functools
import logging
import os
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Tuple

from autobot_shared import env_utils
from models.database import BackupStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from models.database import Backup, Node
    from services.backup import BackupService

logger = logging.getLogger(__name__)

#: Directory of the backend's secrets store on the backend node (``backend_data_dir``).
BACKEND_DATA_DIR = os.getenv("SLM_BACKEND_DATA_DIR", "/var/lib/autobot")
#: The account the backend service runs as (ansible ``backend_user``, the service units' ``User=``).
SERVICE_USER = os.getenv("SLM_BACKEND_SERVICE_USER", "autobot")
#: File name ``SecretsService`` uses inside the data directory.
SECRETS_DB_NAME = "secrets.db"  # pragma: allowlist secret
#: Where the snapshot is staged on the node before the copy.
STAGING_DIR = os.getenv("SLM_SECRETS_BACKUP_STAGING_DIR", "/tmp")
#: Roles that mean "this node runs the backend" (same pair inventory_builder treats as backend).
BACKEND_ROLES = frozenset({"backend", "main"})
STORED_SUFFIX = ".secrets.db"
# Clamped readers: a typo'd value must not stop api/stateful.py (which imports this module) from loading.
SNAPSHOT_TIMEOUT_S = env_utils.env_int_clamped("SLM_SECRETS_BACKUP_TIMEOUT_S", 300, min_v=10, max_v=3600)
REMOVE_TIMEOUT_S = env_utils.env_int_clamped("SLM_SECRETS_BACKUP_REMOVE_TIMEOUT_S", 30, min_v=5, max_v=600)
CHECKSUM_TIMEOUT_S = env_utils.env_int_clamped("SLM_SECRETS_BACKUP_CHECKSUM_TIMEOUT_S", 60, min_v=5, max_v=3600)
STAGED_NAME = "snapshot.db"
STAGING_PREFIX = "slm-secrets-"

#: A POSIX account name (no leading "-", which sudo would read as an option); at most 32 characters.
_USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]*[$]?$")
USERNAME_MAX_LEN = 32
NO_BACKEND_NODE = "no registered backend node: the secrets store lives on a node with the backend role"

# Run with: python3 -c <script> <source>, as the backend service user (the data directory is 0750 to
# its group). sqlite3's online backup API gives a transactionally consistent copy while the backend
# keeps writing; the source is only read, and a missing source is an error, never an empty new store.
# The copy goes to a private 0600 temp file of that user, is integrity-checked, then streamed to stdout
# and unlinked, so no artifact owned by the service user outlives the run: the caller's shell redirect
# creates the only persistent file, owned by the ssh user, mode 0600.
_SNAPSHOT_SCRIPT = """\
import os, sqlite3, sys, tempfile
src = sys.argv[1]
if not os.path.isfile(src):
    sys.exit('secrets store not found')
fd, tmp = tempfile.mkstemp(prefix='slm-secrets-')
os.close(fd)
try:
    s = sqlite3.connect(src)
    d = sqlite3.connect(tmp)
    s.backup(d)
    ok = d.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
    d.close()
    s.close()
    if not ok:
        sys.exit('snapshot failed integrity_check')
    with open(tmp, 'rb') as f:
        sys.stdout.buffer.write(f.read())
finally:
    os.unlink(tmp)
"""


def remote_store_path() -> str:
    """The secrets database path on the backend node, derived from the data directory."""
    return str(Path(BACKEND_DATA_DIR) / SECRETS_DB_NAME)


def staged_file(staging_dir: str) -> str:
    """The snapshot's path inside the fresh per-run staging directory."""
    return str(Path(staging_dir) / STAGED_NAME)


def snapshot_command(ssh_user: str, source: str, destination: str) -> str:
    """The remote shell command that snapshots *source* into *destination* (owner-only, ssh user's).

    Runs the script as ``SERVICE_USER`` through ``sudo -n`` (no password prompt, fail fast) unless the
    ssh user already is that user.
    """
    run_as = "" if ssh_user == SERVICE_USER else f"sudo -n -u {shlex.quote(SERVICE_USER)} "
    script, src, dst = shlex.quote(_SNAPSHOT_SCRIPT), shlex.quote(source), shlex.quote(destination)
    return f"umask 077 && {run_as}python3 -c {script} {src} > {dst}"


def is_backend_node(node: "Node") -> bool:
    """Whether *node* is registered with a backend role."""
    return bool(BACKEND_ROLES & set(node.roles or []))


async def _make_staging_dir(service: "BackupService", node: "Node") -> str:
    """A fresh ``mktemp -d`` directory (0700, the ssh user's) on the node: unpredictable, never pre-existing."""
    template = shlex.quote(f"{STAGING_PREFIX}XXXXXX")
    command = f"umask 077 && mktemp -d -p {shlex.quote(STAGING_DIR)} {template}"
    cmd = service._build_ssh_command(node.ip_address, node.ssh_user or "autobot", node.ssh_port or 22, command)
    ok, out = await service._run_command(cmd, timeout=REMOVE_TIMEOUT_S)
    path = out.strip()
    if not ok or "\n" in path or not path.startswith(STAGING_DIR.rstrip("/") + "/"):
        raise RuntimeError("could not create a staging directory on the node")
    return path


async def _remove_staged(service: "BackupService", node: "Node", staging_dir: str) -> None:
    """Best-effort removal of the whole staging directory (a copy of the store must not linger)."""
    try:
        cmd = service._build_ssh_command(
            node.ip_address, node.ssh_user or "autobot", node.ssh_port or 22, f"rm -rf -- {shlex.quote(staging_dir)}"
        )
        await service._run_command(cmd, timeout=REMOVE_TIMEOUT_S)
    except Exception as exc:
        logger.warning("Could not remove staged secrets snapshot on node %s: %s", node.node_id, exc)


async def _remote_sha256(service: "BackupService", node: "Node", path: str) -> str | None:
    """sha256 of the staged snapshot as the node sees it."""
    command = f"sha256sum -- {shlex.quote(path)} | cut -d' ' -f1"
    cmd = service._build_ssh_command(node.ip_address, node.ssh_user or "autobot", node.ssh_port or 22, command)
    ok, out = await service._run_command(cmd, timeout=CHECKSUM_TIMEOUT_S)
    digest = out.strip() if ok else ""
    return digest or None


def _private_copy(service: "BackupService") -> "BackupService":
    """A copy of *service* whose scp child runs under ``umask 077``, so the file lands owner-only.

    Child-only (not ``os.umask`` and not a unit-wide ``UMask=``): the SLM writes other files that
    other accounts may need to read, and a process umask is shared with every concurrent task.
    """
    private = copy.copy(service)

    async def _run(cmd: list, timeout: int = 60, stdin: bytes | None = None):
        return await service._run_command(["/bin/sh", "-c", 'umask 077 && exec "$@"', "sh", *cmd], timeout, stdin)

    private._run_command = _run
    return private


def valid_service_user(name: str) -> bool:
    """Whether *name* is a safe POSIX account name to hand to ``sudo -u``."""
    return len(name) <= USERNAME_MAX_LEN and bool(_USERNAME_RE.match(name))


async def _fetch_verified(service: "BackupService", node: "Node", backup_id: str, remote: str) -> Tuple[Path, str]:
    """Copy the staged snapshot to SLM storage; return (path, sha256), raising on any mismatch."""
    host, user, port = node.ip_address, node.ssh_user or "autobot", node.ssh_port or 22
    remote_sum = await _remote_sha256(service, node, remote)
    ok, path, _ = await _private_copy(service)._copy_backup_to_storage(
        host, user, port, remote, backup_id, suffix=STORED_SUFFIX
    )
    try:
        if not ok:  # the scp output names user@host:path; keep it out of the row and the logs
            raise RuntimeError("scp failed")
        path.chmod(0o600)  # before anything else can fail: ciphertext is owner-only from the moment it lands
        local_sum = await service._calculate_checksum(path)
        if not local_sum or local_sum != remote_sum:
            raise RuntimeError("checksum mismatch")
    except BaseException:
        path.unlink(missing_ok=True)  # an unverified file with no row would never be pruned by retention
        raise
    return path, local_sum


async def _snapshot(service: "BackupService", node: "Node", remote: str) -> None:
    """Run the online-backup snapshot on the node, raising when it fails."""
    user = node.ssh_user or "autobot"
    cmd = service._build_ssh_command(
        node.ip_address, user, node.ssh_port or 22, snapshot_command(user, remote_store_path(), remote)
    )
    ok, out = await service._run_command(cmd, timeout=SNAPSHOT_TIMEOUT_S)
    if not ok:
        raise RuntimeError("snapshot failed on the node")


async def execute_secrets_backup(
    service: "BackupService", db: "AsyncSession", backup_id: str, node: "Node"
) -> Tuple[bool, str]:
    """Back up the secrets store of *node*; the row ends COMPLETED or FAILED with a message."""
    backup = await service._mark_backup_in_progress(db, backup_id)
    if not backup:
        return False, "Backup not found"
    if not is_backend_node(node):
        return await service._fail_backup(db, backup, NO_BACKEND_NODE)
    if not valid_service_user(SERVICE_USER):
        return await service._fail_backup(db, backup, "SLM_BACKEND_SERVICE_USER is not a valid account name")
    staging = None
    try:
        staging = await _make_staging_dir(service, node)
        path, checksum = await _snapshot_and_fetch(service, node, backup_id, staged_file(staging))
    except asyncio.TimeoutError:
        return await service._fail_backup(db, backup, "Secrets backup timed out")
    except Exception as exc:
        logger.error("Secrets backup %s failed: %s", backup_id, exc)
        return await service._fail_backup(db, backup, f"Secrets backup failed: {exc}")
    finally:
        if staging:
            await _remove_staged(service, node, staging)
    return await _record_completed(db, backup, path, checksum)


async def _snapshot_and_fetch(service: "BackupService", node: "Node", backup_id: str, remote: str) -> Tuple[Path, str]:
    """Snapshot on the node, then copy it home and verify it."""
    await _snapshot(service, node, remote)
    return await _fetch_verified(service, node, backup_id, remote)


async def _record_completed(db: "AsyncSession", backup: "Backup", path: Path, checksum: str) -> Tuple[bool, str]:
    """Fill the row for a verified snapshot."""
    backup.status = BackupStatus.COMPLETED.value
    backup.backup_path = str(path)
    backup.size_bytes = path.stat().st_size
    backup.checksum = checksum
    backup.error = None
    backup.completed_at = datetime.now(timezone.utc)
    await db.commit()
    logger.info("Secrets backup %s completed: %s bytes", backup.backup_id, backup.size_bytes)
    return True, "Secrets backup completed successfully"


def secrets_runner(service: "BackupService"):
    """The dispatch entry for ``BackupServiceType.SECRETS``: ``await runner(db, backup_id, node)``."""
    return functools.partial(execute_secrets_backup, service)
