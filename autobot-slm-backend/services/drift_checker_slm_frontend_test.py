# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the SLM frontend staged-release protection in
services/drift_checker.py (#16717).

Split out of services/drift_checker_test.py, which sits at its #14236
ceiling: a grandfathered file may not grow, so this class -- entirely new,
not moved logic -- gets its own file rather than pushing that file over.

Same offline contract as drift_checker_test.py: no filesystem reads beyond
tmp_path, no Redis, no network calls.
"""

import importlib
import sys
import types
from pathlib import Path

# ---------------------------------------------------------------------------
# Import drift_checker without pulling in the real services package or
# services.git_tracker (which requires SQLAlchemy, config, etc.) -- same
# harness as drift_checker_test.py and its siblings (test_resolve_deletion_
# guard_13851.py, test_worker_component_resolve_12450.py).
# ---------------------------------------------------------------------------

_SERVICES_DIR = Path(__file__).parent
_MODULE_PATH = _SERVICES_DIR / "drift_checker.py"

_gt_stub = types.ModuleType("services.git_tracker")
_gt_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]
sys.modules.setdefault("services.git_tracker", _gt_stub)

# services.deploy_artifacts must be REAL while drift_checker.py executes (the
# root conftest stubs it as a MagicMock) -- see drift_checker_test.py:34-39
# for the full rationale. The module is dependency-free, so real-load it and
# restore the previous sys.modules entry afterwards.
_da_spec = importlib.util.spec_from_file_location("services.deploy_artifacts", _SERVICES_DIR / "deploy_artifacts.py")
_da = importlib.util.module_from_spec(_da_spec)  # type: ignore[arg-type]
_da_spec.loader.exec_module(_da)  # type: ignore[union-attr]
_prev_da = sys.modules.get("services.deploy_artifacts")
sys.modules["services.deploy_artifacts"] = _da
try:
    _spec = importlib.util.spec_from_file_location("drift_checker", _MODULE_PATH)
    _dc = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
    _spec.loader.exec_module(_dc)  # type: ignore[union-attr]
finally:
    if _prev_da is None:
        sys.modules.pop("services.deploy_artifacts", None)
    else:
        sys.modules["services.deploy_artifacts"] = _prev_da

build_drift_report = _dc.build_drift_report
deploy_only_entries = _dc.deploy_only_entries


def _write(path: Path, content: bytes = b"hello") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


class TestSlmFrontendReleaseLayoutIsProtected:
    """#16717: a forced "resync from source" is a delete-style rsync with no
    exclude for autobot-slm-frontend's staged-release layout --
    current/previous (the served bundle and its rollback) and each
    dist-<build-id>/ directory (services/slm_frontend_build.py,
    SLM_FRONTEND_RELEASE_KEEP retained builds) were never tracked in git, so
    the (old, per-component) drift walk reported them as "untracked ... left
    over" and a forced resolve deleted them, live bundle and rollback
    included, with no earlier build left to fall back to.

    Every assertion here reads the protected names off services.deploy_artifacts
    (aliased ``_da``), never restating them -- a renamed prefix or symlink
    fails these tests automatically instead of silently going unprotected.
    """

    def test_release_names_are_protected_from_deletion(self):
        entries = deploy_only_entries("autobot-slm-frontend")
        assert _da.SLM_FRONTEND_CURRENT_LINK in entries
        assert _da.SLM_FRONTEND_PREVIOUS_LINK in entries
        assert _da.SLM_FRONTEND_LEGACY_DIR in entries
        assert f"{_da.SLM_FRONTEND_BUILD_PREFIX}*" in entries

    def test_every_retained_build_is_classified_as_release_artifact_not_untracked(self, tmp_path):
        """Three retained builds (the default SLM_FRONTEND_RELEASE_KEEP), none
        tracked in source -- the shape observed on 2026-09-14 (264 files
        across the three retained builds)."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        for build_id in ("20260901T000000000Z", "20260905T000000000Z", "20260910T000000000Z"):
            build_dir = f"{_da.SLM_FRONTEND_BUILD_PREFIX}{build_id}"
            _write(dep / build_dir / "index.html", b"<html></html>")
            _write(dep / build_dir / "assets" / "app.js", b"console.log(1)")

        report = build_drift_report(str(src), str(dep), "autobot-slm-frontend")
        assert report["untracked_files"] == []
        assert report["drift_detected"] is False

    def test_an_arbitrary_build_id_is_covered_not_a_hardcoded_example(self, tmp_path):
        """A genuine prefix match, not a restated literal for one build id --
        proven with a build id no other test in this file uses."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        weird_id = "99999999T999999999Z"
        _write(dep / f"{_da.SLM_FRONTEND_BUILD_PREFIX}{weird_id}" / "index.html", b"<html></html>")
        report = build_drift_report(str(src), str(dep), "autobot-slm-frontend")
        assert report["untracked_files"] == []

    def test_a_genuinely_removed_source_file_is_still_untracked(self, tmp_path):
        """The release-layout protection must not blanket the whole component
        -- an ordinary deployed file whose source was actually deleted
        (#16310's own ServicesView.vue example) must still surface."""
        src = tmp_path / "src"
        dep = tmp_path / "dep"
        src.mkdir()
        _write(dep / "ServicesView.vue", b"<template>old</template>")
        report = build_drift_report(str(src), str(dep), "autobot-slm-frontend")
        assert [e["path"] for e in report["untracked_files"]] == ["ServicesView.vue"]
