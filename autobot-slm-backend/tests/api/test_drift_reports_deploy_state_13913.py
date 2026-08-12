# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The drift endpoint says when its own reading is untrustworthy (#13913).

Measured across one self-update: 28 of 30 reported drifts evaporated once the
play settled. Both checksums were populated during the window, so the
``source_checksum: null`` heuristic from #13851 does not filter them out — they
look exactly like genuine content drift.

Two behaviours are covered here:

* the report carries the deploy state it was taken under, so a caller can tell
  "28 files have drifted" from "28 files are being written right now";
* the **destructive** path refuses while a play is running. Resolve is a
  delete-style rsync (#13851), so running one against a tree ansible is
  mid-write destroys files that are merely mid-copy.

The third case is the one worth stating explicitly: when the deploy state
cannot be determined, resolve **proceeds**. Refusing on an unknown signal would
permanently disable remediation on any host where the unit cannot be queried —
a worse outcome than the behaviour that existed before this guard.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

code_sync = import_code_sync()


def _activity(in_progress, reason="r", last=None):
    """A stand-in DeployActivity with the real readings_are_unstable rule.

    Written out rather than imported so the assertions below cannot pass by
    inheriting a mocked truthiness from the conftest stubs.
    """

    class _A:
        def __init__(self):
            self.in_progress = in_progress
            self.reason = reason
            self.last_completed_play_at = last

        @property
        def readings_are_unstable(self):
            return self.in_progress is True

    return _A()


# ------------------------------------------------------- the destructive path


@pytest.mark.asyncio
async def test_resolve_refuses_while_a_play_is_running():
    """409, not a delete-style rsync over files ansible is writing."""
    with patch.object(code_sync, "read_deploy_activity", AsyncMock(return_value=_activity(True))):
        with pytest.raises(HTTPException) as exc:
            await code_sync._reject_if_deploy_in_progress()

    assert exc.value.status_code == 409
    assert "self-update" in exc.value.detail


@pytest.mark.asyncio
async def test_resolve_proceeds_when_no_play_is_running():
    """The guard must not block the ordinary case it exists to protect."""
    with patch.object(code_sync, "read_deploy_activity", AsyncMock(return_value=_activity(False))):
        await code_sync._reject_if_deploy_in_progress()  # must not raise


@pytest.mark.asyncio
async def test_resolve_proceeds_when_the_deploy_state_is_unknown():
    """Unknown does not block — deliberately.

    On a host where the self-update unit cannot be queried, refusing would
    leave the operator with no way to clear drift at all. That is a regression
    against a feature that works today, whereas proceeding is exactly the
    pre-existing behaviour. The unknown state is logged and surfaced in the
    drift response instead.
    """
    with patch.object(code_sync, "read_deploy_activity", AsyncMock(return_value=_activity(None))):
        await code_sync._reject_if_deploy_in_progress()  # must not raise


@pytest.mark.asyncio
async def test_a_probe_that_raises_does_not_take_down_the_endpoint():
    """A safety probe must never be the thing that breaks the operation.

    ``read_deploy_activity`` is written never to raise, so this is defence in
    depth — but the failure mode it guards is bad enough to be worth the four
    lines: a 500 from the probe would make resolve unusable everywhere, which
    is strictly worse than the unguarded behaviour that preceded it.
    """
    with patch.object(code_sync, "read_deploy_activity", AsyncMock(side_effect=RuntimeError("probe exploded"))):
        await code_sync._reject_if_deploy_in_progress()  # must not raise


def test_both_resolve_paths_share_one_guard():
    """Sync and async resolve must not drift apart.

    Two copies of a safety check is how one of them ends up outdated, so the
    rule lives in one helper and both endpoints call it. A future endpoint that
    inlines its own copy fails here.
    """
    source = (Path(__file__).resolve().parents[2] / "api" / "code_sync.py").read_text(encoding="utf-8")

    assert source.count("await _reject_if_deploy_in_progress()") == 2, (
        "expected exactly the sync and async resolve endpoints to call the guard — "
        "a third call site, or a missing one, means the paths have diverged"
    )


# ------------------------------------------------------------ the report itself
#
# ``_code_sync_import`` binds *fieldless* Pydantic stand-ins for every
# models.schemas class (the root conftest stubs the real ones), so a returned
# FileDriftReport carries no attributes to assert on. These tests therefore
# capture what the endpoint *passes* to the response model, and check the real
# schema declaration separately — between them that is the same claim, without
# either one passing vacuously against a stand-in.


def _capture_report(monkeypatch):
    """Replace the response model with a recorder and return the recording."""
    captured = {}

    def _recorder(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(code_sync, "FileDriftReport", _recorder)
    monkeypatch.setattr(code_sync, "VISIBILITY_COMPONENTS", {"autobot-slm-backend"})
    monkeypatch.setattr(code_sync, "get_default_source_dir", lambda c: "/s")
    monkeypatch.setattr(code_sync, "get_default_deployed_dir", lambda c: "/d")
    return captured


def _base_report(drifted):
    return {
        "source_dir": "/s",
        "deployed_dir": "/d",
        "drifted_files": drifted,
        "untracked_files": [],
        "total_compared": len(drifted),
        "drift_detected": bool(drifted),
        "checked_at": "2026-08-10T00:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_the_report_carries_the_deploy_state_it_was_taken_under(monkeypatch):
    """The reading is annotated with the deploy state, from the activity call."""
    drifted = [{"path": "a.py", "source_checksum": "x", "deployed_checksum": "y", "status": "modified"}]
    monkeypatch.setattr(code_sync, "build_drift_report", lambda *a, **k: _base_report(drifted))
    captured = _capture_report(monkeypatch)

    activity = _activity(True, reason="a self-update play is running", last="2026-08-09T00:00:00+00:00")
    with patch.object(code_sync, "read_deploy_activity", AsyncMock(return_value=activity)):
        await code_sync.get_file_drift(_={}, component="autobot-slm-backend")

    assert captured["deploy_in_progress"] is True, "a reading taken mid-deploy did not say so"
    assert captured["deploy_state_reason"] == "a self-update play is running"
    assert captured["last_completed_play_at"] == "2026-08-09T00:00:00+00:00"
    # The measurement itself is unchanged — the annotation is purely additive.
    assert captured["drift_detected"] is True
    assert captured["drifted_files"] == drifted


@pytest.mark.asyncio
async def test_an_unknown_deploy_state_reaches_the_caller_as_none(monkeypatch):
    """None must survive to the response rather than becoming False.

    ``deploy_in_progress: false`` is a claim that the reading is trustworthy.
    Passing an unanswered query along as ``false`` would restore the silence
    this issue is about, in the one place a caller actually looks.
    """
    monkeypatch.setattr(code_sync, "build_drift_report", lambda *a, **k: _base_report([]))
    captured = _capture_report(monkeypatch)

    with patch.object(code_sync, "read_deploy_activity", AsyncMock(return_value=_activity(None))):
        await code_sync.get_file_drift(_={}, component="autobot-slm-backend")

    assert captured["deploy_in_progress"] is None
    assert captured["deploy_in_progress"] is not False


def test_the_schema_declares_the_three_fields_as_optional():
    """The real FileDriftReport gained the fields, with None defaults.

    Defaults matter as much as presence: every existing construction site and
    every stored fixture omits them, so a required field would turn this
    annotation into a breaking change for callers it is meant to inform.
    """
    schemas_src = (Path(__file__).resolve().parents[2] / "models" / "schemas.py").read_text(encoding="utf-8")
    tree = ast.parse(schemas_src)

    cls = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "FileDriftReport")
    fields = {n.target.id: n.value for n in cls.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)}

    for name in ("deploy_in_progress", "deploy_state_reason", "last_completed_play_at"):
        assert name in fields, f"FileDriftReport does not declare {name}"
        default = fields[name]
        assert (
            isinstance(default, ast.Constant) and default.value is None
        ), f"{name} must default to None — a required field would break every existing caller"
