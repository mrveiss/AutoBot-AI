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
import json
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

import archive_safety as _arch
import plugin_install
from plugin_install import _read_manifest


def _zip_bytes(entries: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


_BASE_MANIFEST = {
    "name": "test-plugin",
    "display_name": "Test Plugin",
    "description": "A test plugin",
    "author": "mrveiss",
    "entry_point": "plugins.test_plugin.main",
}


def _write_manifest(plugin_root: Path, data: dict) -> None:
    with (plugin_root / "plugin.json").open("w", encoding="utf-8") as f:
        json.dump(data, f)


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


# ---------------------------------------------------------------------------
# _read_manifest — install path shared by install_from_zip / install_from_git
# (Issue #11652: semver pre-release fix + previously-untested error paths)
# ---------------------------------------------------------------------------


def test_read_manifest_valid(tmp_path: Path):
    _write_manifest(tmp_path, {**_BASE_MANIFEST, "version": "1.0.0"})
    manifest = _read_manifest(tmp_path)
    assert manifest.name == "test-plugin"
    assert manifest.version == "1.0.0"


def test_read_manifest_numeric_only_version_accepted(tmp_path: Path):
    _write_manifest(tmp_path, {**_BASE_MANIFEST, "version": "2.5.11"})
    manifest = _read_manifest(tmp_path)
    assert manifest.version == "2.5.11"


@pytest.mark.parametrize("version", ["1.0.0-beta", "1.0.0-rc.1", "1.0.0+build.5"])
def test_read_manifest_semver_prerelease_and_build_accepted(tmp_path: Path, version: str):
    """Issue #11652: pre-release/build semver must no longer 400 on install."""
    _write_manifest(tmp_path, {**_BASE_MANIFEST, "version": version})
    manifest = _read_manifest(tmp_path)
    assert manifest.version == version


def test_read_manifest_with_required_env_with_description(tmp_path: Path):
    _write_manifest(
        tmp_path,
        {
            **_BASE_MANIFEST,
            "version": "1.0.0",
            "required_env": [{"name": "MY_API_KEY", "description": "The API key."}],
        },
    )
    manifest = _read_manifest(tmp_path)
    assert manifest.required_env[0].name == "MY_API_KEY"
    assert manifest.required_env[0].description == "The API key."


def test_read_manifest_required_env_without_description_rejected(tmp_path: Path):
    """`description` is required (min_length=1) — omitting it is a malformed manifest."""
    _write_manifest(
        tmp_path,
        {**_BASE_MANIFEST, "version": "1.0.0", "required_env": [{"name": "MY_API_KEY"}]},
    )
    with pytest.raises(HTTPException) as exc:
        _read_manifest(tmp_path)
    assert exc.value.status_code == 400


def test_read_manifest_non_upper_snake_env_name_rejected(tmp_path: Path):
    _write_manifest(
        tmp_path,
        {
            **_BASE_MANIFEST,
            "version": "1.0.0",
            "required_env": [{"name": "my_api_key", "description": "The API key."}],
        },
    )
    with pytest.raises(HTTPException) as exc:
        _read_manifest(tmp_path)
    assert exc.value.status_code == 400


def test_read_manifest_missing_file_rejected(tmp_path: Path):
    with pytest.raises(HTTPException) as exc:
        _read_manifest(tmp_path)
    assert exc.value.status_code == 400
    assert "not found" in exc.value.detail


def test_read_manifest_malformed_json_rejected(tmp_path: Path):
    (tmp_path / "plugin.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(HTTPException) as exc:
        _read_manifest(tmp_path)
    assert exc.value.status_code == 400
    assert "not valid JSON" in exc.value.detail


def test_read_manifest_invalid_version_rejected(tmp_path: Path):
    """Genuinely invalid versions (not semver) must still 400."""
    _write_manifest(tmp_path, {**_BASE_MANIFEST, "version": "v1.0.0"})
    with pytest.raises(HTTPException) as exc:
        _read_manifest(tmp_path)
    assert exc.value.status_code == 400


def test_read_manifest_missing_required_field_rejected(tmp_path: Path):
    """Malformed manifest: missing a required field (`author`)."""
    incomplete = {k: v for k, v in _BASE_MANIFEST.items() if k != "author"}
    _write_manifest(tmp_path, {**incomplete, "version": "1.0.0"})
    with pytest.raises(HTTPException) as exc:
        _read_manifest(tmp_path)
    assert exc.value.status_code == 400
