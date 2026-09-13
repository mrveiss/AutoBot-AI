# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for services/deployed_dir_resolver.py (#13539 B2, #15092).

Covers the READ (``get_live_dir``) / WRITE (``get_release_component_dir``)
split of ``drift_checker.get_default_deployed_dir``:

- Each form resolves the same path arithmetic ``get_default_deployed_dir``
  always did (env root, nonstandard-component overrides).
- The two forms AGREE on every allowed/extra-visibility component under
  today's flat layout — the "unchanged today" proof the split requires.
- ``tests/api/test_drift_resolve.py::
  test_resolve_drift_writes_to_release_component_dir_not_live_dir`` is the
  load-bearing companion to this file: it proves a real WRITE call site
  (``resolve_drift``) is wired to ``get_release_component_dir`` and not
  ``get_live_dir``, which no assertion in this file (both forms agreeing on
  a bare path) can show by itself.

Bootstrap mirrors ``drift_checker_test.py``: the root conftest stubs
``services.drift_checker`` (and its ``services.deploy_artifacts`` import) as
MagicMocks, but ``deployed_dir_resolver`` imports the real
``_NONSTANDARD_COMPONENT_PATHS`` dict from ``drift_checker`` at module load
time, so both must be real-loaded first.
"""

import importlib
import os
import sys
import types
from pathlib import Path
from unittest.mock import patch

_SERVICES_DIR = Path(__file__).parent

# Stub out services.git_tracker so drift_checker's module-level import succeeds.
_gt_stub = types.ModuleType("services.git_tracker")
_gt_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"  # type: ignore[attr-defined]
sys.modules.setdefault("services.git_tracker", _gt_stub)


def _real_load(name: str, path: Path):
    """Exec *path* under canonical *name*, registered in sys.modules so
    relative imports (``from services.drift_checker import ...``) resolve."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


_SWAPPED = ("services.deploy_artifacts", "services.drift_checker", "services.deployed_dir_resolver")
_prev_modules = {_name: sys.modules.get(_name) for _name in _SWAPPED}
try:
    _real_load("services.deploy_artifacts", _SERVICES_DIR / "deploy_artifacts.py")
    _dc = _real_load("services.drift_checker", _SERVICES_DIR / "drift_checker.py")
    _ddr = _real_load("services.deployed_dir_resolver", _SERVICES_DIR / "deployed_dir_resolver.py")
finally:
    for _name, _prev in _prev_modules.items():
        if _prev is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _prev

# Convenience aliases.
_resolve_deployed_dir = _ddr._resolve_deployed_dir
get_live_dir = _ddr.get_live_dir
get_release_component_dir = _ddr.get_release_component_dir
ALLOWED_COMPONENTS = _dc.ALLOWED_COMPONENTS
EXTRA_VISIBILITY_COMPONENTS = _dc.EXTRA_VISIBILITY_COMPONENTS
_NONSTANDARD_COMPONENT_PATHS = _dc._NONSTANDARD_COMPONENT_PATHS


class TestGetLiveDir:
    def test_default_root(self):
        """Without SLM_DEPLOYED_ROOT set, defaults to /opt/autobot/<component>."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SLM_DEPLOYED_ROOT", None)
            result = get_live_dir("autobot-slm-backend")
        assert result == "/opt/autobot/autobot-slm-backend"

    def test_env_override(self, tmp_path):
        """SLM_DEPLOYED_ROOT env var overrides the hardcoded /opt/autobot root."""
        custom_root = str(tmp_path / "custom_root")
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": custom_root}):
            result = get_live_dir("autobot-slm-backend")
        assert result == str(Path(custom_root) / "autobot-slm-backend")

    def test_component_appended(self, tmp_path):
        """The component name is appended as a sub-directory of the root,
        except for the #12450 nonstandard-path components."""
        root = str(tmp_path)
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": root}):
            for component in ALLOWED_COMPONENTS - set(_NONSTANDARD_COMPONENT_PATHS):
                result = get_live_dir(component)
                assert result == str(Path(root) / component)


class TestGetReleaseComponentDir:
    """Same cases as TestGetLiveDir, run through the writer form."""

    def test_default_root(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SLM_DEPLOYED_ROOT", None)
            result = get_release_component_dir("autobot-slm-backend")
        assert result == "/opt/autobot/autobot-slm-backend"

    def test_env_override(self, tmp_path):
        custom_root = str(tmp_path / "custom_root")
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": custom_root}):
            result = get_release_component_dir("autobot-slm-backend")
        assert result == str(Path(custom_root) / "autobot-slm-backend")

    def test_component_appended(self, tmp_path):
        root = str(tmp_path)
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": root}):
            for component in ALLOWED_COMPONENTS - set(_NONSTANDARD_COMPONENT_PATHS):
                result = get_release_component_dir(component)
                assert result == str(Path(root) / component)


class TestReaderWriterAgreeOnTodaysFlatLayout:
    """#13539 B2's "unchanged today" proof.

    The split makes the read/write distinction EXPRESSIBLE, not behaviourally
    different — yet. Until the release-flip scheme (#13539) lands, both
    forms must return the exact same value for every allowed component, in
    every environment configuration. This is the test that would fail first
    if the split accidentally changed behaviour instead of just vocabulary.
    """

    def test_agree_for_every_allowed_component_default_root(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SLM_DEPLOYED_ROOT", None)
            for component in ALLOWED_COMPONENTS:
                assert get_live_dir(component) == get_release_component_dir(component)

    def test_agree_for_every_allowed_component_custom_root(self, tmp_path):
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": str(tmp_path)}):
            for component in ALLOWED_COMPONENTS:
                assert get_live_dir(component) == get_release_component_dir(component)

    def test_agree_for_extra_visibility_components(self, tmp_path):
        """Read-only components (plugins, tts-worker) never resolve, but the
        two forms must still agree — a future writer promoted from this set
        (#12450) inherits agreement for free rather than a silent gap."""
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": str(tmp_path)}):
            for component in EXTRA_VISIBILITY_COMPONENTS:
                assert get_live_dir(component) == get_release_component_dir(component)


class TestNonstandardComponentDeployedPaths:
    """DEPLOYED-path half of #12450's override table (#13539 B2 split moved
    these out of drift_checker_test.py's TestNonstandardComponentPathMap,
    which keeps the SOURCE-path half)."""

    def test_ai_stack_deployed_path_strips_to_flat_dir(self):
        """--strip-components=4 (Play 2, ~1060-1064) lands ai-stack's contents
        flat under /opt/autobot/autobot-ai-stack, not a nested path."""
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": "/opt/autobot"}):
            result = get_live_dir("autobot-ai-stack")
        assert result == "/opt/autobot/autobot-ai-stack"

    def test_slm_agent_deployed_path_is_agent_subtree(self):
        """Deployed target is <slm_agent_dir>/slm/agent (role tasks ~132-213),
        not the top-level /opt/autobot/autobot-slm-agent dir (which also
        holds config.yaml/role.json/version.json — templated, not raw source)."""
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": "/opt/autobot"}):
            result = get_live_dir("autobot-slm-agent")
        assert result == "/opt/autobot/autobot-slm-agent/slm/agent"

    def test_plugins_deployed_path_is_inside_backend(self):
        """plugins/ is rsynced into the backend's own plugins/ subdirectory
        (backend role #10294), not a top-level /opt/autobot/plugins tree."""
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": "/opt/autobot"}):
            result = get_live_dir("plugins")
        assert result == "/opt/autobot/autobot-backend/plugins"

    def test_standard_components_are_unaffected_by_the_override_map(self, tmp_path):
        """npu-worker and browser-worker follow the standard
        code_source/<name> -> <root>/<name> convention — no override needed."""
        with patch.dict(os.environ, {"SLM_DEPLOYED_ROOT": str(tmp_path)}):
            assert get_live_dir("autobot-npu-worker") == str(tmp_path / "autobot-npu-worker")
            assert get_live_dir("autobot-browser-worker") == str(tmp_path / "autobot-browser-worker")
