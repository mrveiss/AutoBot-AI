# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One-time migration for secrets-store files off the legacy CWD-relative
resolver, onto the canonical ssot_config-derived data directory (#14081
review, #14113).

Before #14081, ``SecretsManager``/``SecretsService`` resolved their storage
through ``utils.paths_manager.get_data_path()``, which reads an unset
``config.yaml`` ``paths:`` key and silently falls back to a CWD-relative
``"data/..."`` path. Pointing them at ``ssot_config.path.data_path`` instead
fixes the divergence going forward, but on an existing deployment the real
store already lives at the old location -- changing where the code *looks*
without moving what is already there orphans every stored credential and
looks exactly like a first boot (a new key gets minted, an empty store gets
created, nothing raises).

This module runs once, at the same points the old code decided "generate a
new key vs. load the existing one", and either performs a safe move or
refuses to guess.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Sequence

from autobot_shared.logging_manager import get_logger
from utils.paths_manager import get_data_path

logger = get_logger(__name__)


class AmbiguousSecretsStoreError(RuntimeError):
    """Both the legacy and canonical secrets-store locations hold data.

    Raised instead of guessing which one is authoritative -- an automatic
    choice here can silently destroy whichever store it doesn't pick.
    """


def _legacy_absolute_path(filename: str) -> Path:
    """Resolve *filename* the exact way the pre-#14081 code did.

    Calls the real ``get_data_path`` rather than reimplementing its
    CWD-relative fallback, so this migration stays correct even if that
    resolver's behavior changes later (#14113 tracks fixing it directly).
    ``get_data_path`` can return a relative path (the bug) or, if
    ``config.yaml`` ever gains a real ``paths:`` section, an absolute one;
    ``os.path.abspath`` handles both.
    """
    return Path(os.path.abspath(str(get_data_path(filename))))


def migrate_legacy_secrets_store(canonical_dir: Path, filenames: Sequence[str], store_role: str) -> None:
    """Move *filenames* from the legacy data dir to *canonical_dir* if needed.

    Must be called before any caller decides whether to generate a fresh
    encryption key or treat the store as empty -- that decision is exactly
    what silently destroys existing secrets if the legacy location still
    holds the real store.

    Args:
        canonical_dir: the new, ssot_config-derived data directory.
        filenames: the store's files to check/move, e.g. ``["secrets.key",
            "secrets.json"]`` or ``["secrets.db"]``.
        store_role: a generic, log-safe description of what this store is
            (e.g. ``"secrets manager"``) -- never an absolute path, so log
            lines stay safe to paste into an issue or PR.

    Raises:
        AmbiguousSecretsStoreError: both locations already hold data for
            this store.
    """
    canonical_dir = Path(canonical_dir)
    legacy_paths = {name: _legacy_absolute_path(name) for name in filenames}
    canonical_paths = {name: canonical_dir / name for name in filenames}

    # Common dev case: the legacy and canonical resolvers agree (CWD ==
    # base_dir). Nothing to migrate, and must stay a no-op -- there is only
    # ever one location, so "moving" it would just be a same-path shutil.move.
    if all(legacy_paths[name] == canonical_paths[name] for name in filenames):
        return

    legacy_has_data = any(p.exists() for p in legacy_paths.values())
    if not legacy_has_data:
        return  # genuine first boot, or a migration that already ran

    canonical_has_data = any(p.exists() for p in canonical_paths.values())
    if canonical_has_data:
        raise AmbiguousSecretsStoreError(
            f"Both the legacy and canonical {store_role} storage locations contain "
            "data (#14081/#14113 path-resolver migration). Refusing to guess which "
            "is authoritative: a human must compare the two locations, manually "
            "consolidate them, and remove the stale one before this service can "
            "start."
        )

    canonical_dir.mkdir(parents=True, exist_ok=True)
    for name in filenames:
        legacy_path = legacy_paths[name]
        if not legacy_path.exists():
            continue
        canonical_path = canonical_paths[name]
        shutil.move(str(legacy_path), str(canonical_path))
        # Keys stay 0o600 regardless of what mode they moved with; other
        # store files (json/db) keep the permissions shutil.move preserved.
        if name.endswith(".key"):
            os.chmod(canonical_path, 0o600)

    logger.warning(
        "Migrated %s storage from its legacy location to the canonical data "
        "directory (#14081/#14113 path-resolver fix). This is a one-time move; "
        "no data was lost.",
        store_role,
    )
