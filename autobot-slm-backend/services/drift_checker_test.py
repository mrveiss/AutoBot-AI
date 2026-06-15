# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
_BACKEND_EXTENSIONS = _dc._BACKEND_EXTENSIONS
_FRONTEND_EXTENSIONS = _dc._FRONTEND_EXTENSIONS
_FRONTEND_COMPONENTS = _dc._FRONTEND_COMPONENTS
comparable_extensions = _dc.comparable_extensions


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


# ===========================================================================
# Extension sets and frontend drift (Issue #10120)
# ===========================================================================


class TestExtensionSets:
    """Verify that the extension constants are correctly structured (Issue #10120)."""

    def test_backend_extensions_subset_of_include(self):
        """Every backend extension must be in the unified _INCLUDE_EXTENSIONS set."""
        assert _BACKEND_EXTENSIONS <= _INCLUDE_EXTENSIONS

    def test_frontend_extensions_subset_of_include(self):
        """Every frontend extension must be in the unified _INCLUDE_EXTENSIONS set."""
        assert _FRONTEND_EXTENSIONS <= _INCLUDE_EXTENSIONS

    def test_frontend_extensions_present(self):
        """Core frontend source extensions are all in _INCLUDE_EXTENSIONS."""
        required = {".vue", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".html", ".json"}
        assert required <= _INCLUDE_EXTENSIONS, (
            f"Missing frontend extensions: {required - _INCLUDE_EXTENSIONS}"
        )

    def test_frontend_components_named_correctly(self):
        """_FRONTEND_COMPONENTS names match the ALLOWED_COMPONENTS frontend entries."""
        expected_frontends = {"autobot-frontend", "autobot-slm-frontend"}
        assert _FRONTEND_COMPONENTS == expected_frontends

    def test_no_build_artifact_extensions_added(self):
        """Map/lock extensions that only appear as build output are not included."""
        build_only = {".map", ".wasm", ".br", ".gz"}
        overlap = build_only & _INCLUDE_EXTENSIONS
        assert not overlap, f"Build-artifact extensions must not be included: {overlap}"


class TestFrontendDriftDetection:
    """
    Regression tests for Issue #10120.

    Before the fix, _INCLUDE_EXTENSIONS contained only backend extensions
    (.py/.yaml/...) so a frontend component whose source consists of .vue/.ts/.css
    files produced total_compared≈0 and drift_detected=False even when 200+ source
    files differed.  These tests assert the corrected behaviour.
    """

    # ------------------------------------------------------------------
    # REGRESSION: .vue file drift was invisible before fix
    # ------------------------------------------------------------------

    def test_vue_file_drift_detected(self, tmp_path):
        """REGRESSION (#10120): a changed .vue file must appear in drifted_files."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "App.vue", b"<template>v1</template>")
        _write(dep / "App.vue", b"<template>v2</template>")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1, "App.vue must be compared"
        assert len(drifted) == 1
        assert drifted[0]["path"] == "App.vue"
        assert drifted[0]["status"] == "modified"

    def test_ts_file_drift_detected(self, tmp_path):
        """REGRESSION (#10120): a changed .ts file must appear in drifted_files."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "main.ts", b"const x = 1")
        _write(dep / "main.ts", b"const x = 2")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted[0]["path"] == "main.ts"
        assert drifted[0]["status"] == "modified"

    def test_css_file_drift_detected(self, tmp_path):
        """REGRESSION (#10120): a changed .css file must appear in drifted_files."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "styles.css", b"body { color: red; }")
        _write(dep / "styles.css", b"body { color: blue; }")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted[0]["status"] == "modified"

    def test_frontend_source_only_in_source_is_detected(self, tmp_path):
        """A .vue file present in source but not deployed → 'source_only' drift."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        dep.mkdir()
        _write(src / "views" / "HomeView.vue", b"<template>Home</template>")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted[0]["path"] == "views/HomeView.vue"
        assert drifted[0]["status"] == "source_only"

    def test_mixed_frontend_and_backend_drift(self, tmp_path):
        """Both .py and .vue drifts are detected in a mixed component."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "server.py", b"v1")
        _write(dep / "server.py", b"v2")
        _write(src / "App.vue", b"<template>v1</template>")
        _write(dep / "App.vue", b"<template>v2</template>")
        _write(src / "same.yaml", b"config: 1")
        _write(dep / "same.yaml", b"config: 1")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 3
        paths = {e["path"] for e in drifted}
        assert "server.py" in paths
        assert "App.vue" in paths
        assert "same.yaml" not in paths

    def test_build_drift_report_frontend_drift_detected_true(self, tmp_path):
        """build_drift_report returns drift_detected=True for a changed .vue file."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "Component.vue", b"<template>source</template>")
        _write(dep / "Component.vue", b"<template>deployed</template>")
        report = build_drift_report(str(src), str(dep))
        assert report["drift_detected"] is True
        assert report["total_compared"] == 1
        assert len(report["drifted_files"]) == 1

    # ------------------------------------------------------------------
    # node_modules / dist must remain excluded despite frontend extensions
    # ------------------------------------------------------------------

    def test_node_modules_excluded_even_with_js_extensions(self, tmp_path):
        """node_modules/.ts and node_modules/.vue files are never compared."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        # Both sides have a real source file (identical — no drift).
        _write(src / "App.vue", b"same")
        _write(dep / "App.vue", b"same")
        # Deployed side has node_modules with a different .ts file (must be ignored).
        _write(dep / "node_modules" / "lodash" / "index.ts", b"different ts in nm")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1, "Only App.vue must be compared; node_modules must be skipped"
        assert drifted == [], "App.vue is identical — no drift"

    def test_dist_excluded_even_with_js_extensions(self, tmp_path):
        """dist/*.js build artifacts are never compared."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "main.ts", b"source ts")
        _write(dep / "main.ts", b"source ts")
        # Deployed dist/ has a different .js bundle (must be ignored).
        _write(dep / "dist" / "assets" / "index.js", b"bundled output")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1, "Only main.ts must be compared; dist/ must be skipped"
        assert drifted == [], "main.ts is identical — no drift"

    def test_build_dir_excluded(self, tmp_path):
        """build/ directory contents are never compared."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "index.ts", b"ts source")
        _write(dep / "index.ts", b"ts source")
        _write(dep / "build" / "chunk.js", b"compiled chunk")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted == []

    # ------------------------------------------------------------------
    # Backend component behaviour is unchanged
    # ------------------------------------------------------------------

    def test_backend_py_drift_still_detected(self, tmp_path):
        """Backend .py drift still detected — extension addition is additive."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "api.py", b"def get(): pass")
        _write(dep / "api.py", b"def get(): return 1")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted[0]["path"] == "api.py"
        assert drifted[0]["status"] == "modified"

    def test_backend_yaml_drift_still_detected(self, tmp_path):
        """Backend .yaml drift still detected after extension superset change."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "ansible" / "deploy.yaml", b"version: 1")
        _write(dep / "ansible" / "deploy.yaml", b"version: 2")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 1
        assert drifted[0]["status"] == "modified"

    def test_all_frontend_extensions_collected(self, tmp_path):
        """Every extension in _FRONTEND_EXTENSIONS produces a checksum entry."""
        for ext in _FRONTEND_EXTENSIONS:
            _write(tmp_path / f"file{ext}", b"content")
        result = _collect_checksums(tmp_path)
        for ext in _FRONTEND_EXTENSIONS:
            assert f"file{ext}" in result, f"Frontend extension {ext} not collected"


# ===========================================================================
# comparable_extensions (Issue #10120)
# ===========================================================================


class TestComparableExtensions:
    """Unit tests for the comparable_extensions() selector function."""

    def test_frontend_component_includes_vue(self):
        """autobot-frontend returns a set that includes .vue."""
        assert ".vue" in comparable_extensions("autobot-frontend")

    def test_frontend_component_includes_ts(self):
        """autobot-frontend returns a set that includes .ts."""
        assert ".ts" in comparable_extensions("autobot-frontend")

    def test_slm_frontend_component_includes_vue(self):
        """autobot-slm-frontend returns a set that includes .vue."""
        assert ".vue" in comparable_extensions("autobot-slm-frontend")

    def test_frontend_component_includes_backend_extensions(self):
        """Frontend extension set is a superset of the backend extensions."""
        assert _BACKEND_EXTENSIONS <= comparable_extensions("autobot-frontend")

    def test_backend_component_excludes_vue(self):
        """autobot-backend does NOT include .vue in its extension set."""
        assert ".vue" not in comparable_extensions("autobot-backend")

    def test_backend_component_excludes_ts(self):
        """autobot-backend does NOT include .ts in its extension set."""
        assert ".ts" not in comparable_extensions("autobot-backend")

    def test_backend_component_includes_py(self):
        """autobot-backend includes .py."""
        assert ".py" in comparable_extensions("autobot-backend")

    def test_slm_backend_component_excludes_vue(self):
        """autobot-slm-backend does NOT include .vue."""
        assert ".vue" not in comparable_extensions("autobot-slm-backend")

    def test_unknown_component_returns_backend_set(self):
        """An unknown component name falls back to the backend extension set."""
        assert comparable_extensions("unknown-component") == _BACKEND_EXTENSIONS

    def test_returns_frozenset(self):
        """Return type is frozenset for both component types."""
        assert isinstance(comparable_extensions("autobot-frontend"), frozenset)
        assert isinstance(comparable_extensions("autobot-backend"), frozenset)


# ===========================================================================
# Per-component compute_drift isolation (Issue #10120)
# ===========================================================================


class TestComputeDriftPerComponent:
    """Verify that the component parameter correctly scopes which files are compared."""

    def test_frontend_component_detects_vue_drift(self, tmp_path):
        """compute_drift with component='autobot-frontend' detects .vue drift."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "App.vue", b"<template>v1</template>")
        _write(dep / "App.vue", b"<template>v2</template>")
        drifted, total = compute_drift(str(src), str(dep), "autobot-frontend")
        assert total == 1
        assert drifted[0]["path"] == "App.vue"
        assert drifted[0]["status"] == "modified"

    def test_backend_component_ignores_vue_files(self, tmp_path):
        """compute_drift with component='autobot-backend' ignores .vue files."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        # .vue file differs — must be invisible for a backend component.
        _write(src / "App.vue", b"<template>src</template>")
        _write(dep / "App.vue", b"<template>dep</template>")
        # .py file differs — must be reported.
        _write(src / "app.py", b"v1")
        _write(dep / "app.py", b"v2")
        drifted, total = compute_drift(str(src), str(dep), "autobot-backend")
        assert total == 1, ".vue must be excluded for a backend component"
        assert drifted[0]["path"] == "app.py"

    def test_slm_frontend_component_detects_ts_drift(self, tmp_path):
        """compute_drift with component='autobot-slm-frontend' detects .ts drift."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "main.ts", b"const x = 1")
        _write(dep / "main.ts", b"const x = 2")
        drifted, total = compute_drift(str(src), str(dep), "autobot-slm-frontend")
        assert total == 1
        assert drifted[0]["path"] == "main.ts"

    def test_no_component_uses_full_union_set(self, tmp_path):
        """compute_drift without component uses _INCLUDE_EXTENSIONS union."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "App.vue", b"v1")
        _write(dep / "App.vue", b"v2")
        _write(src / "app.py", b"v1")
        _write(dep / "app.py", b"v2")
        drifted, total = compute_drift(str(src), str(dep))
        assert total == 2
        paths = {e["path"] for e in drifted}
        assert "App.vue" in paths
        assert "app.py" in paths

    def test_frontend_node_modules_excluded_with_component(self, tmp_path):
        """node_modules stay excluded even when component='autobot-frontend'."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        _write(src / "App.vue", b"same")
        _write(dep / "App.vue", b"same")
        _write(dep / "node_modules" / "react" / "index.ts", b"different")
        drifted, total = compute_drift(str(src), str(dep), "autobot-frontend")
        assert total == 1
        assert drifted == []
