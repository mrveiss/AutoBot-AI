# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Shared, hardened zip-archive handling for package installers (plugins, themes).

Extracted from plugin_install.py (#10472) so every installer reuses the same
zip-slip / symlink / zip-bomb / upload-size guards — one place to audit and fix.
"""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ZIP_ENTRIES = 5000
MAX_UPLOAD_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100


def is_zip_symlink(info: zipfile.ZipInfo) -> bool:
    return ((info.external_attr >> 16) & 0xF000) == 0xA000


def validate_zip_metadata(zf: zipfile.ZipFile, extract_root: Path) -> None:
    names = zf.namelist()
    if len(names) > MAX_ZIP_ENTRIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Archive has too many entries (>{MAX_ZIP_ENTRIES})",
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
        if is_zip_symlink(info):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive contains symlink: {info.filename}",
            )
        if info.compress_size > 0 and info.file_size // info.compress_size > MAX_COMPRESSION_RATIO:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive entry has suspicious compression ratio: {info.filename}",
            )


def safe_extract(zf: zipfile.ZipFile, extract_root: Path) -> None:
    extract_root_resolved = extract_root.resolve()
    bytes_written = 0
    for info in zf.infolist():
        if info.is_dir():
            continue
        if "__MACOSX/" in info.filename or Path(info.filename).name.startswith("._"):
            continue
        target = (extract_root / info.filename).resolve()
        target.relative_to(extract_root_resolved)
        if is_zip_symlink(info):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Archive contains symlink: {info.filename}",
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, target.open("wb") as out:
            while chunk := src.read(1024 * 1024):
                bytes_written += len(chunk)
                if bytes_written > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Archive uncompressed size exceeds 256MB",
                    )
                out.write(chunk)


def find_package_root(extract_dir: Path, manifest_filename: str) -> Path:
    if (extract_dir / manifest_filename).is_file():
        return extract_dir
    children = [c for c in extract_dir.iterdir() if c.is_dir() and c.name != "__MACOSX" and not c.name.startswith(".")]
    if len(children) == 1 and (children[0] / manifest_filename).is_file():
        return children[0]
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{manifest_filename} not found at archive root or single top-level folder",
    )


def move_into_target(source: Path, target: Path) -> None:
    for child in source.iterdir():
        shutil.move(str(child), str(target / child.name))
    source.rmdir()


async def stream_upload_to(upload: UploadFile, dest: Path) -> None:
    bytes_written = 0
    with dest.open("wb") as out:
        while chunk := await upload.read(1024 * 1024):
            bytes_written += len(chunk)
            if bytes_written > MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)}MB",
                )
            out.write(chunk)
