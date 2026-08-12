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

#14081 security review round 5 (PR #14110) found three sharper problems with
the first version of this module, all fixed here:

1. ``SecretsManager`` and ``SecretsService`` each migrated only the files
   they personally read (key+json, db respectively). A process that only
   ever constructs one of the two -- a celery worker calling
   ``get_secrets_service()`` without the FastAPI app's ``SecretsManager``
   singleton ever running -- migrated the db alone, leaving the shared
   encryption key behind at the legacy location. ``ALL_SECRETS_STORE_FILES``
   and a single shared call site (`migrate_legacy_secrets_store` invoked
   with that whole set, from both classes) close this: whichever class
   constructs first migrates everything, not just its own slice.
2. Backend and worker processes can both reach a genuine first boot at the
   same moment on an upgrade. ``_canonical_store_lock`` serializes the
   actual move (and, via ``ensure_and_read_shared_key``, first-time key
   generation) across processes with an ``O_EXCL`` lockfile, so two
   processes can never interleave writes to the same destination file.
3. ``shutil.move`` degrades to copy2+unlink when source and destination are
   on different filesystems -- exactly the persistent-volume-to-container-
   layer case this migration exists for -- and that path is not atomic: an
   interrupt mid-copy can leave a truncated file at the destination *and*
   the intact source, which then reads as "both locations populated"
   forever after. ``_atomic_move`` copies to a temp file in the destination
   directory, ``fsync``s it, verifies its size against the source, and only
   then ``os.replace``s it into place before removing the source.
"""

from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Sequence

from cryptography.fernet import Fernet

from autobot_shared.logging_manager import get_logger
from utils.paths_manager import get_data_path

logger = get_logger(__name__)

#: The complete set of files that make up the secrets store, spanning both
#: SecretsManager (key + json) and SecretsService (db). Migrated together,
#: as one unit, regardless of which class triggers the migration -- see
#: finding 2 in the module docstring above.
ALL_SECRETS_STORE_FILES: tuple[str, ...] = ("secrets.key", "secrets.json", "secrets.db")

_LOCK_FILENAME = ".secrets_store_migration.lock"
# Long enough to cover a slow cross-filesystem copy of a large secrets.db;
# short enough that a crashed lock holder doesn't wedge every future boot.
_LOCK_STALE_SECONDS = 120
_LOCK_POLL_INTERVAL_SECONDS = 0.5
_LOCK_WAIT_TIMEOUT_SECONDS = 30


class AmbiguousSecretsStoreError(RuntimeError):
    """Both the legacy and canonical secrets-store locations hold data.

    Raised instead of guessing which one is authoritative -- an automatic
    choice here can silently destroy whichever store it doesn't pick.
    """


class SecretsStoreLockTimeoutError(RuntimeError):
    """Another process held the canonical secrets-store lock too long."""


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


@contextmanager
def _canonical_store_lock(canonical_dir: Path) -> Iterator[None]:
    """Cross-process mutual exclusion for writes to *canonical_dir* (#14081
    review round 5, finding 3).

    Backend and worker processes -- separate OS processes, so an
    in-process ``threading.Lock`` cannot see each other -- can both reach a
    genuine first boot at the same moment on an upgrade. ``O_CREAT |
    O_EXCL`` makes the lockfile's creation itself atomic at the kernel
    level: at most one caller's ``os.open`` succeeds when two race it
    concurrently. Callers that lose the race poll until the winner releases
    it (or a stale lock is reclaimed after a crash).
    """
    canonical_dir.mkdir(parents=True, exist_ok=True)
    lock_path = canonical_dir / _LOCK_FILENAME
    deadline = time.monotonic() + _LOCK_WAIT_TIMEOUT_SECONDS
    fd = None
    while fd is None:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                stale = (time.time() - lock_path.stat().st_mtime) > _LOCK_STALE_SECONDS
            except FileNotFoundError:
                continue  # released between our failed open() and this stat()
            if stale:
                # A crashed holder never reached the `finally` unlink below.
                # Reclaiming is safe: the winner of the resulting race for
                # the *next* O_EXCL create is the only one that proceeds.
                lock_path.unlink(missing_ok=True)
                continue
            if time.monotonic() > deadline:
                raise SecretsStoreLockTimeoutError(
                    f"Timed out after {_LOCK_WAIT_TIMEOUT_SECONDS}s waiting for another "
                    "process to finish initializing the secrets store (#14081/#14113)."
                )
            time.sleep(_LOCK_POLL_INTERVAL_SECONDS)
    try:
        os.write(fd, str(os.getpid()).encode("utf-8"))
        os.close(fd)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _atomic_move(src: Path, dst: Path) -> None:
    """Copy *src* to *dst*, verify it, then remove *src* -- not
    ``shutil.move`` (#14081 review round 5, finding 3).

    ``shutil.move`` silently degrades to ``copy2`` + ``unlink`` when the
    two paths are on different filesystems, which is exactly the
    persistent-volume -> container-writable-layer move this module makes.
    That path is not atomic: an interrupt between the copy and the unlink
    leaves a partial file at *dst* and the untouched original at *src* --
    both "populated", forever indistinguishable from two independent real
    stores.
    """
    tmp_dst = dst.with_name(dst.name + ".tmp")
    shutil.copy2(str(src), str(tmp_dst))
    fd = os.open(str(tmp_dst), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)

    if tmp_dst.stat().st_size != src.stat().st_size:
        tmp_dst.unlink(missing_ok=True)
        raise OSError(f"Atomic move verification failed for {dst.name}: size mismatch after copy")

    os.replace(str(tmp_dst), str(dst))
    src.unlink()


def migrate_legacy_secrets_store(canonical_dir: Path, filenames: Sequence[str], store_role: str) -> None:
    """Move *filenames* from the legacy data dir to *canonical_dir* if needed.

    Must be called before any caller decides whether to generate a fresh
    encryption key or treat the store as empty -- that decision is exactly
    what silently destroys existing secrets if the legacy location still
    holds the real store. Callers should pass ``ALL_SECRETS_STORE_FILES``
    (see the module docstring, finding 2) rather than their own subset.

    Args:
        canonical_dir: the new, ssot_config-derived data directory.
        filenames: the store's files to check/move.
        store_role: a generic, log-safe description of what this store is
            (e.g. ``"secrets store"``) -- never an absolute path, so log
            lines stay safe to paste into an issue or PR.

    Raises:
        AmbiguousSecretsStoreError: both locations already hold data for
            this store.
        SecretsStoreLockTimeoutError: another process held the migration
            lock past its timeout.
    """
    canonical_dir = Path(canonical_dir)
    legacy_paths = {name: _legacy_absolute_path(name) for name in filenames}
    canonical_paths = {name: canonical_dir / name for name in filenames}

    # Common dev case: the legacy and canonical resolvers agree (CWD ==
    # base_dir). Nothing to migrate, and must stay a no-op -- there is only
    # ever one location, so "moving" it would just be a same-path move.
    if all(legacy_paths[name] == canonical_paths[name] for name in filenames):
        return

    # Cheap, lock-free fast path (#14081 review round 5): most calls to this
    # function happen long after the real migration completed (every
    # SecretsService() construction, not only the first), and must not pay
    # for a lockfile create/unlink on every one. Nothing to race over if
    # legacy is already empty.
    if not any(p.exists() for p in legacy_paths.values()):
        return  # genuine first boot, or a migration that already ran

    with _canonical_store_lock(canonical_dir):
        # Re-check under the lock: another process may have completed the
        # migration (or lost the ambiguous-state race) while this one
        # waited.
        legacy_has_data = any(p.exists() for p in legacy_paths.values())
        if not legacy_has_data:
            return

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
            _atomic_move(legacy_path, canonical_path)
            # Keys stay 0o600 regardless of what mode they moved with; other
            # store files (json/db) keep the permissions copy2 preserved.
            if name.endswith(".key"):
                os.chmod(canonical_path, 0o600)

        logger.warning(
            "Migrated %s storage from its legacy location to the canonical data "
            "directory (#14081/#14113 path-resolver fix). This is a one-time move; "
            "no data was lost.",
            store_role,
        )


def ensure_and_read_shared_key(canonical_dir: Path) -> bytes:
    """Load the shared Fernet key from ``<canonical_dir>/secrets.key``,
    minting and persisting one if it does not exist yet (#14081 review
    round 5).

    The single code path that may create this file, used by both
    ``SecretsManager`` and ``SecretsService`` so the two classes cannot
    disagree about the key -- and so a genuine first boot racing across two
    processes mints exactly one real, persisted key rather than each
    process silently keeping its own throwaway one in memory. That
    silent-throwaway-key behavior was ``SecretsService``'s pre-#14081
    fallback: a key generated on a WARNING and never written to disk,
    indistinguishable from first boot even when a real store already
    existed, and undecryptable by any other process or the next restart.
    """
    canonical_dir = Path(canonical_dir)
    key_path = canonical_dir / "secrets.key"

    if key_path.exists():
        return key_path.read_bytes()

    with _canonical_store_lock(canonical_dir):
        if key_path.exists():  # minted by another process while we waited
            return key_path.read_bytes()

        canonical_dir.mkdir(parents=True, exist_ok=True)
        key = Fernet.generate_key()
        tmp_path = key_path.with_name(key_path.name + ".tmp")
        tmp_path.write_bytes(key)
        fd = os.open(str(tmp_path), os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.chmod(tmp_path, 0o600)
        os.replace(str(tmp_path), str(key_path))

        logger.warning(
            "Generated and persisted a new shared secrets-store encryption key at the "
            "canonical data directory (#14081 review round 5). Set AUTOBOT_SECRETS_KEY "
            "for a deployment-managed key instead."
        )
        return key
