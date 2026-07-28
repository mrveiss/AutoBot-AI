# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""drift/resolve must rsync the paths the override table declares (#12872).

#12450 gave the worker components a real per-component resolve path, but the
rsync step rebuilt the source as `{parent}/{component}` and the destination as
`/opt/autobot/{component}`. Components in _NONSTANDARD_COMPONENT_PATHS do not
live at a path ending in their own name:

    autobot-ai-stack   source .../shared/docker/ai-stack   (not .../autobot-ai-stack)
    autobot-slm-agent  deploys to autobot-slm-agent/slm/agent

So detection honoured the override while resolution did not, and those
components reported drift that could never be cleared.
"""

import importlib.util
import re
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[2]


def _load(name, rel):
    """Load past the suite's session-global stubs (mirrors sibling SLM tests)."""
    key = f"_{name}_12872"
    if key in sys.modules:
        return sys.modules[key]
    saved = sys.modules.get("autobot_shared.logging_manager")
    sys.modules["autobot_shared.logging_manager"] = MagicMock()
    try:
        spec = importlib.util.spec_from_file_location(key, _ROOT / rel)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[key] = mod
        spec.loader.exec_module(mod)
        return mod
    finally:
        if saved is None:
            sys.modules.pop("autobot_shared.logging_manager", None)
        else:
            sys.modules["autobot_shared.logging_manager"] = saved


drift = _load("drift", "services/drift_checker.py")

# The helpers validate that the resolved directory exists, and under the suite's
# stubs DEFAULT_REPO_PATH is a MagicMock. Point them at the real repo, which
# genuinely contains the override sources — so these assertions are about the
# actual layout, not a fixture that agrees with the code by construction.
_REPO = str(_ROOT.parent)


@pytest.fixture(autouse=True)
def _real_repo_path(monkeypatch):
    monkeypatch.setattr(drift, "DEFAULT_REPO_PATH", _REPO)
    monkeypatch.setenv("SLM_DEPLOYED_ROOT", "/opt/autobot")


# ---------------------------------------------------------------------------
# The override table is what resolve must follow
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("component", ["autobot-ai-stack", "autobot-slm-agent"])
def test_source_dir_does_not_end_in_the_component_name(component):
    """Precisely why rebuilding `{parent}/{component}` was wrong."""
    source = drift.get_default_source_dir(component)

    assert not source.endswith(f"/{component}"), (
        f"{component} source is {source}; rebuilding it from the component name "
        "would point rsync at a directory that does not exist"
    )


def test_ai_stack_source_is_the_mapped_leaf():
    assert drift.get_default_source_dir("autobot-ai-stack").endswith("/shared/docker/ai-stack")


def test_slm_agent_deploys_below_its_own_root():
    deployed = drift.get_default_deployed_dir("autobot-slm-agent")

    assert deployed.endswith("/autobot-slm-agent/slm/agent"), (
        f"deployed path is {deployed}; the standard /opt/autobot/<component> "
        "convention would sync to the wrong directory"
    )


def test_standard_components_are_unaffected():
    """The override must not change components that follow the convention."""
    src = drift.get_default_source_dir("autobot-slm-backend")
    dst = drift.get_default_deployed_dir("autobot-slm-backend")

    assert src.endswith("/autobot-slm-backend")
    assert dst.endswith("/autobot-slm-backend")


# ---------------------------------------------------------------------------
# The rsync helper must honour explicit paths
# ---------------------------------------------------------------------------


def _code_sync_src() -> str:
    """Read api/code_sync.py as text.

    It cannot be imported under the suite's stubs — its FastAPI routes reference
    stubbed Pydantic models and raise FastAPIError at import. Asserting on the
    source is honest here: an import-based test would either fail to load or
    pass against a mock.
    """
    return (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")


def test_rsync_helper_accepts_explicit_paths():
    """The helper must be able to take paths verbatim, not rebuild them."""
    src = _code_sync_src()
    fn = src[src.index("async def _rsync_component_local(") :]
    fn = fn[: fn.index("\nasync def ", 1)]

    assert "source_dir: str | None = None" in fn
    assert "dest_dir: str | None = None" in fn
    assert "source_dir or" in fn, "source must prefer the explicit path"
    assert "dest_dir or" in fn, "destination must prefer the explicit path"


def test_drift_resolve_passes_the_resolved_paths():
    """The resolve caller must hand over the override-aware paths."""
    src = _code_sync_src()
    call_start = src.index("ok, msg = await _rsync_component_local(\n        source_root,\n        request.component")
    call = src[call_start : call_start + 400]

    assert "source_dir=source_dir" in call, "resolve still rebuilds the source path"
    assert "dest_dir=deployed_dir" in call, "resolve still rebuilds the destination path"


def test_other_callers_keep_the_convention():
    """The four non-drift callers must be untouched, so their behaviour is unchanged."""
    src = _code_sync_src()
    calls = re.findall(r"_rsync_component_local\((.*?)\)", src, re.S)
    explicit = [c for c in calls if "source_dir=" in c or "dest_dir=" in c]

    assert len(explicit) == 1, f"expected only the drift-resolve caller to pass explicit paths, got {len(explicit)}"
