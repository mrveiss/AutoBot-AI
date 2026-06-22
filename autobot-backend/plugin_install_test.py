# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard tests for plugin_install.py — verify that the archive_safety refactor
does not regress plugin install behaviour (#10472).

Tests are deliberately lightweight:
  (a) import-level smoke — confirms plugin_install imports and its core functions
      delegate to archive_safety (not a copy of the old logic).
  (b) zip-slip rejection via archive_safety (which plugin_install delegates to),
      called directly to avoid the heavy _community_plugins_dir / config chain.
"""
import io
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

import archive_safety as _arch
import plugin_install


def _zip_bytes(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


# (a) Import-level smoke: confirm delegation is wired up
def test_plugin_install_delegates_to_archive_safety():
    assert plugin_install._validate_zip_metadata is _arch.validate_zip_metadata
    assert plugin_install._safe_extract is _arch.safe_extract
    assert plugin_install._move_into_target is _arch.move_into_target
    assert plugin_install._stream_upload_to is _arch.stream_upload_to


# (b) Zip-slip rejection — the shared guard that plugin_install now uses
def test_zip_slip_rejected_via_shared_guard(tmp_path: Path):
    zf = zipfile.ZipFile(io.BytesIO(_zip_bytes({"../evil.txt": b"x"})))
    with pytest.raises(HTTPException) as exc:
        plugin_install._validate_zip_metadata(zf, tmp_path)
    assert exc.value.status_code == 400


# (c) find_plugin_root wraps find_package_root with plugin.json
def test_find_plugin_root_wraps_archive_safety(tmp_path: Path):
    (tmp_path / "myplugin").mkdir()
    (tmp_path / "myplugin" / "plugin.json").write_text("{}", encoding="utf-8")
    assert plugin_install._find_plugin_root(tmp_path) == tmp_path / "myplugin"
