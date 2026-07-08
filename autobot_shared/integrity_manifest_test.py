# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for autobot_shared.integrity_manifest (GH#11265)."""

from __future__ import annotations

import json


from autobot_shared.integrity_manifest import (
    compute_manifest,
    verify_integrity_at_startup,
    verify_manifest,
    write_manifest,
)

# ---------------------------------------------------------------------------
# compute_manifest
# ---------------------------------------------------------------------------


class TestComputeManifest:
    def test_deterministic(self, tmp_path):
        """Same file content always produces the same SHA-256 hex."""
        f = tmp_path / ".eslintrc.json"
        f.write_bytes(b"rule: on")

        m1 = compute_manifest([str(f)])
        m2 = compute_manifest([str(f)])

        assert m1 == m2
        assert len(m1) == 1
        # SHA-256 hex is always 64 chars
        assert len(next(iter(m1.values()))) == 64

    def test_relative_key_when_root_given(self, tmp_path):
        f = tmp_path / "ruff.toml"
        f.write_bytes(b"[tool.ruff]")

        manifest = compute_manifest([str(f)], root=str(tmp_path))

        assert list(manifest.keys()) == ["ruff.toml"]

    def test_absolute_key_when_no_root(self, tmp_path):
        f = tmp_path / "mypy.ini"
        f.write_bytes(b"[mypy]")

        manifest = compute_manifest([str(f)])

        assert str(f) in manifest

    def test_missing_file_skipped(self, tmp_path):
        absent = str(tmp_path / "ghost.toml")
        manifest = compute_manifest([absent])
        assert manifest == {}

    def test_content_change_changes_hash(self, tmp_path):
        f = tmp_path / ".editorconfig"
        f.write_bytes(b"v1")
        m1 = compute_manifest([str(f)])
        f.write_bytes(b"v2-tampered")
        m2 = compute_manifest([str(f)])
        assert m1 != m2


# ---------------------------------------------------------------------------
# write_manifest + round-trip
# ---------------------------------------------------------------------------


class TestWriteManifest:
    def test_round_trip(self, tmp_path):
        f = tmp_path / "ruff.toml"
        f.write_bytes(b"content")
        manifest = compute_manifest([str(f)])

        dest = tmp_path / "manifest.json"
        write_manifest(manifest, str(dest))

        with open(dest, encoding="utf-8") as fh:
            loaded = json.load(fh)

        assert loaded == manifest


# ---------------------------------------------------------------------------
# verify_manifest
# ---------------------------------------------------------------------------


class TestVerifyManifest:
    def _make_manifest(self, files: dict[str, bytes], tmp_path) -> dict[str, str]:
        for name, content in files.items():
            (tmp_path / name).write_bytes(content)
        paths = [str(tmp_path / n) for n in files]
        return compute_manifest(paths, root=str(tmp_path))

    def test_all_ok(self, tmp_path):
        manifest = self._make_manifest({"ruff.toml": b"ok"}, tmp_path)
        result = verify_manifest(manifest, root=str(tmp_path))
        assert result.clean
        assert result.ok == ["ruff.toml"]
        assert result.modified == []
        assert result.missing == []

    def test_detects_modified(self, tmp_path):
        manifest = self._make_manifest({"mypy.ini": b"original"}, tmp_path)
        (tmp_path / "mypy.ini").write_bytes(b"tampered!")
        result = verify_manifest(manifest, root=str(tmp_path))
        assert not result.clean
        assert "mypy.ini" in result.modified
        assert result.missing == []

    def test_detects_missing(self, tmp_path):
        f = tmp_path / ".editorconfig"
        f.write_bytes(b"data")
        manifest = compute_manifest([str(f)], root=str(tmp_path))
        f.unlink()

        result = verify_manifest(manifest, root=str(tmp_path))
        assert not result.clean
        assert ".editorconfig" in result.missing
        assert result.modified == []

    def test_mixed_ok_modified_missing(self, tmp_path):
        (tmp_path / "ruff.toml").write_bytes(b"r")
        (tmp_path / "mypy.ini").write_bytes(b"m")
        (tmp_path / ".editorconfig").write_bytes(b"e")
        paths = [str(tmp_path / n) for n in ("ruff.toml", "mypy.ini", ".editorconfig")]
        manifest = compute_manifest(paths, root=str(tmp_path))

        (tmp_path / "mypy.ini").write_bytes(b"tampered")
        (tmp_path / ".editorconfig").unlink()

        result = verify_manifest(manifest, root=str(tmp_path))
        assert "ruff.toml" in result.ok
        assert "mypy.ini" in result.modified
        assert ".editorconfig" in result.missing
        assert not result.clean


# ---------------------------------------------------------------------------
# verify_integrity_at_startup
# ---------------------------------------------------------------------------


class TestVerifyIntegrityAtStartup:
    def test_disabled_flag_short_circuits(self, monkeypatch, tmp_path, caplog):
        """When AUTOBOT_INTEGRITY_CHECK_ENABLED is absent/false nothing happens."""
        monkeypatch.delenv("AUTOBOT_INTEGRITY_CHECK_ENABLED", raising=False)
        monkeypatch.setenv("AUTOBOT_INTEGRITY_MANIFEST_PATH", str(tmp_path / "x.json"))
        import logging

        with caplog.at_level(logging.WARNING):
            verify_integrity_at_startup()

        # No warnings — function bailed early
        assert caplog.records == []

    def test_missing_manifest_path_env_warns(self, monkeypatch, caplog):
        monkeypatch.setenv("AUTOBOT_INTEGRITY_CHECK_ENABLED", "1")
        monkeypatch.delenv("AUTOBOT_INTEGRITY_MANIFEST_PATH", raising=False)
        import logging

        with caplog.at_level(logging.WARNING):
            verify_integrity_at_startup()

        assert any("AUTOBOT_INTEGRITY_MANIFEST_PATH" in r.message for r in caplog.records)

    def test_missing_manifest_file_is_nonfatal(self, monkeypatch, tmp_path, caplog):
        monkeypatch.setenv("AUTOBOT_INTEGRITY_CHECK_ENABLED", "1")
        monkeypatch.setenv("AUTOBOT_INTEGRITY_MANIFEST_PATH", str(tmp_path / "nonexistent.json"))
        import logging

        with caplog.at_level(logging.WARNING):
            verify_integrity_at_startup()  # must not raise

        assert any("not found" in r.message for r in caplog.records)

    def test_tampered_file_logs_warning(self, monkeypatch, tmp_path, caplog):
        # Build a manifest, then tamper with the file
        f = tmp_path / "ruff.toml"
        f.write_bytes(b"clean")
        manifest = compute_manifest([str(f)], root=str(tmp_path))
        manifest_file = tmp_path / "manifest.json"
        write_manifest(manifest, str(manifest_file))

        f.write_bytes(b"TAMPERED")

        monkeypatch.setenv("AUTOBOT_INTEGRITY_CHECK_ENABLED", "1")
        monkeypatch.setenv("AUTOBOT_INTEGRITY_MANIFEST_PATH", str(manifest_file))
        import logging

        with caplog.at_level(logging.WARNING):
            verify_integrity_at_startup(root=str(tmp_path))

        assert any("TAMPERED" in r.message for r in caplog.records)

    def test_clean_files_logs_info(self, monkeypatch, tmp_path, caplog):
        f = tmp_path / "ruff.toml"
        f.write_bytes(b"clean")
        manifest = compute_manifest([str(f)], root=str(tmp_path))
        manifest_file = tmp_path / "manifest.json"
        write_manifest(manifest, str(manifest_file))

        monkeypatch.setenv("AUTOBOT_INTEGRITY_CHECK_ENABLED", "1")
        monkeypatch.setenv("AUTOBOT_INTEGRITY_MANIFEST_PATH", str(manifest_file))
        import logging

        with caplog.at_level(logging.INFO):
            verify_integrity_at_startup(root=str(tmp_path))

        assert any("verified OK" in r.message for r in caplog.records)

    def test_corrupt_json_manifest_is_nonfatal(self, monkeypatch, tmp_path, caplog):
        bad = tmp_path / "bad.json"
        bad.write_text("not json{{", encoding="utf-8")

        monkeypatch.setenv("AUTOBOT_INTEGRITY_CHECK_ENABLED", "1")
        monkeypatch.setenv("AUTOBOT_INTEGRITY_MANIFEST_PATH", str(bad))
        import logging

        with caplog.at_level(logging.WARNING):
            verify_integrity_at_startup()  # must not raise

        assert any("cannot load" in r.message for r in caplog.records)
