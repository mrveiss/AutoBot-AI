# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for MetaEvalHarness (issue #3224).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from unittest.mock import patch as mock_patch

import pytest

from .archive import Archive
from .config import AutoResearchConfig
from .meta_agent import MetaPatch
from .meta_eval_harness import MetaEvalHarness, MetaEvalResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_harness(approval_gate=None) -> MetaEvalHarness:
    config = AutoResearchConfig()
    config.meta_agent_test_timeout = 10
    config.meta_agent_approval_threshold = 0.1
    return MetaEvalHarness(config=config, approval_gate=approval_gate)


def _make_patch(
    original: str = "def foo(): return 1\n",
    modified: str = "def foo(): return 2\n",
    patch_id: str = "test-patch-1",
) -> MetaPatch:
    return MetaPatch(
        patch_id=patch_id,
        target_path="/tmp/module.py",  # nosec B108 - test/controlled code uses tmpdir intentionally
        original_content=original,
        modified_content=modified,
        rationale="test change",
        generation=1,
    )


# ---------------------------------------------------------------------------
# MetaEvalResult
# ---------------------------------------------------------------------------


def test_result_succeeded_true() -> None:
    r = MetaEvalResult(tests_passed=3, tests_total=4)
    assert r.succeeded is True


def test_result_succeeded_false_zero_total() -> None:
    r = MetaEvalResult(tests_passed=0, tests_total=0)
    assert r.succeeded is False


def test_result_succeeded_false_zero_passed() -> None:
    r = MetaEvalResult(tests_passed=0, tests_total=5)
    assert r.succeeded is False


def test_result_to_dict() -> None:
    r = MetaEvalResult(patch_id="abc", score=0.8, decision="approved", applied=True)
    d = r.to_dict()
    assert d["patch_id"] == "abc"
    assert d["score"] == 0.8
    assert d["decision"] == "approved"
    assert d["applied"] is True


# ---------------------------------------------------------------------------
# _parse_pytest_summary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "output,expected_passed,expected_total",
    [
        ("5 passed, 2 failed in 0.5s", 5, 7),
        ("3 passed in 0.1s", 3, 3),
        ("2 failed in 0.05s", 0, 2),
        ("1 passed, 1 failed, 1 error in 1.0s", 1, 3),
        ("no output", 0, 0),
        ("", 0, 0),
    ],
)
def test_parse_pytest_summary(output, expected_passed, expected_total) -> None:
    passed, total = MetaEvalHarness._parse_pytest_summary(output)
    assert passed == expected_passed
    assert total == expected_total


# ---------------------------------------------------------------------------
# _compute_score
# ---------------------------------------------------------------------------


def test_compute_score_all_pass() -> None:
    assert MetaEvalHarness._compute_score(5, 5) == 1.0


def test_compute_score_partial() -> None:
    assert MetaEvalHarness._compute_score(3, 4) == pytest.approx(0.75)


def test_compute_score_zero_total() -> None:
    assert MetaEvalHarness._compute_score(0, 0) == 0.0


# ---------------------------------------------------------------------------
# evaluate_patch — no changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_patch_no_changes_skips() -> None:
    harness = _make_harness()
    archive = Archive()
    patch = MetaPatch(
        patch_id="same",
        target_path="/tmp/module.py",  # nosec B108 - test/controlled code uses tmpdir intentionally
        original_content="x = 1\n",
        modified_content="x = 1",  # stripped equal
    )
    result = await harness.evaluate_patch(patch, archive)
    assert result.decision == "skipped"
    assert result.applied is False
    assert archive.size == 1  # still recorded


# ---------------------------------------------------------------------------
# evaluate_patch — tests fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_patch_tests_fail_rejected(tmp_path) -> None:
    harness = _make_harness()
    archive = Archive()
    patch = _make_patch()

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(0, 3, "3 failed in 0.1s")),
        ),
    ):
        # write a placeholder so unlink won't fail
        (tmp_path / "tmp.py").touch()
        result = await harness.evaluate_patch(patch, archive)

    assert result.decision == "rejected"
    assert result.applied is False
    assert result.score == 0.0


# ---------------------------------------------------------------------------
# evaluate_patch — tests pass, approval not needed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_patch_approved_no_gate(tmp_path) -> None:
    harness = _make_harness()
    # Override threshold so no gate needed for score < threshold
    harness.config.meta_agent_approval_threshold = 2.0  # impossible to trigger

    archive = Archive()
    patch = _make_patch()

    applied_path = tmp_path / "module.py"
    applied_path.write_text(patch.original_content, encoding="utf-8")
    patch = MetaPatch(
        patch_id="p1",
        target_path=str(applied_path),
        original_content=patch.original_content,
        modified_content=patch.modified_content,
    )

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(5, 5, "5 passed in 0.2s")),
        ),
    ):
        (tmp_path / "tmp.py").touch()
        result = await harness.evaluate_patch(patch, archive)

    assert result.decision == "approved"
    assert result.applied is True
    assert applied_path.read_text(encoding="utf-8") == patch.modified_content


# ---------------------------------------------------------------------------
# evaluate_patch — approval gate consulted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_patch_gate_approved(tmp_path) -> None:
    gate = MagicMock()
    gate.check_approval_needed = MagicMock(return_value=True)
    gate.request_approval = AsyncMock()
    gate.wait_for_approval = AsyncMock(return_value="approved")

    harness = _make_harness(approval_gate=gate)

    applied_path = tmp_path / "module.py"
    applied_path.write_text("def foo(): return 1\n", encoding="utf-8")

    patch = MetaPatch(
        patch_id="gate-patch",
        target_path=str(applied_path),
        original_content="def foo(): return 1\n",
        modified_content="def foo(): return 2\n",
    )
    archive = Archive()

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(4, 4, "4 passed in 0.1s")),
        ),
    ):
        (tmp_path / "tmp.py").touch()
        result = await harness.evaluate_patch(patch, archive, session_id="sess-1")

    assert result.decision == "approved"
    assert result.applied is True
    gate.request_approval.assert_awaited_once()
    gate.wait_for_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_evaluate_patch_gate_rejected(tmp_path) -> None:
    gate = MagicMock()
    gate.check_approval_needed = MagicMock(return_value=True)
    gate.request_approval = AsyncMock()
    gate.wait_for_approval = AsyncMock(return_value="rejected")

    harness = _make_harness(approval_gate=gate)

    applied_path = tmp_path / "module.py"
    applied_path.write_text("def foo(): return 1\n", encoding="utf-8")

    patch = MetaPatch(
        patch_id="rejected-patch",
        target_path=str(applied_path),
        original_content="def foo(): return 1\n",
        modified_content="def foo(): return 2\n",
    )
    archive = Archive()

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(4, 4, "4 passed in 0.1s")),
        ),
    ):
        (tmp_path / "tmp.py").touch()
        result = await harness.evaluate_patch(patch, archive, session_id="sess-1")

    assert result.decision == "rejected"
    assert result.applied is False
    # Live file unchanged
    assert applied_path.read_text(encoding="utf-8") == "def foo(): return 1\n"


# ---------------------------------------------------------------------------
# Archive integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_patch_adds_to_archive(tmp_path) -> None:
    harness = _make_harness()
    harness.config.meta_agent_approval_threshold = 2.0  # no gate

    applied_path = tmp_path / "module.py"
    applied_path.write_text("def foo(): return 1\n", encoding="utf-8")

    patch = MetaPatch(
        patch_id="arch-patch",
        target_path=str(applied_path),
        original_content="def foo(): return 1\n",
        modified_content="def foo(): return 99\n",
        generation=2,
    )
    archive = Archive()

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(3, 4, "3 passed, 1 failed in 0.1s")),
        ),
    ):
        (tmp_path / "tmp.py").touch()
        await harness.evaluate_patch(patch, archive)

    assert archive.size == 1
    entry = archive.best
    assert entry.variant_id == "arch-patch"
    assert entry.score == pytest.approx(0.75)
    assert entry.generation == 2


# ---------------------------------------------------------------------------
# Gate bypass safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_evaluate_patch_rejects_when_gate_required_no_session(tmp_path) -> None:
    """When approval is required but session_id is empty, reject (not approve)."""
    gate = MagicMock()
    gate.check_approval_needed = MagicMock(return_value=True)  # gate always required
    gate.request_approval = AsyncMock()

    harness = _make_harness(approval_gate=gate)
    archive = Archive()

    applied_path = tmp_path / "module.py"
    applied_path.write_text("def foo(): return 1\n", encoding="utf-8")

    patch = MetaPatch(
        patch_id="bypass-patch",
        target_path=str(applied_path),
        original_content="def foo(): return 1\n",
        modified_content="def foo(): return 2\n",
    )

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(5, 5, "5 passed in 0.1s")),
        ),
    ):
        (tmp_path / "tmp.py").touch()
        result = await harness.evaluate_patch(patch, archive, session_id="")

    assert result.decision == "rejected"
    assert result.applied is False
    gate.request_approval.assert_not_awaited()
    # Live file must be unchanged
    assert applied_path.read_text(encoding="utf-8") == "def foo(): return 1\n"


# ---------------------------------------------------------------------------
# Backup filename uniqueness
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_patch_backup_includes_patch_id(tmp_path) -> None:
    """Each applied patch must create a unique backup file."""
    harness = _make_harness()
    harness.config.meta_agent_approval_threshold = 2.0  # no gate

    applied_path = tmp_path / "module.py"
    applied_path.write_text("def foo(): return 1\n", encoding="utf-8")

    patch = MetaPatch(
        patch_id="abcdef12-0000-0000-0000-000000000000",
        target_path=str(applied_path),
        original_content="def foo(): return 1\n",
        modified_content="def foo(): return 2\n",
    )
    archive = Archive()

    with (
        mock_patch.object(harness, "_write_temp_module", return_value=tmp_path / "tmp.py"),
        mock_patch.object(
            harness,
            "_run_tests",
            new=AsyncMock(return_value=(3, 3, "3 passed in 0.1s")),
        ),
    ):
        (tmp_path / "tmp.py").touch()
        result = await harness.evaluate_patch(patch, archive)

    assert result.applied is True
    backup = tmp_path / "module.abcdef12.meta_bak"
    assert backup.exists(), f"expected backup at {backup}"
