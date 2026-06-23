# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Plugin Install Service

Issue #6464 - Install 3rd-party plugins from ZIP upload or Git URL.

Note: Uses asyncio.create_subprocess_exec (no shell, args passed as a list)
which is the safe equivalent of execFile — no shell injection possible.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile, status

import archive_safety as _arch
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from plugin_sdk.base import PluginManifest

logger = get_logger(__name__)

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_GIT_URL_SCHEMES = {"http", "https"}
# Disallow leading '-' (so '-foo' can't be mistaken for an option) and '..' segments.
_GIT_REF_PATTERN = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/\-]{1,128}$")
_MAX_UPLOAD_BYTES = _arch.MAX_UPLOAD_BYTES  # 512 MB hard cap on the raw upload
_GIT_CLONE_TIMEOUT_SECONDS = 120

# Per-plugin install lock prevents two concurrent installs of the same name
# from racing past the directory-existence check (TOCTOU).
_install_locks: dict[str, asyncio.Lock] = {}
_install_locks_guard = asyncio.Lock()


async def _acquire_install_lock(name: str) -> asyncio.Lock:
    async with _install_locks_guard:
        lock = _install_locks.get(name)
        if lock is None:
            lock = asyncio.Lock()
            _install_locks[name] = lock
    return lock


@dataclass
class InstallResult:
    name: str
    version: str
    path: str
    source: str  # "zip" | "git"


def _community_plugins_dir() -> Path:
    target = config.path.plugins_path / "community-plugins"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _sanitize_plugin_name(name: str) -> str:
    if not _NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Invalid plugin name: must be lowercase alphanumeric with dashes/"
                "underscores, start with letter or digit, max 63 chars."
            ),
        )
    return name


def _read_manifest(plugin_root: Path) -> PluginManifest:
    manifest_path = plugin_root / "plugin.json"
    if not manifest_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="plugin.json not found at plugin root",
        )
    try:
        with manifest_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return PluginManifest(**data)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"plugin.json is not valid JSON: {exc}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid plugin manifest: {exc}",
        ) from exc


def _claim_install_target(name: str) -> Path:
    """Atomically reserve `community-plugins/<name>/` by creating an empty
    placeholder directory. Raises 409 if the name is already taken. The caller
    is responsible for cleaning up the placeholder on any subsequent failure.
    """
    target = _community_plugins_dir() / name
    try:
        target.mkdir(parents=False, exist_ok=False)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plugin '{name}' already installed. Unload and remove first.",
        ) from exc
    return target


# Delegate zip-safety primitives to the shared archive_safety module (#10472).
# Private wrappers preserved so call sites inside this file need no changes.
_is_zip_symlink = _arch.is_zip_symlink
_validate_zip_metadata = _arch.validate_zip_metadata
_safe_extract = _arch.safe_extract
_move_into_target = _arch.move_into_target
_stream_upload_to = _arch.stream_upload_to


def _find_plugin_root(extract_dir: Path) -> Path:
    return _arch.find_package_root(extract_dir, "plugin.json")


async def install_from_zip(upload: UploadFile) -> InstallResult:
    if not upload.filename or not upload.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload must be a .zip file",
        )
    with tempfile.TemporaryDirectory(prefix="plugin-install-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "upload.zip"
        await _stream_upload_to(upload, zip_path)
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        try:
            # Open + extract are blocking I/O; offload from the event loop.
            await asyncio.to_thread(_extract_archive, zip_path, extract_dir)
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not a valid ZIP archive: {exc}",
            ) from exc
        plugin_root = _find_plugin_root(extract_dir)
        manifest = _read_manifest(plugin_root)
        name = _sanitize_plugin_name(manifest.name)
        lock = await _acquire_install_lock(name)
        async with lock:
            target = _claim_install_target(name)
            try:
                await asyncio.to_thread(_move_into_target, plugin_root, target)
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
        logger.info("Installed plugin '%s' v%s from ZIP upload", name, manifest.version)
        return InstallResult(name=name, version=manifest.version, path=str(target), source="zip")


def _extract_archive(zip_path: Path, extract_dir: Path) -> None:
    """Synchronous wrapper for offloading via asyncio.to_thread."""
    with zipfile.ZipFile(zip_path) as zf:
        _validate_zip_metadata(zf, extract_dir)
        _safe_extract(zf, extract_dir)


def _validate_git_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in _GIT_URL_SCHEMES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only http(s) Git URLs are supported",
        )
    if not parsed.netloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Git URL is missing host",
        )


def _validate_git_ref(ref: str | None) -> str | None:
    if ref is None or ref == "":
        return None
    if not _GIT_REF_PATTERN.match(ref):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid git ref",
        )
    return ref


async def _git_clone(url: str, ref: str | None, dest: Path) -> None:
    cmd = [
        "git",
        "-c",
        "protocol.file.allow=never",
        "clone",
        "--depth=1",
        "--no-tags",
        "--recurse-submodules=no",
    ]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, str(dest)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=_GIT_CLONE_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="git clone timed out",
        ) from exc
    if proc.returncode != 0:
        stderr_text = stderr.decode(errors="replace")
        logger.warning("git clone failed for %s: %s", url, stderr_text)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"git clone failed: {stderr_text[:500]}",
        )


async def install_from_git(url: str, ref: str | None) -> InstallResult:
    _validate_git_url(url)
    ref = _validate_git_ref(ref)
    with tempfile.TemporaryDirectory(prefix="plugin-git-") as tmp:
        clone_dir = Path(tmp) / "clone"
        await _git_clone(url, ref, clone_dir)
        manifest = _read_manifest(clone_dir)
        name = _sanitize_plugin_name(manifest.name)
        # Strip .git so the installed plugin is a plain directory.
        git_dir = clone_dir / ".git"
        if git_dir.exists():
            await asyncio.to_thread(shutil.rmtree, git_dir, ignore_errors=True)
        lock = await _acquire_install_lock(name)
        async with lock:
            target = _claim_install_target(name)
            try:
                await asyncio.to_thread(_move_into_target, clone_dir, target)
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
        logger.info("Installed plugin '%s' v%s from git %s", name, manifest.version, url)
        return InstallResult(name=name, version=manifest.version, path=str(target), source="git")
