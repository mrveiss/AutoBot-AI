# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for services/drift_checker.py (Issue #3428).

All tests are offline: no filesystem reads beyond tmp_path, no Redis,
no network calls.  External dependencies (services.git_tracker) are
patched at module-import time via monkeypatch / unittest.mock.
"""

import hashlib
import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Import drift_checker without pulling in the real services package or
# services.git_tracker (which requires SQLAlchemy, config, etc.).
# ---------------------------------------------------------------------------

_SERVICES_DIR = Path(__file__).parent
_MODULE_PATH = _SERVICES_DIR / "drift_checker.py"

# Stub out services.git_tracker so that the module-level import succeeds.
_gt_stub = types.ModuleType("services.git_tracker")
_gt_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]
sys.modules.setdefault("services.git_tracker", _gt_stub)

_spec = importlib.util.spec_from_file_location("drift_checker", _MODULE_PATH)
_dc = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_dc)  # type: ignore[union-attr]

# Convenience aliases.
_file_checksum = _dc._file_checksum
_collect_checksums = _dc._collect_checksums
compute_drift = _dc.compute_drift
build_drift_report = _dc.build_drift_report
get_default_source_dir = _dc.get_default_source_dir
get_default_deployed_dir = _dc.get_default_deployed_dir
ALLOWED_COMPONENTS = _dc.ALLOWED_COMPONENTS
_SKIP_DIRS = _dc._SKIP_DIRS
_INCLUDE_EXTENSIONS = _dc._INCLUDE_EXTENSIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _write(path: Path, content: bytes = b"hello") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ===========================================================================
# _file_checksum
# ===========================================================================


class TestFileChecksum:
    def test_known_content(self, tmp_path):
        """SHA-256 of a known byte sequence must match the reference digest."""
        data = b"autobot drift checker"
        f = _write(tmp_path / "sample.py", data)
        assert _file_checksum(f) == _sha256(data)

    def test_empty_file(self, tmp_path):
        """Empty file produces the SHA-256 of an empty byte string."""
        f = _write(tmp_path / "empty.py", b"")
        assert _file_checksum(f) == _sha256(b"")

    def test_large_file_chunked(self, tmp_path):
        """Files larger than a single block are hashed correctly."""
        # 3 * 65 536 bytes — forces multiple read iterations.
        data = b"x" * (3 * 65536)
        f = _write(tmp_path / "big.py", data)
        assert _file_checksum(f) == _sha256(data)

    def test_different_content_different_digest(self, tmp_path):
        f1 = _write(tmp_path / "a.py", b"version 1")
        f2 = _write(tmp_path / "b.py", b"version 2")
        assert _file_checksum(f1) != _file_checksum(f2)


# ===========================================================================
# _collect_checksums
# ===========================================================================


class TestCollectChecksums:
    def test_only_included_extensions(self, tmp_path):
        """Only files whose suffix is in _INCLUDE_EXTENSIONS appear in result."""
        _write(tmp_path / "script.py", b"a")
        _write(tmp_path / "config.yaml", b"b")
        _write(tmp_path / "readme.md", b"c")  # excluded
        _write(tmp_path / "image.png", b"d")  # excluded
        result = _collect_checksums(tmp_path)
        assert "script.py" in result
        assert "config.yaml" in result
        assert "readme.md" not in result
        assert "image.png" not in result

    def test_skips_excluded_dirs(self, tmp_path):
        """Directories in _SKIP_DIRS are not traversed."""
        for skip in _SKIP_DIRS:
            _write(tmp_path / skip / "hidden.py", b"skip me")
        _write(tmp_path / "visible.py", b"keep me")
        result = _collect_checksums(tmp_path)
        # No key should start with a skip-dir prefix.
        for key in result:
            top = key.split("/")[0]
            assert top not in _SKIP_DIRS, f"Key from skip dir leaked: {key}"
        assert "visible.py" in result

    def test_relative_paths_posix_style(self, tmp_path):
        """Returned keys are POSIX-style paths relative to root."""
        sub = tmp_path / "pkg" / "sub"
        _write(sub / "module.py", b"code")
        result = _collect_checksums(tmp_path)
        assert "pkg/sub/module.py" in result

    def test_empty_directory(self, tmp_path):
        """Empty directory produces an empty dict."""
        assert _collect_checksums(tmp_path) == {}

    def test_checksum_values_match_direct_hash(self, tmp_path):
        """Checksums in the returned dict match _file_checksum() directly."""
        data = b"deterministic content"
        _write(tmp_path / "check.py", data)
        result = _collect_checksums(tmp_path)
        assert result["check.py"] == _sha256(data)

    def test_unreadable_file_skipped(self, tmp_path, monkeypatch):
        """An unreadable file is skipped with a warning, not a raised exception."""
        _write(tmp_path / "bad.py", b"data")

        original_open = open

        def _mock_open(path, *args, **kwargs):
            if Path(path).name == "bad.py":
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr("builtins.open", _mock_open)
        # Must not raise; bad.py simply absent from result.
        result = _collect_checksums(tmp_path)
        assert "bad.py" not in result

    def test_all_included_extensions_accepted(self, tmp_path):
        """Every extension in _INCLUDE_EXTENSIONS produces an entry."""
        for ext in _INCLUDE_EXTENSIONS:
            _write(tmp_path / f"file{ext}", b"content")
        result = _collect_checksums(tmp_path)
        for ext in _INCLUDE_EXTENSIONS:
            assert f"file{ext}" in result, f"Extension {ext} not collected"


# ===========================================================================
# compute_drift
# ===========================================================================


class TestComputeDrift:
    def test_identical_dirs_no_drift(self, tmp_path):
        """Two directories with identical files return an empty drift list."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "app.py", b"same")
        _write(dep / "app.py", b"same")
        drifted, total = compute_drift(str(src), str(dep))
        assert drifted == []
        assert total == 1

    def test_modified_file_detected(self, tmp_path):
        """A file present in both dirs but with different content → 'modified'."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "worker.py", b"version 1")
        _write(dep / "worker.py", b"version 2")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert len(drifted) == 1
        entry = drifted[0]
        assert entry["path"] == "worker.py"
        assert entry["status"] == "modified"
        assert entry["source_checksum"] == _sha256(b"version 1")
        assert entry["deployed_checksum"] == _sha256(b"version 2")

    def test_source_only_file(self, tmp_path):
        """A file that exists only in source → 'source_only'."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        dep.mkdir()
        _write(src / "new_feature.py", b"not deployed yet")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert len(drifted) == 1
        entry = drifted[0]
        assert entry["status"] == "source_only"
        assert entry["source_checksum"] is not None
        assert entry["deployed_checksum"] is None

    def test_deployed_only_file(self, tmp_path):
        """A file that exists only in deployed dir → 'deployed_only'."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        _write(dep / "manual_patch.py", b"hotfix")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert len(drifted) == 1
        entry = drifted[0]
        assert entry["status"] == "deployed_only"
        assert entry["source_checksum"] is None
        assert entry["deployed_checksum"] is not None

    def test_mixed_drift(self, tmp_path):
        """Multiple drift categories are all reported correctly."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "same.py", b"shared")
        _write(dep / "same.py", b"shared")
        _write(src / "changed.py", b"old")
        _write(dep / "changed.py", b"new")
        _write(src / "src_only.py", b"new feature")
        _write(dep / "dep_only.py", b"manual patch")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 4
        statuses = {e["path"]: e["status"] for e in drifted}
        assert statuses["changed.py"] == "modified"
        assert statuses["src_only.py"] == "source_only"
        assert statuses["dep_only.py"] == "deployed_only"
        assert "same.py" not in statuses

    def test_results_sorted_by_path(self, tmp_path):
        """Drifted file list is returned in sorted path order."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        dep.mkdir()
        for name in ("zebra.py", "alpha.sh", "middle.yaml"):
            _write(src / name, b"x")
        drifted, _ = compute_drift(str(src), str(dep))
        paths = [e["path"] for e in drifted]
        assert paths == sorted(paths)

    def test_missing_source_dir_returns_empty(self, tmp_path):
        """Non-existent source_dir returns ([], 0) without raising."""
        dep = tmp_path / "dep"
        dep.mkdir()
        drifted, total = compute_drift(str(tmp_path / "nonexistent"), str(dep))
        assert drifted == []
        assert total == 0

    def test_missing_deployed_dir_returns_empty(self, tmp_path):
        """Non-existent deployed_dir returns ([], 0) without raising."""
        src = tmp_path / "src"
        src.mkdir()
        drifted, total = compute_drift(str(src), str(tmp_path / "nonexistent"))
        assert drifted == []
        assert total == 0

    def test_both_dirs_missing_returns_empty(self, tmp_path):
        """Both dirs missing returns ([], 0) without raising."""
        drifted, total = compute_drift(str(tmp_path / "no_src"), str(tmp_path / "no_dep"))
        assert drifted == []
        assert total == 0

    def test_total_compared_includes_all_unique_paths(self, tmp_path):
        """total_compared equals the union of all paths in both directories."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "a.py", b"1")
        _write(src / "b.py", b"2")
        _write(dep / "b.py", b"2")  # same — no drift but still counted
        _write(dep / "c.py", b"3")
        _, total = compute_drift(str(src), str(dep))
        # a.py (src only) + b.py (same) + c.py (dep only) = 3
        assert total == 3

    def test_non_included_extensions_ignored(self, tmp_path):
        """Files with extensions outside _INCLUDE_EXTENSIONS are ignored."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "logo.png", b"img")
        _write(dep / "logo.png", b"different img")
        _write(src / "notes.md", b"doc")
        _write(dep / "notes.md", b"different doc")
        drifted, total = compute_drift(str(src), str(dep))
        assert drifted == []
        assert total == 0

    def test_nested_subdirectory_paths(self, tmp_path):
        """Files inside subdirectories use POSIX relative paths."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        dep.mkdir()
        _write(src / "pkg" / "sub" / "module.py", b"nested")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted[0]["path"] == "pkg/sub/module.py"


# ===========================================================================
# build_drift_report
# ===========================================================================


class TestBuildDriftReport:
    def test_schema_keys_present(self, tmp_path):
        """Report contains all required schema keys."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        dep.mkdir()
        report = build_drift_report(str(src), str(dep))
        for key in (
            "source_dir",
            "deployed_dir",
            "drifted_files",
            "total_compared",
            "drift_detected",
            "checked_at",
        ):
            assert key in report, f"Missing key: {key}"

    def test_drift_detected_true_when_drifted(self, tmp_path):
        """drift_detected is True when at least one file differs."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "main.py", b"v1")
        _write(dep / "main.py", b"v2")
        report = build_drift_report(str(src), str(dep))
        assert report["drift_detected"] is True
        assert len(report["drifted_files"]) > 0

    def test_drift_detected_false_when_clean(self, tmp_path):
        """drift_detected is False when both dirs are identical."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "utils.py", b"same content")
        _write(dep / "utils.py", b"same content")
        report = build_drift_report(str(src), str(dep))
        assert report["drift_detected"] is False
        assert report["drifted_files"] == []

    def test_source_dir_and_deployed_dir_in_report(self, tmp_path):
        """Report echoes back the source_dir and deployed_dir values."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        dep.mkdir()
        report = build_drift_report(str(src), str(dep))
        assert report["source_dir"] == str(src)
        assert report["deployed_dir"] == str(dep)

    def test_total_compared_matches_compute_drift(self, tmp_path):
        """total_compared in report matches the value from compute_drift."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "a.py", b"x")
        _write(dep / "b.py", b"y")
        _, expected_total = compute_drift(str(src), str(dep))
        report = build_drift_report(str(src), str(dep))
        assert report["total_compared"] == expected_total

    def test_checked_at_is_utc_iso_string(self, tmp_path):
        """checked_at is a non-empty ISO 8601 string containing UTC offset."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        dep.mkdir()
        report = build_drift_report(str(src), str(dep))
        checked_at = report["checked_at"]
        assert isinstance(checked_at, str)
        assert len(checked_at) > 0
        # datetime.now(timezone.utc).isoformat() always contains '+00:00'
        assert "+00:00" in checked_at


# ===========================================================================
# get_default_deployed_dir
# ===========================================================================


class TestGetDefaultDeployedDir:
    def test_default_root(self):
        """Without SLM_DEPLOYED_ROOT set, defaults to /opt/autobot/<component>."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SLM_DEPLOYED_ROOT", None)
            result = get_default_deployed_dir("autobot-slm-backend")
        assert result == "/opt/autobot/autobot-slm-backend"

    def test_env_override(self, tmp_path):
        """SLM_DEPLOYED_ROOT env var overrides the hardcoded /opt/autobot root."""
        custom_root = str(tmp_path / "custom_root")
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": custom_root}):
            result = get_default_deployed_dir("autobot-slm-backend")
        assert result == str(Path(custom_root) / "autobot-slm-backend")

    def test_component_appended(self, tmp_path):
        """The component name is appended as a sub-directory of the root."""
        root = str(tmp_path)
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": root}):
            for component in ALLOWED_COMPONENTS:
                result = get_default_deployed_dir(component)
                assert result == str(Path(root) / component)


# ===========================================================================
# get_default_source_dir
# ===========================================================================


class TestGetDefaultSourceDir:
    def test_returns_path_when_dir_exists(self, tmp_path, monkeypatch):
        """Returns the candidate path string when the directory exists."""
        component = "autobot-slm-backend"
        fake_repo = tmp_path / "repo"
        (fake_repo / component).mkdir(parents=True)
        monkeypatch.setattr(_dc, "DEFAULT_REPO_PATH", str(fake_repo))
        result = get_default_source_dir(component)
        assert result == str(fake_repo / component)

    def test_raises_when_dir_missing(self, tmp_path, monkeypatch):
        """Raises ValueError when the component sub-directory does not exist."""
        monkeypatch.setattr(_dc, "DEFAULT_REPO_PATH", str(tmp_path / "empty_repo"))
        with pytest.raises(ValueError, match="does not exist"):
            get_default_source_dir("autobot-slm-backend")

    def test_env_var_respected_via_default_repo_path(self, tmp_path, monkeypatch):
        """DEFAULT_REPO_PATH (which reads SLM_REPO_PATH) controls the base dir."""
        component = "autobot-backend"
        alt_repo = tmp_path / "alt_repo"
        (alt_repo / component).mkdir(parents=True)
        monkeypatch.setattr(_dc, "DEFAULT_REPO_PATH", str(alt_repo))
        result = get_default_source_dir(component)
        assert result == str(alt_repo / component)


# ===========================================================================
# ALLOWED_COMPONENTS allowlist (Issue #3427)
# ===========================================================================


class TestAllowedComponents:
    def test_allowlist_contains_expected_components(self):
        """The allowlist must contain all four expected component names."""
        expected = {
            "autobot-slm-backend",
            "autobot-slm-frontend",
            "autobot-backend",
            "autobot-frontend",
        }
        assert expected == set(ALLOWED_COMPONENTS)

    def test_allowlist_is_frozenset(self):
        """ALLOWED_COMPONENTS must be a frozenset (immutable)."""
        assert isinstance(ALLOWED_COMPONENTS, frozenset)

    def test_path_traversal_not_in_allowlist(self):
        """Common path-traversal payloads are not in the allowlist."""
        traversal_attempts = [
            "../etc/passwd",
            "../../root",
            "/etc/passwd",
            "autobot-backend/../../../etc",
            ".",
            "..",
        ]
        for attempt in traversal_attempts:
            assert (
                attempt not in ALLOWED_COMPONENTS
            ), f"Path traversal payload '{attempt}' should not be in ALLOWED_COMPONENTS"
