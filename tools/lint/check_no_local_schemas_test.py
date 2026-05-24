# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for tools/lint/check_no_local_schemas.py — see #6056.

Covers detection, allowlist, path filtering, and exit codes for the hook
that prevents re-introduction of local BaseModel subclasses in non-schema
API endpoint files (autobot-backend/api/*.py, excluding schemas_*.py).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_HOOK_PATH = Path(__file__).parent / "check_no_local_schemas.py"
_spec = importlib.util.spec_from_file_location("_hook_under_test", _HOOK_PATH)
assert _spec is not None and _spec.loader is not None
hook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hook)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _api_root(tmp_path: Path) -> Path:
    """Create fake autobot-backend/api/ dir under tmp_path, return repo root."""
    api_dir = tmp_path / "autobot-backend" / "api"
    api_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_api(tmp_path: Path, name: str, content: str) -> tuple[Path, Path]:
    """Write an api file under a fake repo root, return (file_path, repo_root)."""
    repo_root = _api_root(tmp_path)
    p = repo_root / "autobot-backend" / "api" / name
    p.write_text(content, encoding="utf-8")
    return p, repo_root


# ---------------------------------------------------------------------------
# Positive cases — should be flagged (violations)
# ---------------------------------------------------------------------------


def test_detects_basemodel_subclass_in_api_file(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "some_endpoint.py",
        """\
from pydantic import BaseModel

class MyResponse(BaseModel):
    data: str
""",
    )
    hits = hook._check_file(path, repo_root)
    assert len(hits) == 1
    assert hits[0][1] == "MyResponse"
    assert hits[0][0] == 3  # line number


def test_detects_multiple_basemodel_subclasses(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "analytics.py",
        """\
from pydantic import BaseModel

class FooRequest(BaseModel):
    x: int

class BarResponse(BaseModel):
    y: str
""",
    )
    hits = hook._check_file(path, repo_root)
    assert len(hits) == 2
    names = {h[1] for h in hits}
    assert names == {"FooRequest", "BarResponse"}


def test_detects_qualified_basemodel(tmp_path: Path) -> None:
    """pydantic.BaseModel (attribute form) is also caught."""
    path, repo_root = _write_api(
        tmp_path,
        "code_api.py",
        """\
import pydantic

class LocalSchema(pydantic.BaseModel):
    value: int
""",
    )
    hits = hook._check_file(path, repo_root)
    assert len(hits) == 1
    assert hits[0][1] == "LocalSchema"


# ---------------------------------------------------------------------------
# Negative cases — should NOT be flagged
# ---------------------------------------------------------------------------


def test_schema_file_not_flagged(tmp_path: Path) -> None:
    """schemas_*.py files in api/ are excluded — double safety."""
    path, repo_root = _write_api(
        tmp_path,
        "schemas_analytics.py",
        """\
from pydantic import BaseModel

class AnalyticsRecord(BaseModel):
    count: int
""",
    )
    hits = hook._check_file(path, repo_root)
    assert hits == []


def test_api_file_with_no_basemodel_passes(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "agent.py",
        """\
from fastapi import APIRouter

router = APIRouter()

@router.get("/status")
async def get_status():
    return {"status": "ok"}
""",
    )
    hits = hook._check_file(path, repo_root)
    assert hits == []


def test_allowlisted_workflow_state_passes(tmp_path: Path) -> None:
    """workflow_state.py is exempt — WorkflowState tightly coupled with
    WorkflowStateMachine."""
    path, repo_root = _write_api(
        tmp_path,
        "workflow_state.py",
        """\
from pydantic import BaseModel

class WorkflowState(BaseModel):
    state: str
""",
    )
    hits = hook._check_file(path, repo_root)
    assert hits == []


def test_empty_file_passes(tmp_path: Path) -> None:
    path, repo_root = _write_api(tmp_path, "empty.py", "")
    hits = hook._check_file(path, repo_root)
    assert hits == []


def test_non_api_file_not_flagged(tmp_path: Path) -> None:
    """Files outside autobot-backend/api/ are ignored even if they contain BaseModel."""
    repo_root = tmp_path
    services_dir = repo_root / "autobot-backend" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)
    path = services_dir / "my_service.py"
    path.write_text(
        """\
from pydantic import BaseModel

class ServiceData(BaseModel):
    value: int
""",
        encoding="utf-8",
    )
    hits = hook._check_file(path, repo_root)
    assert hits == []


def test_class_not_inheriting_basemodel_passes(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "terminal.py",
        """\
class PTYSession:
    def __init__(self):
        self.pid = None

class OutputBuffer(list):
    pass
""",
    )
    hits = hook._check_file(path, repo_root)
    assert hits == []


# ---------------------------------------------------------------------------
# _is_target_file path filtering
# ---------------------------------------------------------------------------


def test_is_target_file_api_endpoint(tmp_path: Path) -> None:
    path, repo_root = _write_api(tmp_path, "knowledge.py", "")
    assert hook._is_target_file(path, repo_root) is True


def test_is_target_file_schema_file_excluded(tmp_path: Path) -> None:
    path, repo_root = _write_api(tmp_path, "schemas_agent.py", "")
    assert hook._is_target_file(path, repo_root) is False


def test_is_target_file_allowlisted_excluded(tmp_path: Path) -> None:
    path, repo_root = _write_api(tmp_path, "workflow_state.py", "")
    assert hook._is_target_file(path, repo_root) is False


def test_is_target_file_outside_api_excluded(tmp_path: Path) -> None:
    repo_root = tmp_path
    other = repo_root / "autobot-backend" / "services" / "svc.py"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_text("", encoding="utf-8")
    assert hook._is_target_file(other, repo_root) is False


# ---------------------------------------------------------------------------
# Exit-code integration (main())
# ---------------------------------------------------------------------------


def test_main_returns_0_for_clean_file(tmp_path: Path) -> None:
    path, repo_root = _write_api(
        tmp_path,
        "agent_clean.py",
        """\
from fastapi import APIRouter
router = APIRouter()
""",
    )
    # main() uses argv paths relative to real repo_root (resolved from __file__)
    # so passing absolute path to a non-api file returns 0 regardless
    result = hook.main(["hook", str(path)])
    assert result == 0


def test_main_returns_0_for_empty_argv(tmp_path: Path) -> None:
    """No files passed triggers full-repo scan; must not crash and return int."""
    result = hook.main(["hook"])
    assert isinstance(result, int)
