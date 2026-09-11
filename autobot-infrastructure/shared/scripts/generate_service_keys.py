#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Generate service API keys for AutoBot distributed infrastructure.

Stores keys in Redis and creates backup configuration file.

Usage:
    python3 scripts/generate_service_keys.py
    python3 scripts/generate_service_keys.py --output-dir /opt/autobot/config/service-keys
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Export retention (#16348): the deploy role only ever reads the newest
# service-keys-*.yaml (deploy-keys.yml, "sort by mtime, take last"), so every
# older export left on disk after a rotation is one more plaintext copy of
# live keys with no reader. Override via AUTOBOT_SERVICE_KEYS_KEEP_COUNT;
# default keeps just the newest.
_KEYS_EXPORT_RETENTION_ENV = "AUTOBOT_SERVICE_KEYS_KEEP_COUNT"
_SERVICE_KEYS_KEEP_COUNT_DEFAULT = 1


def _resolve_keep_count() -> int:
    """How many service-keys-*.yaml exports survive a rotation (#16348)."""
    raw = os.environ.get(_KEYS_EXPORT_RETENTION_ENV)
    if raw is None:
        return _SERVICE_KEYS_KEEP_COUNT_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; keeping the default of %d",
            _KEYS_EXPORT_RETENTION_ENV,
            raw,
            _SERVICE_KEYS_KEEP_COUNT_DEFAULT,
        )
        return _SERVICE_KEYS_KEEP_COUNT_DEFAULT
    if value < 1:
        logger.warning(
            "%s=%d must be at least 1; keeping the default of %d",
            _KEYS_EXPORT_RETENTION_ENV,
            value,
            _SERVICE_KEYS_KEEP_COUNT_DEFAULT,
        )
        return _SERVICE_KEYS_KEEP_COUNT_DEFAULT
    return value


SERVICE_KEYS_KEEP_COUNT = _resolve_keep_count()

# Project paths (#16348). The repo root goes on sys.path, never the
# autobot_shared package directory itself: that exposed autobot_shared's own
# ``security`` subpackage as a top-level ``security``, which shadowed the
# backend's and made the ServiceAuthManager import fail. The backend path and
# its imports load only when keys are generated (_load_backend), so importing
# this module to test its path helpers pulls in no backend code.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from autobot_shared.ssot_config import config  # noqa: E402


def _load_backend():
    """The Redis client factory and the backend's key manager, imported at run time."""
    backend_dir = str(PROJECT_ROOT / "autobot-backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    from autobot_shared.redis_client import get_async_redis_client  # noqa: PLC0415
    from security.service_auth import ServiceAuthManager  # noqa: PLC0415

    return get_async_redis_client, ServiceAuthManager

# Service definitions for AutoBot's distributed VM infrastructure.
# Hosts are resolved from SSOT config — never hardcoded.
SERVICES = [
    {
        "id": "main-backend",
        "host_attr": "main",
        "description": "Main backend API server",
    },
    {
        "id": "slm-backend",
        "host_attr": "slm",
        "description": "SLM control-plane backend (unified-secrets System-vault client, #10153)",
    },
    {
        "id": "frontend",
        "host_attr": "frontend",
        "description": "Vue.js frontend web interface",
    },
    {
        "id": "npu-worker",
        "host_attr": "npu",
        "description": "NPU hardware acceleration worker",
    },
    {
        "id": "redis-stack",
        "host_attr": "redis",
        "description": "Redis Stack database",
    },
    {
        "id": "ai-stack",
        "host_attr": "aistack",
        "description": "AI/ML processing stack",
    },
    {
        "id": "browser-service",
        "host_attr": "browser",
        "description": "Playwright browser automation",
    },
]


def _resolve_host(host_attr: str) -> str:
    """Resolve host IP from SSOT config."""
    return getattr(config.vms, host_attr)


async def _generate_all_keys(auth_manager):
    """Generate keys for all services and return dict.

    Helper for generate_keys (#1734).
    """
    generated_keys = {}
    for service in SERVICES:
        service_id = service["id"]
        host = _resolve_host(service["host_attr"])

        logger.info("Generating key for %s...", service_id)
        key = await auth_manager.generate_service_key(service_id)
        generated_keys[service_id] = {
            "key": key,
            "host": host,
            "description": service["description"],
            "generated_at": datetime.now().isoformat(),
        }
        logger.info("  %s: %s***", service_id, key[:8])
    return generated_keys


def _resolve_output_dir(output_dir: str | None) -> Path:
    """Resolve the service-keys export directory (#16348).

    An explicit ``--output-dir`` wins. Otherwise the SSOT-configured
    installation root (``config.path.base_dir``) is used — itself anchored
    to AUTOBOT_BASE_DIR or the checkout root, never to this process's
    working directory, so there is no cwd fallback to remove here.
    """
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    if not config.path.base_dir:
        raise RuntimeError(
            "No --output-dir given and SSOT has no base_dir configured; "
            "refusing to fall back to the working directory (#16348)."
        )
    return config.path.resolve("config/service-keys").resolve()


def _refuse_if_inside_git_worktree(directory: Path) -> None:
    """Refuse to export live keys into a git checkout (#16348).

    Walks the resolved directory's own ancestry for a ``.git`` entry — a
    directory in a normal clone, a file (``gitdir: ...``) in a worktree
    checkout — so a broad ``git add`` can never sweep up live keys again
    (the exposure behind #16301).
    """
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            raise RuntimeError(
                f"Refusing to write service keys inside a git work tree: "
                f"{candidate} contains .git. Point --output-dir (or SSOT's "
                f"base_dir) outside any checkout (#16348)."
            )


def _prune_old_backups(backup_dir: Path, keep: int = SERVICE_KEYS_KEEP_COUNT) -> None:
    """Delete all but the newest *keep* service-keys-*.yaml exports (#16348).

    The filename timestamp (``%Y%m%d-%H%M%S``) sorts lexicographically in
    chronological order, so a plain name sort picks the newest without a
    stat() call — the deploy role's own selector (deploy-keys.yml, sorted by
    path) keeps working against whatever survives. ``keep`` is clamped to at
    least 1: a caller passing 0 would delete the export just written.
    """
    keep = max(1, keep)
    exports = sorted(backup_dir.glob("service-keys-*.yaml"))
    for path in exports[:-keep]:
        path.unlink()
        logger.info("Pruned old service-keys export: %s", path.name)


def _ensure_private_dir(directory: Path) -> None:
    """Create *directory* at 0700, explicitly -- never the process umask (#16348)."""
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(directory, 0o700)


def _save_backup(generated_keys, redis_host, redis_port, output_dir: str | None = None):
    """Write keys backup YAML and return file path.

    Helper for generate_keys (#1734). Refuses a git work tree and never
    falls back to the working directory (#16348). The directory and file
    are put at 0700/0600 explicitly rather than left to the umask, and the
    file is opened O_EXCL so it never exists at a world-readable mode even
    for an instant.
    """
    backup_dir = _resolve_output_dir(output_dir)
    _refuse_if_inside_git_worktree(backup_dir)
    _ensure_private_dir(backup_dir)

    backup_file = backup_dir / f"service-keys-{datetime.now().strftime('%Y%m%d-%H%M%S')}.yaml"
    fd = os.open(backup_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        yaml.safe_dump(
            {
                "generated_at": datetime.now().isoformat(),
                "redis_host": redis_host,
                "redis_port": redis_port,
                "services": generated_keys,
            },
            f,
            default_flow_style=False,
        )

    logger.info("Backup saved: %s", backup_file)
    _prune_old_backups(backup_dir)
    return backup_file


async def _verify_keys_in_redis(auth_manager, generated_keys):
    """Verify all generated keys are stored in Redis.

    Helper for generate_keys (#1734).
    """
    logger.info("Verifying keys in Redis...")
    for service_id in generated_keys:
        stored_key = await auth_manager.get_service_key(service_id)
        if stored_key:
            logger.info("  %s: Key verified in Redis", service_id)
        else:
            logger.error("  %s: FAILED - Key not found!", service_id)


async def generate_keys(output_dir: str | None = None):
    """Generate API keys for all services and store in Redis."""
    redis_host = config.vms.redis
    redis_port = config.ports.redis

    logger.info("AutoBot Service Key Generation")
    logger.info("=" * 60)
    logger.info("Timestamp: %s", datetime.now().isoformat())
    logger.info("Redis: %s:%s", redis_host, redis_port)
    logger.info("Services: %d", len(SERVICES))
    logger.info("")

    redis_client_factory, key_manager_cls = _load_backend()
    auth_manager = key_manager_cls(await redis_client_factory(database="main"))

    generated_keys = await _generate_all_keys(auth_manager)
    logger.info("")
    logger.info("Generated %d service keys", len(generated_keys))
    logger.info("")

    backup_file = _save_backup(generated_keys, redis_host, redis_port, output_dir)
    logger.info("")

    await _verify_keys_in_redis(auth_manager, generated_keys)

    logger.info("")
    logger.info("=" * 60)
    logger.info("Service key generation complete!")
    logger.info("  Deploy: ansible-playbook playbooks/deploy-service-auth.yml")
    logger.info("  Backup: %s", backup_file)

    return generated_keys


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments (#16348)."""
    parser = argparse.ArgumentParser(description="Generate AutoBot service API keys.")
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for the service-keys-*.yaml export. Defaults to SSOT's "
            "base_dir/config/service-keys; never the working directory."
        ),
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    _cli_args = _parse_args()
    asyncio.run(generate_keys(_cli_args.output_dir))
