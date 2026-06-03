# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

from autobot_shared.logging_manager import get_logger
from autobot_shared.plugin_sdk import PluginManifest
from autobot_shared.ssot_config import config

logger = get_logger(__name__)

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_GIT_URL_SCHEMES = {"http", "https"}
# Disallow leading '-' (so '-foo' can't be mistaken for an option) and '..' segments.
_GIT_REF_PATTERN = re.compile(r"^(?!-)(?!.*\.\.)[A-Za-z0-9._/\-]{1,128}$")
_MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MB
_MAX_ZIP_ENTRIES = 5000
_MAX_UPLOAD_BYTES = 512 * 1024 * 1024  # 512 MB hard cap on the raw upload
_MAX_COMPRESSION_RATIO = 100  # zip-bomb sentinel
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


def _is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    # External attr stores Unix mode in the high 16 bits; 0xA000 = symlink.
    return ((info.external_attr >> 16) & 0xF000) == 0xA000


def _validate_zip_metadata(zf: zipfile.ZipFile, extract_root: Path) -> None:
    """Pre-flight checks on archive metadata. Cheap, runs before extraction."""
    names = zf.namelist()
    if len(names) > _MAX_ZIP_ENTRIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive has too many entries (>{_MAX_ZIP_ENTRIES})",
        )
    extract_root_resolved = extract_root.resolve()
    for info in zf.infolist():
        if info.is_dir():
            continue
        target = (extract_root / info.filename).resolve()
        try:
            target.relative_to(extract_root_resolved)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive entry escapes root: {info.filename}",
            ) from exc
        if _is_zip_symlink(info):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive contains symlink: {info.filename}",
            )
        # Sentinel against ZIP bombs whose header file_size is honest.
        if info.compress_size > 0 and info.file_size // info.compress_size > _MAX_COMPRESSION_RATIO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive entry has suspicious compression ratio: {info.filename}",
            )


def _safe_extract(zf: zipfile.ZipFile, extract_root: Path) -> None:
    """Stream-extract with byte cap. Tracks ACTUAL bytes written, so a
    forged file_size in the central directory can't bypass the size cap."""
    extract_root_resolved = extract_root.resolve()
    bytes_written = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        # Skip macOS resource-fork dotfiles and __MACOSX/ noise.
        if "__MACOSX/" in info.filename or Path(info.filename).name.startswith("._"):
            continue
        # Re-validate at extraction time (defense in depth).
        target = (extract_root / info.filename).resolve()
        target.relative_to(extract_root_resolved)
        if _is_zip_symlink(info):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive contains symlink: {info.filename}",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            while chunk := src.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > _MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Archive uncompressed size exceeds 256MB",
                    )
                out.write(chunk)


def _find_plugin_root(extract_dir: Path) -> Path:
    if (extract_dir / "plugin.json").is_file():
        return extract_dir
    children = [c for c in extract_dir.iterdir() if c.is_dir() and c.name != "__MACOSX" and not c.name.startswith(".")]
    if len(children) == 1 and (children[0] / "plugin.json").is_file():
        return children[0]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="plugin.json not found at archive root or single top-level folder",
    )


def _move_into_target(source: Path, target: Path) -> None:
    """Move source contents into a placeholder target dir, then remove the
    now-empty source. Target must exist (created by _claim_install_target)."""
    for child in source.iterdir():
        shutil.move(str(child), str(target / child.name))
    source.rmdir()


async def _stream_upload_to(upload: UploadFile, dest: Path) -> None:
    bytes_written = 0
    with dest.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Upload exceeds {_MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                )
            out.write(chunk)


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
