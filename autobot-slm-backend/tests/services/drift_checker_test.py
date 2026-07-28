# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for DriftChecker service — expected-drift exclusions (Issue #4610).

Verifies that deployment-generated files (ansible/enroll.yml,
ansible/inventory/localhost.yml, and autobot_shared/* files) are excluded from
the drift report even when their checksums differ between source and deployed.
"""

import importlib.util
import sys
import tempfile
import types
from pathlib import Path

_services_dir = Path(__file__).parent.parent.parent / "services"


def _load_service_module(name: str, filename: str):
    """Load a services/*.py module standalone, bypassing services/__init__.py."""
    spec = importlib.util.spec_from_file_location(name, _services_dir / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# drift_checker imports ``services.deploy_artifacts`` (canonical artifact
# vocabulary, #11459) and ``services.git_tracker`` at module scope. Register a
# minimal ``services`` package whose __path__ is the real directory so those
# submodule imports resolve from disk WITHOUT executing the heavy
# services/__init__.py chain (fastapi/redis/etc.).
if "services" not in sys.modules:
    _services_pkg = types.ModuleType("services")
    _services_pkg.__path__ = [str(_services_dir)]  # type: ignore[attr-defined]
    sys.modules["services"] = _services_pkg

# The slm-backend root conftest pre-stubs ``services.deploy_artifacts`` and
# ``services.git_tracker`` as MagicMocks (both are api/code_sync.py imports),
# so ``if X not in sys.modules`` guards are no-ops and drift_checker would
# bind _SKIP_DIR_SUFFIXES to a MagicMock — ``str.endswith(MagicMock)`` then
# raises TypeError at walk time (#11737).  Force the REAL deploy_artifacts
# (import-light constants) and a thin git_tracker shim (drift_checker only
# needs DEFAULT_REPO_PATH; the real module pulls in models.database) into
# sys.modules for the duration of the drift_checker load, then restore the
# pre-existing entries so sibling test files are unaffected (#11478 pattern).
_real_deploy_artifacts = _load_service_module("services.deploy_artifacts", "deploy_artifacts.py")
_git_tracker_stub = types.ModuleType("services.git_tracker")
_git_tracker_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]

_SWAPPED_KEYS = ("services.deploy_artifacts", "services.git_tracker")
_orig_modules = {_key: sys.modules.get(_key) for _key in _SWAPPED_KEYS}
sys.modules["services.deploy_artifacts"] = _real_deploy_artifacts
sys.modules["services.git_tracker"] = _git_tracker_stub
try:
    # Load drift_checker without triggering services/__init__.py import chain.
    drift_checker = _load_service_module("drift_checker", "drift_checker.py")
finally:
    for _key, _mod in _orig_modules.items():
        if _mod is not None:
            sys.modules[_key] = _mod
        else:
            sys.modules.pop(_key, None)

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

    def test_egg_info_dir_not_reported_as_drift(self):
        """#11440: <pkg>.egg-info build-artifact dirs (deployed-only, pip-generated)
        are pruned from the walk, not reported as permanent false drift. Their
        contents are .txt (an included extension), so without the suffix-skip they
        would surface as deployed-only drift forever."""
        with tempfile.TemporaryDirectory() as src_root, tempfile.TemporaryDirectory() as dep_root:
            src = Path(src_root)
            dep = Path(dep_root)

            self._write(src, "main.py", b"import os")
            self._write(dep, "main.py", b"import os")

            # pip-install artifacts present ONLY in the deployed dir.
            self._write(dep, "autobot_shared.egg-info/SOURCES.txt", b"main.py\n")
            self._write(dep, "autobot_shared.egg-info/requires.txt", b"redis\n")
            self._write(dep, "autobot_shared.egg-info/top_level.txt", b"autobot_shared\n")
            self._write(dep, "autobot_shared.egg-info/dependency_links.txt", b"\n")

            drifted, _ = compute_drift(str(src), str(dep))
            paths = [d["path"] for d in drifted]
            assert paths == [], f"egg-info artifacts must not be reported as drift, got: {paths}"

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


class TestTemplatedComponentDrift:
    """Render-invariant drift for template-deployed components (#12886).

    ``autobot-tts-worker`` is deployed as a rendered Jinja2 template, so a
    directory checksum walk reports nothing but fake drift (the repo dir ships
    main.py; the host runs tts-worker.py). It was therefore excluded from drift
    entirely — and silently fell behind the backend calling it until users hit
    a runtime 404 on /tts/synthesize/stream. These tests pin both halves of the
    replacement: a render must NOT read as drift, a missing route MUST.
    """

    REPO_ROOT = Path(__file__).parent.parent.parent.parent
    TEMPLATE_REL, DEPLOYED_REL = drift_checker._TEMPLATED_COMPONENTS["autobot-tts-worker"]

    def _render(self) -> str:
        """Substitute every Jinja expression the way ansible's template task would."""
        import re

        template = (self.REPO_ROOT / self.TEMPLATE_REL).read_text(encoding="utf-8")
        assert "{{" in template, "template has no Jinja expressions — test is vacuous"
        return re.sub(r"{{.*?}}", "/opt/autobot/rendered-value", template)

    def _drift_for(self, deployed_text: str | None, monkeypatch):
        monkeypatch.setattr(drift_checker, "DEFAULT_REPO_PATH", str(self.REPO_ROOT))
        with tempfile.TemporaryDirectory() as dep_root:
            if deployed_text is not None:
                (Path(dep_root) / self.DEPLOYED_REL).write_text(deployed_text, encoding="utf-8")
            return compute_drift("unused-for-templated-components", dep_root, "autobot-tts-worker")

    def test_visible_but_not_resolve_capable(self):
        """Drift surfaces see the worker; resolve still rejects it (no re-render path)."""
        assert "autobot-tts-worker" in drift_checker.VISIBILITY_COMPONENTS
        assert "autobot-tts-worker" not in drift_checker.ALLOWED_COMPONENTS

    def test_faithful_render_is_not_drift(self, monkeypatch):
        """Substituted values must never register as drift — the fake-drift guard."""
        drifted, total = self._drift_for(self._render(), monkeypatch)

        assert drifted == [], f"faithful render reported fake drift: {drifted}"
        assert total == 1

    def test_missing_route_is_drift(self, monkeypatch):
        """A stale worker missing a route the backend calls must be reported."""
        stale = self._render().replace('@app.post("/tts/synthesize/stream")', '@app.post("/tts/unused")')
        drifted, total = self._drift_for(stale, monkeypatch)

        assert total == 1
        assert [d["status"] for d in drifted] == ["modified"]
        assert drifted[0]["path"] == self.DEPLOYED_REL

    def test_dropped_function_is_drift(self, monkeypatch):
        """Structure comparison catches removed code, not just changed route strings."""
        rendered = self._render()
        marker = "def _run_clone_synthesis(text: str, audio_path: str) -> bytes:"
        assert marker in rendered, "clone-synthesis helper missing from template (#12886)"
        stale = rendered.replace(marker, "def _run_clone_synthesis(text, audio_path):")

        drifted, _ = self._drift_for(stale, monkeypatch)

        assert [d["status"] for d in drifted] == ["modified"]

    def test_absent_deployed_file_is_drift(self, monkeypatch):
        """A host that never received the rendered file reads as source_only, not silence."""
        drifted, total = self._drift_for(None, monkeypatch)

        assert total == 1
        assert drifted[0]["status"] == "source_only"
        assert drifted[0]["deployed_checksum"] is None

    def test_unparseable_deployed_file_is_drift(self, monkeypatch):
        """Corrupt deployed code falls back to a raw checksum rather than reporting clean."""
        drifted, _ = self._drift_for("def broken( :\n", monkeypatch)

        assert [d["status"] for d in drifted] == ["modified"]
        assert drifted[0]["deployed_checksum"] is not None

    def test_different_rendered_values_are_not_drift(self, monkeypatch):
        """Two hosts rendered with different vars must both read clean."""
        import re

        template = (self.REPO_ROOT / self.TEMPLATE_REL).read_text(encoding="utf-8")
        other_host = re.sub(r"{{.*?}}", "/srv/elsewhere/other-value", template)

        drifted, total = self._drift_for(other_host, monkeypatch)

        assert drifted == [], f"a differently-rendered host reported drift: {drifted}"
        assert total == 1
