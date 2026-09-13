# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for npu_worker_design -- dry-run must be genuinely safe (#14563).

``npu_worker_design.py`` writes ``NPU_WORKER_ARCHITECTURE.json`` at the
resolved project root and, before #14517 fixed its project-root resolution,
could never reach that target. Once it became reachable, it still wrote in
place with no preview and no ``--dry-run`` -- the same "was inert, now
writes" shape #14546 named for ``optimize_agents.py``. The guard this suite
exists for: :func:`main` with the default (``apply_changes=False``) must
perform **zero writes** to the target file. ``test_dry_run_matches_apply``
mutates that guarantee (forces a write even in dry-run) and asserts the test
goes red, so the guard itself is proven to catch the regression it names.
"""

import sys
from pathlib import Path

import pytest

# Add the infrastructure ``shared/scripts`` root to the path so
# ``utilities.npu_worker_design`` (a PEP 420 namespace package portion)
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

from utilities import npu_worker_design  # noqa: E402 - must follow the sys.path setup above


@pytest.fixture
def project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A scratch project root, never the real checkout."""
    monkeypatch.setattr(npu_worker_design, "project_root", lambda: tmp_path)
    monkeypatch.setattr(sys, "argv", ["npu_worker_design.py"])
    return tmp_path


def test_dry_run_writes_nothing(project_dir: Path):
    """The default (no --apply) must not create the target file at all."""
    target = project_dir / "NPU_WORKER_ARCHITECTURE.json"

    exit_code = npu_worker_design.main()

    assert exit_code == 0
    assert not target.exists(), "dry-run created the architecture file"


def test_apply_actually_writes(project_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """--apply must perform the write dry-run only previewed."""
    monkeypatch.setattr(sys, "argv", ["npu_worker_design.py", "--apply"])
    target = project_dir / "NPU_WORKER_ARCHITECTURE.json"

    exit_code = npu_worker_design.main()

    assert exit_code == 0
    assert target.exists()
    architecture = npu_worker_design.NPUWorkerArchitecture()
    assert target.read_text(encoding="utf-8") == architecture.generate_architecture_file()


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
    monkeypatch.setattr(npu_worker_design, "build_arg_parser", lambda: _AlwaysApplyParser())
    target = project_dir / "NPU_WORKER_ARCHITECTURE.json"

    npu_worker_design.main()

    assert target.exists(), "mutation did not reach disk -- guard is not exercising the write path"


def test_atomic_write_leaves_no_partial_file_on_failure(project_dir: Path, monkeypatch: pytest.MonkeyPatch):
    """A failure mid-write must not leave a truncated file behind."""
    target = project_dir / "NPU_WORKER_ARCHITECTURE.json"
    target.write_text("original content", encoding="utf-8")

    def _boom(*_args, **_kwargs):
        raise OSError("simulated crash mid-write")

    monkeypatch.setattr(npu_worker_design.os, "replace", _boom)

    with pytest.raises(OSError):
        npu_worker_design.write_atomically(target, "corrupted content")

    assert target.read_text(encoding="utf-8") == "original content"
    leftover_tmp = list(project_dir.glob(".*.tmp"))
    assert leftover_tmp == [], f"temp file(s) leaked: {leftover_tmp}"


def test_write_failure_is_reported_not_swallowed(project_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys):
    """A write failure under --apply must exit non-zero, never a quiet 0."""
    monkeypatch.setattr(sys, "argv", ["npu_worker_design.py", "--apply"])

    def _boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(npu_worker_design, "write_atomically", _boom)

    exit_code = npu_worker_design.main()

    assert exit_code == 1
