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
import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, UploadFile, status
from plugin_sdk.base import PluginManifest

from autobot_shared.ssot_config import config

logger = logging.getLogger(__name__)

_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")
_GIT_URL_SCHEMES = {"http", "https"}
_GIT_REF_PATTERN = re.compile(r"^[A-Za-z0-9._/\-]{1,128}$")
_MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MB
_MAX_ZIP_ENTRIES = 5000
_GIT_CLONE_TIMEOUT_SECONDS = 120


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


def _ensure_install_target_free(name: str) -> Path:
    target = _community_plugins_dir() / name
    if target.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Plugin '{name}' already installed. Unload and remove first.",
        )
    return target


def _assert_safe_zip(zf: zipfile.ZipFile, extract_root: Path) -> None:
    if len(zf.namelist()) > _MAX_ZIP_ENTRIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive has too many entries (>{_MAX_ZIP_ENTRIES})",
        )
    total_size = 0
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
        if info.external_attr >> 16 & 0xF000 == 0xA000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive contains symlink: {info.filename}",
            )
        total_size += info.file_size
        if total_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Archive uncompressed size exceeds 256MB",
            )


def _find_plugin_root(extract_dir: Path) -> Path:
    if (extract_dir / "plugin.json").is_file():
        return extract_dir
    children = [c for c in extract_dir.iterdir() if c.is_dir()]
    if len(children) == 1 and (children[0] / "plugin.json").is_file():
        return children[0]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="plugin.json not found at archive root or single top-level folder",
    )


async def install_from_zip(upload: UploadFile) -> InstallResult:
    if not upload.filename or not upload.filename.lower().endswith(".zip"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload must be a .zip file",
        )
    with tempfile.TemporaryDirectory(prefix="plugin-install-") as tmp:
        tmp_path = Path(tmp)
        zip_path = tmp_path / "upload.zip"
        with zip_path.open("wb") as out:
            while chunk := await upload.read(1024 * 1024):
                out.write(chunk)
        extract_dir = tmp_path / "extracted"
        extract_dir.mkdir()
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _assert_safe_zip(zf, extract_dir)
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Not a valid ZIP archive: {exc}",
            ) from exc
        plugin_root = _find_plugin_root(extract_dir)
        manifest = _read_manifest(plugin_root)
        name = _sanitize_plugin_name(manifest.name)
        target = _ensure_install_target_free(name)
        shutil.move(str(plugin_root), str(target))
        logger.info("Installed plugin '%s' v%s from ZIP upload", name, manifest.version)
        return InstallResult(
            name=name, version=manifest.version, path=str(target), source="zip"
        )


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


def _validate_git_ref(ref: Optional[str]) -> Optional[str]:
    if ref is None or ref == "":
        return None
    if not _GIT_REF_PATTERN.match(ref):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid git ref",
        )
    return ref


async def _git_clone(url: str, ref: Optional[str], dest: Path) -> None:
    cmd = ["git", "clone", "--depth=1", "--no-tags"]
    if ref:
        cmd += ["--branch", ref]
    cmd += ["--", url, str(dest)]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_GIT_CLONE_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="git clone timed out",
        ) from exc
    if proc.returncode != 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"git clone failed: {stderr.decode(errors='replace')[:500]}",
        )


async def install_from_git(url: str, ref: Optional[str]) -> InstallResult:
    _validate_git_url(url)
    ref = _validate_git_ref(ref)
    with tempfile.TemporaryDirectory(prefix="plugin-git-") as tmp:
        clone_dir = Path(tmp) / "clone"
        await _git_clone(url, ref, clone_dir)
        manifest = _read_manifest(clone_dir)
        name = _sanitize_plugin_name(manifest.name)
        target = _ensure_install_target_free(name)
        git_dir = clone_dir / ".git"
        if git_dir.exists():
            shutil.rmtree(git_dir, ignore_errors=True)
        shutil.move(str(clone_dir), str(target))
        logger.info(
            "Installed plugin '%s' v%s from git %s", name, manifest.version, url
        )
        return InstallResult(
            name=name, version=manifest.version, path=str(target), source="git"
        )
