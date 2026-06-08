#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
ADR-007 migration: move sensitive connector credentials from Redis to SecretsService.

Idempotent: connectors whose secret_id is already set are skipped.

Usage:
    python scripts/migrate_connector_credentials.py [--dry-run]
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure autobot-backend is on the import path.
_BACKEND = Path(__file__).parent.parent / "autobot-backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from knowledge.connectors.credential_store import get_credential_store

logger = get_logger(__name__)

_AUTH_TYPE_MAP: dict = {}


def _get_auth_cls(auth_type: str | None):
    """Resolve an auth class by name; returns None when not recognised."""
    if not auth_type:
        return None
    if not _AUTH_TYPE_MAP:
        from autobot_shared.auth.connector_auth import (
            ApiKeyAuth,
            BasicAuth,
            BearerAuth,
            OAuthRefreshAuth,
        )

        _AUTH_TYPE_MAP.update(
            {
                "BearerAuth": BearerAuth,
                "ApiKeyAuth": ApiKeyAuth,
                "BasicAuth": BasicAuth,
                "OAuthRefreshAuth": OAuthRefreshAuth,
            }
        )
    return _AUTH_TYPE_MAP.get(auth_type)


_NON_CONFIG_INFIXES = (":history", ":job:current", ":schedule:", "scheduler:")


def _is_config_key(key_str: str) -> bool:
    prefix = "connector:"
    stripped = key_str[len(prefix) :]
    return not any(infix in stripped for infix in _NON_CONFIG_INFIXES)


async def _migrate(dry_run: bool) -> None:
    redis = get_redis_client(database="knowledge")
    credential_store = get_credential_store()

    keys = await asyncio.to_thread(lambda: list(redis.scan_iter(match="connector:*")))
    config_keys = [
        (k.decode("utf-8") if isinstance(k, bytes) else k)
        for k in keys
        if _is_config_key(k.decode("utf-8") if isinstance(k, bytes) else k)
    ]

    migrated = 0
    skipped = 0
    failed = 0

    for key in config_keys:
        try:
            raw = await asyncio.to_thread(redis.get, key)
            if raw is None:
                continue
            data = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)

            connector_id = data.get("connector_id", key[len("connector:") :])

            if data.get("secret_id"):
                logger.info("Skipping %s — secret_id already set", connector_id)
                skipped += 1
                continue

            auth_type = data.get("auth_type")
            auth_cls = _get_auth_cls(auth_type)
            if auth_cls is None or not hasattr(auth_cls, "__sensitive_fields__"):
                logger.info("Skipping %s — no sensitive fields (auth_type=%s)", connector_id, auth_type)
                skipped += 1
                continue

            config = data.get("config", {})
            sensitive = auth_cls.__sensitive_fields__
            creds = {k: v for k, v in config.items() if k in sensitive and v}
            if not creds:
                logger.info("Skipping %s — no sensitive values in config", connector_id)
                skipped += 1
                continue

            owner_id = data.get("owner_id") or "system"

            if dry_run:
                logger.info(
                    "[DRY RUN] Would migrate %s: extract fields %s",
                    connector_id,
                    list(creds.keys()),
                )
                migrated += 1
                continue

            secret_id, safe_config = await credential_store.store(
                connector_id=connector_id,
                owner_id=owner_id,
                auth_cls=auth_cls,
                config=config,
            )

            data["config"] = safe_config
            data["secret_id"] = secret_id

            await asyncio.to_thread(redis.set, key, json.dumps(data, ensure_ascii=False))
            logger.info("Migrated %s → secret_id=%s", connector_id, secret_id)
            migrated += 1

        except Exception as exc:
            logger.error("Failed to migrate %s: %s", key, exc)
            failed += 1

    logger.info(
        "Migration complete: migrated=%d skipped=%d failed=%d",
        migrated,
        skipped,
        failed,
    )
    if failed:
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Log what would be done without writing")
    args = parser.parse_args()
    asyncio.run(_migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
