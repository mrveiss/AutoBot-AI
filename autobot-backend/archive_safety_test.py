# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

from archive_safety import find_package_root, safe_extract, validate_zip_metadata


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_safe_extract_writes_files(tmp_path: Path):
    zf = zipfile.ZipFile(io.BytesIO(_zip_bytes({"theme.json": b"{}"})))
    safe_extract(zf, tmp_path)
    assert (tmp_path / "theme.json").read_bytes() == b"{}"


def test_validate_rejects_zip_slip(tmp_path: Path):
    zf = zipfile.ZipFile(io.BytesIO(_zip_bytes({"../evil.txt": b"x"})))
    with pytest.raises(HTTPException) as exc:
        validate_zip_metadata(zf, tmp_path)
    assert exc.value.status_code == 400


def test_find_package_root_in_single_subdir(tmp_path: Path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "theme.json").write_text("{}", encoding="utf-8")
    assert find_package_root(tmp_path, "theme.json") == tmp_path / "pkg"
