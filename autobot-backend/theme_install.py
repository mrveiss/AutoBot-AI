# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Install/list/uninstall uploaded theme packages (#10472)."""
from __future__ import annotations

import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from pydantic import BaseModel

import archive_safety as _arch
from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from theme_css_validator import validate_theme_css

logger = get_logger(__name__)
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


class ThemeManifest(BaseModel):
    id: str
    name: str
    author: str
    version: str
    supports: list[str] = ["light", "dark"]


class ThemeDescriptor(BaseModel):
    id: str
    name: str
    author: str
    version: str
    supports: list[str]


def themes_dir() -> Path:
    target = config.path.data_path / "themes"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _read_manifest(root: Path) -> ThemeManifest:
    mf = root / "theme.json"
    if not mf.is_file():
        raise HTTPException(status_code=400, detail="theme.json not found at theme root")
    try:
        return ThemeManifest(**json.loads(mf.read_text(encoding="utf-8")))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid theme.json: {exc}") from exc


async def install_theme_from_zip(upload: UploadFile) -> ThemeDescriptor:
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / "u.zip"
        await _arch.stream_upload_to(upload, zip_path)
        extract = Path(tmp) / "x"
        extract.mkdir()
        try:
            with zipfile.ZipFile(zip_path) as zf:
                _arch.validate_zip_metadata(zf, extract)
                _arch.safe_extract(zf, extract)
        except zipfile.BadZipFile as exc:
            raise HTTPException(status_code=400, detail="Not a valid ZIP archive") from exc
        root = _arch.find_package_root(extract, "theme.json")
        manifest = _read_manifest(root)
        if not _ID.match(manifest.id):
            raise HTTPException(status_code=400, detail="Invalid theme id (lowercase alphanumeric/-/_, ≤63)")
        css_file = root / "theme.css"
        if not css_file.is_file():
            raise HTTPException(status_code=400, detail="theme.css not found")
        validate_theme_css(css_file.read_text(encoding="utf-8"), manifest.id)
        target = themes_dir() / manifest.id
        try:
            target.mkdir(parents=False, exist_ok=False)
        except FileExistsError as exc:
            raise HTTPException(status_code=409, detail=f"Theme '{manifest.id}' already installed") from exc
        _arch.move_into_target(root, target)
        logger.info("Installed theme '%s' v%s", manifest.id, manifest.version)
        return ThemeDescriptor(**manifest.model_dump())


def list_installed_themes() -> list[ThemeDescriptor]:
    out: list[ThemeDescriptor] = []
    base = themes_dir()
    for d in sorted(base.iterdir()):
        mf = d / "theme.json"
        if d.is_dir() and mf.is_file():
            try:
                out.append(ThemeDescriptor(**ThemeManifest(**json.loads(mf.read_text(encoding="utf-8"))).model_dump()))
            except Exception:
                logger.warning("Skipping malformed theme dir: %s", d.name)
    return out


def _theme_dir(theme_id: str) -> Path:
    if not _ID.match(theme_id):
        raise HTTPException(status_code=400, detail="Invalid theme id")
    d = themes_dir() / theme_id
    if not d.is_dir():
        raise HTTPException(status_code=404, detail=f"Theme '{theme_id}' not found")
    return d


def uninstall_theme(theme_id: str) -> None:
    shutil.rmtree(_theme_dir(theme_id))


def theme_css_path(theme_id: str) -> Path:
    p = _theme_dir(theme_id) / "theme.css"
    if not p.is_file():
        raise HTTPException(status_code=404, detail="theme.css missing")
    return p


def theme_asset_path(theme_id: str, rel: str) -> Path:
    base = _theme_dir(theme_id).resolve()
    target = (base / rel).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid asset path") from exc
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return target
