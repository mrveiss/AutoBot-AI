# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for tools/lint/check_no_local_schemas.py — see #6056.

Covers detection, allowlist, path filtering, and exit codes for the hook
that prevents re-introduction of local BaseModel subclasses in non-schema
API endpoint files (autobot-backend/api/*.py, excluding schemas_*.py).
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import scrubbed_git_env

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


def test_test_files_in_api_are_not_scanned(tmp_path: Path) -> None:
    """A model that a test defines is a fixture, not an endpoint schema (owner ruling 2026-09-11, #16298)."""
    for name in ("chat_api_test.py", "test_chat_api.py"):
        path, repo_root = _write_api(
            tmp_path, name, "from pydantic import BaseModel\n\nclass Fixture(BaseModel):\n    x: int\n"
        )
        assert hook._is_target_file(path, repo_root) is False, name
        assert hook._check_file(path, repo_root) == [], name


def test_the_same_model_in_an_endpoint_file_is_still_flagged(tmp_path: Path) -> None:
    """The contrast case: skipping test files must not open a gap for endpoint files."""
    path, repo_root = _write_api(
        tmp_path, "chat_api.py", "from pydantic import BaseModel\n\nclass Fixture(BaseModel):\n    x: int\n"
    )
    assert [name for _, name in hook._check_file(path, repo_root)] == ["Fixture"]


def test_a_name_merely_containing_test_is_still_scanned(tmp_path: Path) -> None:
    """Only pytest's two naming conventions are skipped, not any name with "test" in it."""
    path, repo_root = _write_api(tmp_path, "latest_results.py", "")
    assert hook._is_target_file(path, repo_root) is True


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


# ---------------------------------------------------------------------------
# Changed-lines scoping (#16178)
#
# Driven through run() against a real throwaway git repository, because the
# thing under test is the diff: a fixture that faked the added-line set would
# pass whatever the hunk parser did.
# ---------------------------------------------------------------------------

E = scrubbed_git_env()  # #15246: an ambient GIT_DIR would point these git calls at the live repo

LEGACY = """\
from pydantic import BaseModel


class LegacyRequest(BaseModel):
    name: str


def handler():
    return 1
"""


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True, env=E)
    return done.stdout.strip()


def _repo_with_legacy_model(tmp_path: Path) -> tuple[Path, Path]:
    """A repo whose base commit already carries a local model: (repo, file)."""
    path, repo = _write_api(tmp_path, "legacy.py", LEGACY)
    _git(repo, "init", "--quiet")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", ".")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "base")
    return repo, path


def test_an_unrelated_staged_edit_is_not_blamed_for_a_preexisting_model(tmp_path: Path, capsys) -> None:
    """AC4, pre-commit stage -- the #15757 case.

    One unrelated line changes in a file that already carries a local model. The
    model is not this change's, and failing the commit for it is the defect.
    """
    repo, path = _repo_with_legacy_model(tmp_path)
    path.write_text(LEGACY.replace("return 1", "return 2"), encoding="utf-8")
    _git(repo, "add", str(path))

    assert hook.run([path], repo, changed_only=True, base=None) == 0
    assert "not counted" in capsys.readouterr().err, "a pre-existing model is listed, not hidden"


def test_a_newly_added_model_still_fails_when_scoped(tmp_path: Path) -> None:
    """AC4, the contrast: scoping must not become a way to add a model."""
    repo, path = _repo_with_legacy_model(tmp_path)
    path.write_text(LEGACY + "\n\nclass NewResponse(BaseModel):\n    ok: bool\n", encoding="utf-8")
    _git(repo, "add", str(path))

    assert hook.run([path], repo, changed_only=True, base=None) == 1


def test_base_mode_judges_the_range_not_the_file(tmp_path: Path) -> None:
    """AC4, PR stage: the same pair, read from BASE..HEAD as the CI wrapper passes it."""
    repo, path = _repo_with_legacy_model(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    path.write_text(LEGACY.replace("return 1", "return 2"), encoding="utf-8")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-am", "unrelated")
    assert hook.run([path], repo, changed_only=True, base=base) == 0

    path.write_text(path.read_text(encoding="utf-8") + "\n\nclass Added(BaseModel):\n    x: int\n", encoding="utf-8")
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-am", "adds a model")
    assert hook.run([path], repo, changed_only=True, base=base) == 1


def test_a_renamed_file_is_not_blamed_for_the_models_it_carried(tmp_path: Path) -> None:
    """A ``git mv`` does not introduce the models inside the file it moves.

    A diff limited to one path cannot pair a rename with its source, so the moved
    file read as wholly added and every model in it as new. Found in review.
    """
    repo, path = _repo_with_legacy_model(tmp_path)
    moved = path.with_name("moved.py")
    _git(repo, "mv", str(path), str(moved))

    assert hook.run([moved], repo, changed_only=True, base=None) == 0


def test_a_renamed_file_that_gains_a_model_still_fails(tmp_path: Path) -> None:
    """The contrast: following the rename must not hide a model added in the same change."""
    repo, path = _repo_with_legacy_model(tmp_path)
    moved = path.with_name("moved.py")
    _git(repo, "mv", str(path), str(moved))
    moved.write_text(LEGACY + "\n\nclass Smuggled(BaseModel):\n    x: int\n", encoding="utf-8")
    _git(repo, "add", str(moved))

    assert hook.run([moved], repo, changed_only=True, base=None) == 1


def test_a_rename_in_a_committed_range_is_followed_too(tmp_path: Path) -> None:
    """The PR stage: the same rename, read from BASE..HEAD."""
    repo, path = _repo_with_legacy_model(tmp_path)
    base = _git(repo, "rev-parse", "HEAD")
    moved = path.with_name("moved.py")
    _git(repo, "mv", str(path), str(moved))
    _git(repo, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "move")

    assert hook.run([moved], repo, changed_only=True, base=base) == 0


def test_an_unstaged_file_has_no_change_to_scope_to_and_is_judged_whole(tmp_path: Path, capsys) -> None:
    """``pre-commit run --all-files`` hands over files that nothing staged.

    An empty staged diff there does not mean "this change added no model": there is
    no change. Reading it as nothing-added reported every model as pre-existing.
    """
    repo, path = _repo_with_legacy_model(tmp_path)

    assert hook.run([path], repo, changed_only=True, base=None) == 1
    assert "no change to scope to" in capsys.readouterr().err


def test_pre_commit_from_ref_becomes_the_base(monkeypatch) -> None:
    """``--from-ref``/``--to-ref`` stages nothing, so pre-commit's exported range is used instead."""
    monkeypatch.setenv("PRE_COMMIT", "1")
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", "abc123")
    assert hook.resolve_base(None) == "abc123"
    assert hook.resolve_base("explicit") == "explicit", "an explicit --base wins"
    monkeypatch.delenv("PRE_COMMIT_FROM_REF")
    assert hook.resolve_base(None) is None, "with no range, the staged diff is what is scoped"


def test_a_from_ref_left_in_a_shell_is_ignored_outside_pre_commit(monkeypatch) -> None:
    """Only pre-commit's own export counts; it always sets PRE_COMMIT=1 alongside the range."""
    monkeypatch.delenv("PRE_COMMIT", raising=False)
    monkeypatch.setenv("PRE_COMMIT_FROM_REF", "stale-ref")

    assert hook.resolve_base(None) is None


def test_an_unscoped_run_still_reads_the_whole_file(tmp_path: Path) -> None:
    """A direct run is for the backlog, and must still show it."""
    repo, path = _repo_with_legacy_model(tmp_path)
    assert hook.run([path], repo, changed_only=False, base=None) == 1


def test_a_git_failure_fails_closed_instead_of_reading_as_nothing_added(tmp_path: Path, capsys) -> None:
    """No repository at all: "this change added nothing" would be an unearned clean verdict."""
    path, repo = _write_api(tmp_path, "legacy.py", LEGACY)
    assert hook.run([path], repo, changed_only=True, base=None) == 1
    assert "refusing to report clean" in capsys.readouterr().err


def test_base_without_scoping_is_rejected() -> None:
    with pytest.raises(SystemExit) as exited:
        hook.main(["hook", "--base", "HEAD~1", "x.py"])
    assert exited.value.code == 2


# ---------------------------------------------------------------------------
# Destination guidance (#16178 AC2): headroom from the size guard's own data
# ---------------------------------------------------------------------------


def _fake_size_guard(repo: Path, known_large: dict[str, int]) -> None:
    """Stand-ins for the size guard and its ceiling data, loaded by path like the real ones."""
    scripts = repo / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "check_python_file_size.py").write_text(
        "MAX_LINES = 10\n" "def count_lines(path):\n" "    return sum(1 for _ in path.open(encoding='utf-8'))\n",
        encoding="utf-8",
    )
    (scripts / "python_file_size_known_large.py").write_text(f"KNOWN_LARGE = {known_large!r}\n", encoding="utf-8")


def test_the_guide_offers_headroom_and_marks_frozen_modules(tmp_path: Path) -> None:
    """The message must not send anyone into a file that refuses them."""
    repo = _api_root(tmp_path)
    api = repo / "autobot-backend" / "api"
    (api / "schemas_big.py").write_text("x = 1\n" * 50, encoding="utf-8")
    (api / "schemas_big_rows.py").write_text("x = 1\n" * 3, encoding="utf-8")
    _fake_size_guard(repo, {"autobot-backend/api/schemas_big.py": 50})

    fits, frozen = hook._destination_guide(repo).split("Frozen at their ceiling", 1)

    assert "schemas_big_rows.py" in fits and "(+7)" in fits, "a companion with headroom must be offered"
    assert "schemas_big.py " in frozen, "a module at its ceiling must be listed as frozen"
    assert "schemas_big.py " not in fits


def test_the_guide_says_so_when_it_cannot_read_the_ceilings(tmp_path: Path) -> None:
    """Advice without numbers beats invented numbers, and the verdict is unaffected."""
    assert "headroom unavailable" in hook._destination_guide(_api_root(tmp_path))
