# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#12450 phase 2: worker components gain a real per-component resolve path.

Phase 1 (#12574) gave ai-stack / npu-worker / browser-worker / slm-agent
read-only drift visibility but deliberately kept them OUT of ALLOWED_COMPONENTS,
because whitelisting resolve without a post-sync definition "would rsync files
but never install deps or restart the right service".

Phase 2 supplies that definition. These tests pin the parts that are NOT
derivable by convention and would silently half-update a running worker if they
regressed — above all the restart targets, which for half of these components do
not match the component name.
"""

from __future__ import annotations

import ast
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_BACKEND_ROOT))

# Same import shims as test_status_stale_components_11820.py: stub the
# conflicting multipart package and swap benign dicts in for MagicMock schema
# names so api.code_sync imports under the conftest stub regime.
if "multipart" in sys.modules and not hasattr(sys.modules["multipart"], "multipart"):
    sys.modules.pop("multipart", None)
_mp_stub = types.ModuleType("multipart")
_mp_stub.multipart = types.ModuleType("multipart.multipart")  # type: ignore[attr-defined]
sys.modules.setdefault("multipart", _mp_stub)
sys.modules.setdefault("multipart.multipart", _mp_stub.multipart)  # type: ignore[attr-defined]

_code_sync_src = (_BACKEND_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
_SCHEMA_NAMES = tuple(
    sorted(
        alias.name
        for node in ast.walk(ast.parse(_code_sync_src))
        if isinstance(node, ast.ImportFrom) and node.module == "models.schemas"
        for alias in node.names
    )
)
_schemas_stub = sys.modules.get("models.schemas")
if isinstance(_schemas_stub, MagicMock):
    for _name in _SCHEMA_NAMES:
        setattr(_schemas_stub, _name, dict)


_WORKERS = (
    "autobot-ai-stack",
    "autobot-npu-worker",
    "autobot-browser-worker",
    "autobot-slm-agent",
)


def _load_drift_checker():
    """Load services/drift_checker.py for real.

    The slm-backend conftest registers ``services`` as a MagicMock package, so a
    plain ``from services.drift_checker import ALLOWED_COMPONENTS`` yields a mock
    attribute and every set assertion below would vacuously "pass". Load the real
    module by file location instead (same approach as
    tests/services/drift_checker_test.py). Its own ``services.*`` imports stay
    stubbed — irrelevant here, since these tests only read the component sets.
    """
    import importlib.util

    services_dir = _BACKEND_ROOT / "services"
    saved = sys.modules.get("services")
    pkg = types.ModuleType("services")
    pkg.__path__ = [str(services_dir)]  # type: ignore[attr-defined]
    sys.modules["services"] = pkg
    try:
        spec = importlib.util.spec_from_file_location("_drift_checker_12450", services_dir / "drift_checker.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is None:
            sys.modules.pop("services", None)
        else:
            sys.modules["services"] = saved


_dc = _load_drift_checker()


# ---------------------------------------------------------------------------
# Gating: resolve now accepts the workers; visibility is unchanged
# ---------------------------------------------------------------------------


def test_workers_are_resolve_capable():
    """ALLOWED_COMPONENTS gates /drift/resolve[-async]; the workers 400'd before."""
    for worker in _WORKERS:
        assert worker in _dc.ALLOWED_COMPONENTS, f"{worker} still rejected by resolve"


def test_visibility_surface_is_unchanged_by_the_promotion():
    """Promotion must move components between sets, never drop any from view.

    VISIBILITY_COMPONENTS is the union used by the GET-only drift surfaces
    (/status stale_components, GET /drift). Moving an entry from the read-only
    set into the allowlist must leave that union identical — otherwise #12574's
    drift signal silently regresses.
    """
    assert _dc.VISIBILITY_COMPONENTS == _dc.ALLOWED_COMPONENTS | _dc.EXTRA_VISIBILITY_COMPONENTS
    for worker in _WORKERS:
        assert worker in _dc.VISIBILITY_COMPONENTS
    assert "plugins" in _dc.VISIBILITY_COMPONENTS


def test_plugins_stays_visibility_only():
    """plugins syncs into TWO deployed locations, so it has no single resolve
    target and must NOT be promoted without an owner decision."""
    assert "plugins" in _dc.EXTRA_VISIBILITY_COMPONENTS
    assert "plugins" not in _dc.ALLOWED_COMPONENTS


# ---------------------------------------------------------------------------
# Restart targets — the half-update risk this whole change hinges on
# ---------------------------------------------------------------------------


def test_every_worker_has_an_explicit_restart_target():
    """A worker with no mapping would rsync and restart NOTHING — the exact
    silent half-update #12574 refused to ship."""
    import api.code_sync as cs

    for worker in _WORKERS:
        assert cs._COMPONENT_SERVICES.get(worker), f"{worker} has no restart target"


def test_restart_targets_that_do_not_match_the_component_name():
    """These two are the reason a name-derived mapping is unsafe.

    slm-agent's unit is autobot-agent (roles/slm_agent/tasks/main.yml:27,:33) and
    browser-worker's is autobot-playwright (roles/browser/tasks/main.yml:295-298).
    Deriving "autobot-slm-agent" / "autobot-browser-worker" would restart units
    that do not exist, leaving the worker running pre-sync code.
    """
    import api.code_sync as cs

    assert cs._COMPONENT_SERVICES["autobot-slm-agent"] == ["autobot-agent"]
    assert cs._COMPONENT_SERVICES["autobot-browser-worker"][0] == "autobot-playwright"


def test_ai_stack_restarts_both_units_in_ansible_order():
    """The ai-stack component tree installs BOTH units and the chroma binary
    lives in its venv (MVA-79), so a sync affects both.

    Order mirrors the role's own restart order: roles/ai-stack/handlers/main.yml
    defines `restart chromadb` before `restart ai-stack`, and ansible runs
    handlers in definition order, so chromadb comes up first.
    """
    import api.code_sync as cs

    assert cs._COMPONENT_SERVICES["autobot-ai-stack"] == [
        "autobot-chromadb",
        "autobot-ai-stack",
    ]


# ---------------------------------------------------------------------------
# Dependency install: only where ansible itself installs from a file
# ---------------------------------------------------------------------------


def test_only_ai_stack_installs_deps_and_from_requirements_ai_txt():
    """ai-stack's ansible role installs requirements-ai.txt — NOT the
    conventional requirements.txt — into its own venv."""
    import api.code_sync as cs

    assert set(cs._WORKER_COMPONENT_PIP) == {"autobot-ai-stack"}
    req_path, pip_bin = cs._WORKER_COMPONENT_PIP["autobot-ai-stack"]
    assert req_path.endswith("/requirements-ai.txt")
    assert pip_bin.endswith("/venv/bin/pip")


def test_ansible_managed_workers_have_no_pip_step():
    """npu-worker, browser-worker and slm-agent get their deps from an explicit
    ansible package LIST, not a requirements file a code sync can refresh.

    npu-worker is the dangerous one: the repo ships
    autobot-npu-worker/requirements.txt but ansible never installs it, so
    running it could pull a different OpenVINO build than the role pinned.
    """
    import api.code_sync as cs

    for worker in ("autobot-npu-worker", "autobot-browser-worker", "autobot-slm-agent"):
        assert worker not in cs._WORKER_COMPONENT_PIP
        assert worker not in cs._COMPONENT_PIP_PATHS


def test_deps_changed_watches_the_ai_stack_requirements_filename():
    """Without this the deps_changed signal reports an ai-stack dep bump as a
    code-only change."""
    import api.code_sync as cs

    assert "requirements-ai.txt" in cs._DEPS_FILES


# ---------------------------------------------------------------------------
# Routing: workers must NOT inherit the backend-shaped post-sync path
# ---------------------------------------------------------------------------


def test_workers_are_not_treated_as_backends():
    """The backend branch runs constraints deploy, interpreter provisioning,
    venv RECREATION, alembic and autobot_shared symlink restore. None apply to a
    worker, and venv recreation would wipe the venv chroma runs from (MVA-79).
    """
    import api.code_sync as cs

    for worker in _WORKERS:
        assert worker in cs._WORKER_COMPONENTS
        assert worker not in cs._BACKEND_COMPONENTS
        assert worker not in cs._COMPONENT_FRONTEND_DIRS


def test_worker_branch_is_evaluated_before_the_shared_library_branch():
    """_run_post_sync_steps routes on `elif component in _COMPONENT_SERVICES`
    for autobot_shared. The workers are in that map too (they need restart
    targets), so their own branch must come FIRST or they would run the
    autobot_shared path and restore both backends' symlinks instead.
    """
    import inspect

    import api.code_sync as cs

    src = inspect.getsource(cs._run_post_sync_steps)
    assert src.index("_WORKER_COMPONENTS") < src.index("elif component in _COMPONENT_SERVICES")


def test_missing_venv_skips_for_workers_but_still_fails_for_backends():
    """The missing-venv relaxation must be worker-scoped.

    A worker venv is provisioned by ansible, never by code-sync, so an absent
    one means "not deployed on this node" and the code rsync + restart is still
    valid. Applying the same relaxation to a backend would swallow a genuine pip
    failure that #11322 exists to surface (pip_ok=False).
    """
    import asyncio
    from unittest.mock import AsyncMock, patch

    import api.code_sync as cs

    missing_pip = "/nonexistent/venv/bin/pip"

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"boom", b""))
        return proc

    def _run(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    with patch("pathlib.Path.exists", return_value=True):
        # Worker: requirements present, venv pip absent → skip, resolve survives.
        with patch.dict(cs._WORKER_COMPONENT_PIP, {"worker-comp": ("/req.txt", missing_pip)}):
            with patch("api.code_sync.Path") as fake_path:
                fake_path.side_effect = lambda p: _StubPath(p, missing_pip)
                steps: list[str] = []
                assert _run(cs._install_pip_deps_for_component("worker-comp", steps)) is True
                assert any("provisioned by ansible" in s for s in steps)

    # Backend with the same absent pip must NOT take the skip path.
    with patch.dict(cs._COMPONENT_PIP_PATHS, {"backend-comp": ("/req.txt", missing_pip)}):
        with patch("api.code_sync.Path") as fake_path:
            fake_path.side_effect = lambda p: _StubPath(p, missing_pip)
            with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
                steps = []
                assert _run(cs._install_pip_deps_for_component("backend-comp", steps)) is False


class _StubPath:
    """Path stub: everything exists except the designated missing pip binary."""

    def __init__(self, p, missing):
        self._p = str(p)
        self._missing = missing

    def exists(self):
        return self._p != self._missing

    @property
    def parent(self):
        return _StubPath(self._p.rsplit("/", 1)[0], self._missing)

    def __str__(self):
        return self._p
