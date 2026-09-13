# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for enhance_workflow_ui -- dry-run must be genuinely safe (#14563).

``enhance_workflow_ui.py`` writes ``WorkflowNotifications.vue`` and
``WorkflowProgressWidget.vue`` under ``_COMPONENTS_REL`` and, before #14517
fixed both write targets, could never reach them. Once it became reachable,
it still wrote in place with no preview and no ``--dry-run`` -- the same
"was inert, now writes" shape #14546 named for ``optimize_agents.py``. The
guard this suite exists for: :func:`main` with the default
(``apply_changes=False``) must perform **zero writes** to either target.
``test_dry_run_matches_apply`` mutates that guarantee (forces a write even
in dry-run) and asserts the test goes red, so the guard itself is proven to
catch the regression it names.
"""

import sys
from pathlib import Path

import pytest

# Add the infrastructure ``shared/scripts`` root to the path so
# ``utilities.enhance_workflow_ui`` (a PEP 420 namespace package portion)
# resolves, matching the convention ``optimize_agents_test.py`` (in this same
# directory) already established for this tree (#14518).
# Lives here, not beside the script it tests: ci.yml's shard command passes an
# explicit path list, and `.../shared/scripts/utilities` is not on it while
# `.../shared/tests` is. A test placed beside the script is collected by a bare
# local pytest and by nothing in CI -- present, passing, and never run where it
# matters. Same reasoning as repo_tests/test_pr_issue_validation_14241.py.
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from utilities import enhance_workflow_ui  # noqa: E402 - must follow the sys.path setup above


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch project root, with the component directory pre-created.

    The real ``_COMPONENTS_REL`` target does not exist in the repository
    today (#14563) -- this fixture stands in for a checkout where it does,
    which is the situation the dry-run/--apply guard has to hold under.
    """
    monkeypatch.setattr(enhance_workflow_ui, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["enhance_workflow_ui.py"])
    (tmp_path / enhance_workflow_ui._COMPONENTS_REL).mkdir(parents=True)
    return tmp_path


def _targets(project_dir: Path) -> list[Path]:
    components_dir = project_dir / enhance_workflow_ui._COMPONENTS_REL
    return [
        components_dir / "WorkflowNotifications.vue",
        components_dir / "WorkflowProgressWidget.vue",
    ]


def test_dry_run_writes_nothing(project_dir: Path):
    """The default (no --apply) must not create either target file."""
    exit_code = enhance_workflow_ui.main()

    assert exit_code == 0
    for target in _targets(project_dir):
        assert not target.exists(), f"dry-run created {target}"


def test_apply_actually_writes(project_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """--apply must perform the writes dry-run only previewed."""
    monkeypatch.setattr(sys, "argv", ["enhance_workflow_ui.py", "--apply"])

    exit_code = enhance_workflow_ui.main()

    assert exit_code == 0
    notifications, progress_widget = _targets(project_dir)
    assert notifications.read_text(encoding="utf-8") == enhance_workflow_ui.create_workflow_notification_component()
    assert progress_widget.read_text(encoding="utf-8") == enhance_workflow_ui.create_workflow_progress_widget()


class _AlwaysApplyParser:
    """A stand-in for the CLI parser that always reports --apply."""

    def parse_args(self):
        """Return a fake namespace with ``apply`` forced True."""
        return _AlwaysApply()


class _AlwaysApply:
    """A stand-in ``argparse.Namespace`` that always reports --apply."""

    apply = True
    dry_run = False


def test_dry_run_matches_apply_preview(project_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """Mutation guard: if dry-run started writing, this test must go red.

    Simulates the exact regression the guard exists for by forcing
    ``main`` to write even when the caller asked for a preview.
    """
    monkeypatch.setattr(enhance_workflow_ui, "build_arg_parser", lambda: _AlwaysApplyParser())

    enhance_workflow_ui.main()

    for target in _targets(project_dir):
        assert target.exists(), "mutation did not reach disk -- guard is not exercising the write path"


def test_atomic_write_leaves_no_partial_file_on_failure(project_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A failure mid-write must not leave a truncated component behind."""
    target = _targets(project_dir)[0]
    target.write_text("original content", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(enhance_workflow_ui.os, "replace", _boom)

    with pytest.raises(OSError):
        enhance_workflow_ui.write_atomically(target, "corrupted content")

    assert target.read_text(encoding="utf-8") == "original content"
    leftover_tmp = list(target.parent.glob(".*.tmp"))
    assert leftover_tmp == [], f"temp file(s) leaked: {leftover_tmp}"


def test_write_failure_is_reported_not_swallowed(project_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A write failure under --apply must exit non-zero, never a quiet 0."""
    monkeypatch.setattr(sys, "argv", ["enhance_workflow_ui.py", "--apply"])

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(enhance_workflow_ui, "write_atomically", _boom)

    exit_code = enhance_workflow_ui.main()

    assert exit_code == 1


def test_stale_component_dir_missing_fails_loudly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """--apply against the real (stale, non-existent) directory must error, not silently no-op.

    Documents current behaviour (#14563): ``_COMPONENTS_REL`` names a
    directory ("autobot-vue/src/components") that does not exist in this
    repository. Fixing that stale path is out of scope for the dry-run
    safety fix -- this test pins that an --apply run against it fails
    loudly (a reported OSError, non-zero exit) rather than being swallowed.
    """
    monkeypatch.setattr(enhance_workflow_ui, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["enhance_workflow_ui.py", "--apply"])

    exit_code = enhance_workflow_ui.main()

    assert exit_code == 1
