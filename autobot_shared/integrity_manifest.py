# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
SHA256 file-integrity manifest for security-critical config files (GH#11265).

Detects out-of-band tampering that ``config_guard`` cannot catch — external
edits that bypass the app's write path.  Non-fatal by design: a missing or
unreadable manifest logs a WARNING and returns cleanly; it never raises at
startup.

Environment variables
---------------------
AUTOBOT_INTEGRITY_CHECK_ENABLED : bool (default False)
    Master switch.  When False every public function short-circuits immediately.
AUTOBOT_INTEGRITY_MANIFEST_PATH : str (default "")
    Absolute path to the JSON manifest file produced by :func:`write_manifest`.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Iterable

from autobot_shared.config_guard import _PROTECTED_BASENAMES, _PROTECTED_PREFIXES
from autobot_shared.env_utils import env_flag
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Env-var constants (never hard-coded)
# ---------------------------------------------------------------------------
_ENV_ENABLED = "AUTOBOT_INTEGRITY_CHECK_ENABLED"
_ENV_MANIFEST_PATH = "AUTOBOT_INTEGRITY_MANIFEST_PATH"


def _check_enabled() -> bool:
    return env_flag(_ENV_ENABLED, default=False)


def _manifest_path() -> str:
    return os.environ.get(_ENV_MANIFEST_PATH, "")


# ---------------------------------------------------------------------------
# Core helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: str) -> str:
    """Return the hex SHA-256 digest of *path* (reads raw bytes)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_protected_basename(name: str) -> bool:
    """True when *name* (basename) matches config_guard's protected set."""
    lower = name.lower()
    if lower in _PROTECTED_BASENAMES:
        return True
    return any(lower.startswith(p) for p in _PROTECTED_PREFIXES)


def _default_fileset(root: str) -> list[str]:
    """Walk *root* and return absolute paths whose basename is protected."""
    found: list[str] = []
    for dirpath, _dirs, files in os.walk(root):
        for fname in files:
            if _is_protected_basename(fname):
                found.append(os.path.join(dirpath, fname))
    return found


# ---------------------------------------------------------------------------
# Manifest compute
# ---------------------------------------------------------------------------


def compute_manifest(files: Iterable[str], root: str = "") -> dict[str, str]:
    """Return ``{relative_path: sha256hex}`` for each existing file in *files*.

    Paths are stored relative to *root* (or absolute when *root* is empty).
    Missing files are skipped with a WARNING.
    """
    manifest: dict[str, str] = {}
    for abs_path in files:
        if not os.path.isfile(abs_path):
            logger.warning("integrity_manifest: skipping missing file %s", abs_path)
            continue
        key = os.path.relpath(abs_path, root) if root else abs_path
        try:
            manifest[key] = _sha256_file(abs_path)
        except OSError as exc:
            logger.warning("integrity_manifest: cannot hash %s: %s", abs_path, exc)
    return manifest


def write_manifest(manifest: dict[str, str], dest: str) -> None:
    """Serialise *manifest* as JSON to *dest* (UTF-8, sorted keys)."""
    with open(dest, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    logger.info("integrity_manifest: wrote %d entries to %s", len(manifest), dest)


# ---------------------------------------------------------------------------
# Verify result
# ---------------------------------------------------------------------------


@dataclass
class VerifyResult:
    """Structured outcome of :func:`verify_manifest`."""

    ok: list[str] = field(default_factory=list)
    modified: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.modified and not self.missing


def verify_manifest(
    manifest: dict[str, str],
    root: str = "",
) -> VerifyResult:
    """Compare *manifest* against current disk state, returning a :class:`VerifyResult`.

    Keys in *manifest* are resolved relative to *root* (or treated as absolute
    when *root* is empty).  Any key that cannot be read is classified MISSING.
    """
    result = VerifyResult()
    for rel_key, expected_hex in manifest.items():
        abs_path = os.path.join(root, rel_key) if root else rel_key
        if not os.path.isfile(abs_path):
            result.missing.append(rel_key)
            continue
        try:
            actual = _sha256_file(abs_path)
        except OSError:
            result.missing.append(rel_key)
            continue
        if actual == expected_hex:
            result.ok.append(rel_key)
        else:
            result.modified.append(rel_key)
    return result


# ---------------------------------------------------------------------------
# Startup entrypoint
# ---------------------------------------------------------------------------


def verify_integrity_at_startup(root: str = "") -> None:
    """Non-fatal startup integrity check.

    Reads AUTOBOT_INTEGRITY_MANIFEST_PATH and verifies current files against
    the stored SHA-256 manifest.  Logs WARNING on any mismatch; never raises.

    Guarded by AUTOBOT_INTEGRITY_CHECK_ENABLED (default False) — a no-op when
    the flag is absent/false.

    Call site: backend ``lifespan`` handler, after logging is initialised but
    before the first request is served.
    """
    if not _check_enabled():
        return

    manifest_path = _manifest_path()
    if not manifest_path:
        logger.warning(
            "integrity_manifest: AUTOBOT_INTEGRITY_CHECK_ENABLED=1 but "
            "AUTOBOT_INTEGRITY_MANIFEST_PATH is not set — skipping check"
        )
        return

    try:
        with open(manifest_path, encoding="utf-8") as fh:
            manifest: dict[str, str] = json.load(fh)
    except FileNotFoundError:
        logger.warning("integrity_manifest: manifest not found at %s", manifest_path)
        return
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("integrity_manifest: cannot load manifest %s: %s", manifest_path, exc)
        return

    result = verify_manifest(manifest, root=root)

    if result.clean:
        logger.info("integrity_manifest: all %d tracked files verified OK", len(result.ok))
        return

    if result.modified:
        logger.warning(
            "integrity_manifest: TAMPERED files detected (%d): %s",
            len(result.modified),
            result.modified,
        )
    if result.missing:
        logger.warning(
            "integrity_manifest: MISSING files (%d): %s",
            len(result.missing),
            result.missing,
        )
