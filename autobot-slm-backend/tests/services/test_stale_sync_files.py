# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Propose and approved removal of stale code-sync files, in the order that keeps a rejection harmless (#22033).

``services/stale_sync_files.py`` is loaded by path with its heavy collaborators stubbed (the node, the backend,
git); its own logic runs for real. Each check has a contrast: the call that proceeds and the one that must not.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from autobot_shared.slm_stale_file_actions import MAX_FILES_PER_PROPOSAL
from services import stale_sync_audit as audit
from services.stale_sync_targets import StaleFile

_BACKEND = Path(__file__).resolve().parents[2]
_WHEN = datetime(2026, 1, 2, tzinfo=timezone.utc)
_APPROVAL = "00000000-0000-4000-8000-000000000044"
_ROOT = "/srv/node"


def _file(path: str, blob: str = "a" * 40, old: str = _ROOT) -> StaleFile:
    return StaleFile(old, "backend", path, 5, _WHEN, blob)


def _entry(path: str, blob: str = "a" * 40) -> dict:
    return {"path": path, "size_bytes": 5, "modified_at": _WHEN.isoformat(), "blob": blob}


class _Unavailable(Exception):
    def __init__(self, status_code: int = 503, detail: str = "down", reason: str = "x"):
        super().__init__(detail)
        self.status_code, self.detail = status_code, detail


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(
        events=[],
        posts=[],
        removed=[],
        backend_status=201,
        claim_status=200,
        claim_files=[],
        audit_down=False,
        key_ok=True,
        ssh_down=False,
        fresh=[],
        node=SimpleNamespace(node_id="n1", auth_method="key"),
    )

    async def call_main_backend(method, path, *, content=None, **_kw):
        body = json.loads(content)
        if path.endswith("/claim"):
            state.events.append("claim")
            data = {"old_target": _ROOT, "files": state.claim_files}
            return SimpleNamespace(status_code=state.claim_status, json=lambda: data)
        state.events.append("post")
        state.posts.append(body)
        return SimpleNamespace(
            status_code=state.backend_status, json=lambda: {"approval_id": "ap1", "status": "pending", "created": True}
        )

    async def key_ok(_node):
        return state.key_ok

    async def remove_files(_node, root, files):
        state.events.append("remove")
        state.removed.append((root, [f.path for f in files]))
        if state.ssh_down:
            raise sys.modules["services.stale_sync_targets"].StaleListingError("ssh down")
        return {f.path: "removed" for f in files}

    async def record(*, actor, node_id, outcome, phase, **details):
        if state.audit_down and phase != audit.PHASE_FINISHED:
            raise audit.StaleFileAuditUnavailable("down")
        state.events.append(f"audit:{phase}:{outcome}")

    _module(monkeypatch, "services.git_tracker", DEFAULT_REPO_PATH="/srv/code_source")
    _module(
        monkeypatch,
        "services.main_backend_client",
        call_main_backend=call_main_backend,
        MainBackendUnavailable=_Unavailable,
    )
    _module(monkeypatch, "services.node_ssh_key_probe", key_auth_and_sudo_work=key_ok)
    _module(monkeypatch, "services.role_registry", DEFAULT_ROLES=[])
    _module(monkeypatch, "services.stale_sync_remote", remove_files=remove_files, stat_candidates=None)
    _module(monkeypatch, "models.database", Node=object, NodeRole=object)
    monkeypatch.setattr(audit, "record_cleanup_step", record)
    spec = importlib.util.spec_from_file_location(
        "_stale_sync_files_under_test", _BACKEND / "services/stale_sync_files.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "_stale_sync_files_under_test", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    async def load_node(_db, _node_id):
        return state.node

    async def list_stale(_db, node_id):
        return mod.StaleListing(node_id, commit="c0ffee1", stale=state.fresh)

    monkeypatch.setattr(mod, "_load_node", load_node)
    monkeypatch.setattr(mod, "list_stale_files", list_stale)
    state.mod = mod
    return state


# --- propose --------------------------------------------------------------


async def test_nothing_stale_proposes_nothing_and_writes_no_audit_row(env) -> None:
    assert await env.mod.propose_cleanup(None, "n1", "alice") == []
    assert env.events == []


async def test_one_proposal_per_old_location_with_a_capped_count_and_whole_paths(env) -> None:
    long_path = "d/" * 300 + "x.py"
    env.fresh = [_file(f"f{i}.py") for i in range(MAX_FILES_PER_PROPOSAL + 3)] + [_file(long_path, old="/srv/agent")]
    results = await env.mod.propose_cleanup(None, "n1", "alice")
    by_target = {post["old_target"]: post for post in env.posts}
    assert set(by_target) == {_ROOT, "/srv/agent"} and len(results) == 2
    assert (
        len(by_target[_ROOT]["files"]) == MAX_FILES_PER_PROPOSAL
        and by_target[_ROOT]["total_found"] == MAX_FILES_PER_PROPOSAL + 3
    )
    assert by_target["/srv/agent"]["files"][0]["path"] == long_path  # the cap counts items, never shortens a path
    assert env.events[0] == "audit:proposed:success"


async def test_an_unavailable_audit_trail_proposes_nothing(env) -> None:
    env.fresh = [_file("a.py")]
    env.audit_down = True
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.propose_cleanup(None, "n1", "alice")
    assert refused.value.status_code == 503 and env.posts == []


@pytest.mark.parametrize(("status", "expected"), [(409, 409), (500, 502)])
async def test_a_backend_that_does_not_create_the_proposal_is_an_error_not_a_success(env, status, expected) -> None:
    env.fresh = [_file("a.py")]
    env.backend_status = status
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.propose_cleanup(None, "n1", "alice")
    assert refused.value.status_code == expected


async def test_a_listing_that_cannot_be_trusted_proposes_nothing(env, monkeypatch) -> None:
    async def broken(_db, node_id):
        return env.mod.StaleListing(node_id, error="shallow clone")

    monkeypatch.setattr(env.mod, "list_stale_files", broken)
    with pytest.raises(env.mod.StaleRefused):
        await env.mod.propose_cleanup(None, "n1", "alice")
    assert env.posts == []


# --- approved removal -----------------------------------------------------


async def test_the_order_is_fresh_listing_then_intent_row_then_claim_then_removal_then_completion(env) -> None:
    env.fresh = [_file("a.py")]
    env.claim_files = [_entry("a.py")]
    report = await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert env.events == ["audit:intent:success", "claim", "remove", "audit:finished:success"]
    assert report == [{"old_target": _ROOT, "path": "a.py", "result": "removed"}]


async def test_a_refused_claim_removes_nothing_and_leaves_a_denied_row(env) -> None:
    env.fresh, env.claim_files, env.claim_status = [_file("a.py")], [_entry("a.py")], 403
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert refused.value.status_code == 403 and env.removed == []
    assert env.events[-1] == "audit:finished:denied"


async def test_no_committed_intent_row_means_no_claim_and_no_removal(env) -> None:
    env.fresh, env.claim_files, env.audit_down = [_file("a.py")], [_entry("a.py")], True
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert refused.value.status_code == 503 and "claim" not in env.events and env.removed == []


async def test_unproven_key_access_stops_before_anything_is_claimed(env) -> None:
    env.key_ok = False
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert refused.value.status_code == 409 and env.events == []


async def test_only_approved_files_that_are_still_stale_are_removed(env) -> None:
    env.fresh = [_file("keep.py"), _file("approved.py"), _file("moved.py", blob="b" * 40)]
    env.claim_files = [_entry("approved.py"), _entry("gone.py"), _entry("moved.py", blob="a" * 40)]
    report = await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert env.removed == [(_ROOT, ["approved.py"])]  # keep.py was never approved; the others are no longer stale
    results = {row["path"]: row["result"] for row in report}
    assert results == {"approved.py": "removed", "gone.py": "no_longer_stale", "moved.py": "no_longer_stale"}


async def test_an_ssh_failure_after_the_spend_is_reported_failed_and_audited(env) -> None:
    env.fresh, env.claim_files, env.ssh_down = [_file("a.py")], [_entry("a.py")], True
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert refused.value.status_code == 502 and env.events[-1] == "audit:finished:failed"


async def test_an_approved_file_whose_old_target_is_absent_from_the_fresh_listing_is_dropped(env) -> None:
    env.fresh = [_file("a.py", old="/srv/other")]  # the same path and blob, but under another old target
    env.claim_files = [_entry("a.py")]
    report = await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert env.removed == [(_ROOT, [])] and report == [
        {"old_target": _ROOT, "path": "a.py", "result": "no_longer_stale"}
    ]


async def test_after_an_ssh_failure_the_outcome_is_recorded_unknown_with_the_relisted_remainder(
    env, monkeypatch
) -> None:
    env.fresh, env.claim_files, env.ssh_down = [_file("a.py"), _file("b.py")], [_entry("a.py"), _entry("b.py")], True
    seen = []

    async def relist(_db, node_id):  # a.py is gone by now, b.py is still there
        return env.mod.StaleListing(node_id, stale=[_file("b.py")])

    async def finish(actor, node_id, approval_id, outcome, **details):
        seen.append((outcome, details))

    calls = iter([env.fresh, None])
    original = env.mod.list_stale_files

    async def listing(db, node_id):
        return await (original if next(calls) else relist)(db, node_id)

    monkeypatch.setattr(env.mod, "list_stale_files", listing)
    monkeypatch.setattr(env.mod, "_finish", finish)
    with pytest.raises(env.mod.StaleRefused) as refused:
        await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert refused.value.status_code == 502 and "1 file(s) may have been removed" in refused.value.reason
    outcome, details = seen[-1]
    assert outcome == "failed" and details["outcome"] == "unknown"
    assert details["may_have_removed"] == 1 and details["remaining"] == ["b.py"]


async def test_contrast_when_the_relisting_fails_too_the_remainder_is_unknown_not_guessed(env, monkeypatch) -> None:
    env.fresh, env.claim_files, env.ssh_down = [_file("a.py")], [_entry("a.py")], True
    seen = []
    calls = iter([True, False])
    original = env.mod.list_stale_files

    async def listing(db, node_id):
        if next(calls):
            return await original(db, node_id)
        return env.mod.StaleListing(node_id, error="unreachable")

    async def finish(actor, node_id, approval_id, outcome, **details):
        seen.append(details)

    monkeypatch.setattr(env.mod, "list_stale_files", listing)
    monkeypatch.setattr(env.mod, "_finish", finish)
    with pytest.raises(env.mod.StaleRefused):
        await env.mod.remove_approved(None, "n1", _APPROVAL)
    assert seen[-1]["remaining"] is None and seen[-1]["may_have_removed"] == 1
