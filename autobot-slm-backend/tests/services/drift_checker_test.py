# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for DriftChecker service — expected-drift exclusions (Issue #4610).

Verifies that deployment-generated files (ansible/enroll.yml,
ansible/inventory/localhost.yml, and autobot_shared/* files) are excluded from
the drift report even when their checksums differ between source and deployed.
"""

import tempfile
from pathlib import Path

# Load drift_checker without triggering services/__init__.py import chain.
_mod_path = Path(__file__).parent.parent.parent / "services" / "drift_checker.py"
_spec = __import__("importlib.util").util.spec_from_file_location("drift_checker", _mod_path)
drift_checker = __import__("importlib.util").util.module_from_spec(_spec)
_spec.loader.exec_module(drift_checker)

_is_expected_drift = drift_checker._is_expected_drift
compute_drift = drift_checker.compute_drift
build_drift_report = drift_checker.build_drift_report


class TestIsExpectedDrift:
    """Unit tests for _is_expected_drift() helper."""

    def test_enroll_yml_is_expected(self):
        assert _is_expected_drift("ansible/enroll.yml") is True

    def test_inventory_localhost_is_expected(self):
        assert _is_expected_drift("ansible/inventory/localhost.yml") is True

    def test_autobot_shared_prefix_is_expected(self):
        assert _is_expected_drift("autobot_shared/redis_client.py") is True
        assert _is_expected_drift("autobot_shared/ssot_config.py") is True
        assert _is_expected_drift("autobot_shared/utils/helpers.py") is True

    def test_autobot_shared_root_itself_not_matched(self):
        # The prefix match requires the slash — bare "autobot_shared" without
        # trailing slash should NOT match (it would never be a file anyway).
        assert _is_expected_drift("autobot_shared") is False

    def test_similar_but_different_paths_are_not_expected(self):
        assert _is_expected_drift("ansible/other.yml") is False
        assert _is_expected_drift("ansible/inventory/nodes.yml") is False
        assert _is_expected_drift("services/drift_checker.py") is False
        assert _is_expected_drift("main.py") is False

    def test_partial_prefix_no_false_positive(self):
        # A file named autobot_shared_extra.py should NOT be excluded.
        assert _is_expected_drift("autobot_shared_extra.py") is False


class TestComputeDriftExclusions:
    """Integration tests using real temp dirs to verify exclusion in compute_drift."""

    def _write(self, directory: Path, rel: str, content: bytes = b"data") -> None:
        target = directory / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def test_expected_drift_files_excluded_from_report(self):
        """Files matching expected-drift patterns must not appear in drifted list."""
        with tempfile.TemporaryDirectory() as src_root, tempfile.TemporaryDirectory() as dep_root:
            src = Path(src_root)
            dep = Path(dep_root)

            # Shared file — identical in both; no drift.
            self._write(src, "main.py", b"import os")
            self._write(dep, "main.py", b"import os")

            # Real-drift file — different content.
            self._write(src, "config.py", b"X=1")
            self._write(dep, "config.py", b"X=2")

            # Expected-drift: only in deployed, should be excluded.
            self._write(dep, "ansible/enroll.yml", b"enrolled: true")
            self._write(dep, "ansible/inventory/localhost.yml", b"ip: 10.0.0.1")
            self._write(dep, "autobot_shared/redis_client.py", b"# shared")
            self._write(dep, "autobot_shared/utils/helpers.py", b"# helpers")

            drifted, total = compute_drift(str(src), str(dep))

            paths = [d["path"] for d in drifted]

            # Only the genuinely modified file should appear.
            assert paths == ["config.py"], f"unexpected drift paths: {paths}"

    def test_real_drift_is_still_reported(self):
        """Files outside exclusion patterns must still appear when they differ."""
        with tempfile.TemporaryDirectory() as src_root, tempfile.TemporaryDirectory() as dep_root:
            src = Path(src_root)
            dep = Path(dep_root)

            self._write(src, "services/code_sync.py", b"v1")
            self._write(dep, "services/code_sync.py", b"v2")

            drifted, _ = compute_drift(str(src), str(dep))
            assert any(d["path"] == "services/code_sync.py" for d in drifted)

    def test_total_compared_excludes_expected_drift_paths(self):
        """total_compared must count only non-excluded paths (Issue #4631)."""
        with tempfile.TemporaryDirectory() as src_root, tempfile.TemporaryDirectory() as dep_root:
            src = Path(src_root)
            dep = Path(dep_root)

            # Two regular files that will be evaluated.
            self._write(src, "main.py", b"import os")
            self._write(dep, "main.py", b"import os")
            self._write(src, "config.py", b"X=1")
            self._write(dep, "config.py", b"X=2")

            # Expected-drift file — must NOT be counted in total_compared.
            self._write(dep, "autobot_shared/foo.py", b"# shared")

            _, total = compute_drift(str(src), str(dep))

            # Only main.py and config.py are evaluated; autobot_shared/foo.py
            # is excluded by _is_expected_drift() before counting.
            assert total == 2, f"expected total_compared=2 (excluding autobot_shared/foo.py), got {total}"

    def test_build_drift_report_excludes_expected_files(self):
        """build_drift_report() should not flag expected-drift paths."""
        with tempfile.TemporaryDirectory() as src_root, tempfile.TemporaryDirectory() as dep_root:
            src = Path(src_root)
            dep = Path(dep_root)

            # Expected-drift file in deployed only.
            self._write(dep, "ansible/enroll.yml", b"node_id: abc")

            report = build_drift_report(str(src), str(dep))

            assert report["drift_detected"] is False
            assert report["drifted_files"] == []
