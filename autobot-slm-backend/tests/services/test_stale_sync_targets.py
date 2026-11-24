# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which files under the old code-sync targets are stale: the planning half (#22033).

Every check has its contrast, run through the function production uses: the shape that is stale or a candidate,
and the one that must be kept.
"""

from __future__ import annotations

import pytest

from services import stale_sync_targets as t

_BLOB_A = "a" * 40
_BLOB_B = "b" * 40
_ZERO = "0" * 40
_ROOT = "/srv/node"


def _role(name: str, target: str, source: str) -> dict:
    return {"name": name, "target_path": target, "source_paths": [source]}


def _source(role: str = "backend", old: str = _ROOT, pathspec: str = "autobot-backend") -> t.RoleSource:
    return t.RoleSource(role, old, f"{old}/{pathspec}", pathspec)


def _present(rel: str, blob: str = _BLOB_A) -> t.PresentFile:
    return t.PresentFile(rel, 10, 1_700_000_000, blob)


# --- old targets ----------------------------------------------------------


def test_old_target_is_the_corrected_target_minus_its_added_segments() -> None:
    assert t.old_target_of("/srv/node/autobot-backend", 1) == "/srv/node"
    assert t.old_target_of("/srv/agent/slm/agent", 2) == "/srv/agent"


@pytest.mark.parametrize("target,depth", [("/autobot-backend", 1), ("/srv", 2), ("relative/x", 1), ("/srv/x", 0)])
def test_an_old_target_that_would_be_the_filesystem_root_or_nothing_is_refused(target: str, depth: int) -> None:
    assert t.old_target_of(target, depth) is None


def test_only_the_moved_roles_are_planned_and_the_unmoved_ones_are_not_listed() -> None:
    roles = [
        _role("backend", "/srv/node/autobot-backend", "autobot-backend/"),
        _role("slm-agent", "/srv/agent/slm/agent", "autobot-slm-backend/slm/agent/"),
        _role("ai-stack", "/srv/node/autobot-ai-stack", "autobot-ai-stack/"),
        {"name": "frontend", "target_path": "", "source_paths": []},
    ]
    planned = {s.role: (s.old_target, s.pathspec) for s in t.moved_role_sources(roles)}
    assert planned == {
        "backend": ("/srv/node", "autobot-backend"),
        "slm-agent": ("/srv/agent", "autobot-slm-backend/slm/agent"),
    }


# --- git history ----------------------------------------------------------


def test_the_raw_log_yields_every_blob_a_path_ever_had_and_ignores_deletions() -> None:
    log = "\n".join(
        [
            f":000000 100644 {_ZERO} {_BLOB_A} A\tautobot-backend/main.py",
            f":100644 100644 {_BLOB_A} {_BLOB_B} M\tautobot-backend/main.py",
            f":100644 000000 {_BLOB_B} {_ZERO} D\tautobot-backend/gone.py",
            f":100644 100644 {_BLOB_A} {_BLOB_A} R100\tautobot-backend/old.py\tautobot-backend/new.py",
            f":100644 100644 {_BLOB_A} {_BLOB_A} M\tother/elsewhere.py",
            '":000000 100644 x"',
        ]
    )
    assert t.parse_raw_log(log, "autobot-backend") == {"main.py": {_BLOB_A, _BLOB_B}, "new.py": {_BLOB_A}}


async def test_a_shallow_or_unknown_clone_is_an_error_never_an_empty_history(monkeypatch) -> None:
    async def shallow(_repo):
        return t.ShallowCheck.SHALLOW

    monkeypatch.setattr(t, "is_shallow_repository", shallow)
    with pytest.raises(t.StaleListingError, match="shallow"):
        await t.historical_blobs("/repo", "autobot-backend")

    async def full(_repo):
        return t.ShallowCheck.FULL

    async def git(_repo, *args, **_kw):
        return (f":000000 100644 {_ZERO} {_BLOB_A} A\tautobot-backend/a.py\n", 0)

    monkeypatch.setattr(t, "is_shallow_repository", full)
    monkeypatch.setattr(t, "run_git_capture", git)
    assert await t.historical_blobs("/repo", "autobot-backend") == {"a.py": {_BLOB_A}}


async def test_a_failing_git_log_is_an_error_not_an_empty_success(monkeypatch) -> None:
    async def full(_repo):
        return t.ShallowCheck.FULL

    async def failing(_repo, *args, **_kw):
        return ("", 1)

    monkeypatch.setattr(t, "is_shallow_repository", full)
    monkeypatch.setattr(t, "run_git_capture", failing)
    with pytest.raises(t.StaleListingError):
        await t.historical_blobs("/repo", "autobot-backend")


# --- candidates -----------------------------------------------------------


def test_host_state_artifacts_and_unsafe_names_are_never_candidates_but_a_source_file_is() -> None:
    history = {
        "api/x.py": {_BLOB_A},
        ".env": {_BLOB_A},
        "data/state.json": {_BLOB_A},
        "venv/lib/x.py": {_BLOB_A},
        "node_modules/a.js": {_BLOB_A},
        "../escape.py": {_BLOB_A},
        "bad\tname.py": {_BLOB_A},
    }
    wanted, kept = t.candidates(_source(), history, [])
    assert wanted == ["api/x.py"]
    reasons = {k.path: k.reason for k in kept}
    assert reasons[".env"] == t.KEPT_HOST_STATE and reasons["data/state.json"] == t.KEPT_HOST_STATE
    assert reasons["venv/lib/x.py"] == t.KEPT_ARTIFACT and reasons["node_modules/a.js"] == t.KEPT_ARTIFACT
    assert reasons["../escape.py"] == t.KEPT_UNSAFE and reasons["bad\tname.py"] == t.KEPT_UNSAFE


def test_a_path_inside_a_directory_the_corrected_sync_owns_is_claimed_not_stale() -> None:
    protected = [f"{_ROOT}/autobot-backend", "/srv/code_source"]
    assert t.is_claimed(_ROOT, "autobot-backend/main.py", protected) is True
    assert t.is_claimed(_ROOT, "main.py", protected) is False  # contrast: directly under the old target
    history = {"autobot-backend/main.py": {_BLOB_A}, "main.py": {_BLOB_A}}
    wanted, kept = t.candidates(_source(), history, protected)
    assert wanted == ["main.py"] and [(k.path, k.reason) for k in kept] == [("autobot-backend/main.py", t.KEPT_CLAIMED)]


def test_the_agent_file_in_the_agent_dir_is_a_candidate_but_its_new_home_is_not() -> None:
    agent = t.RoleSource("slm-agent", "/srv/agent", "/srv/agent/slm/agent", "autobot-slm-backend/slm/agent")
    wanted, kept = t.candidates(
        agent, {"agent.py": {_BLOB_A}, "slm/agent/agent.py": {_BLOB_A}}, ["/srv/agent/slm/agent"]
    )
    assert wanted == ["agent.py"] and kept[0].path == "slm/agent/agent.py"


# --- classification -------------------------------------------------------


def test_only_a_file_byte_identical_to_a_tracked_version_is_stale() -> None:
    history = {"main.py": {_BLOB_A}}
    stale, kept = t.classify(_source(), [_present("main.py", _BLOB_A)], history)
    assert [(s.path, s.blob, s.old_target, s.role) for s in stale] == [
        ("main.py", _BLOB_A, _ROOT, "backend")
    ] and kept == []
    assert stale[0].size_bytes == 10 and stale[0].modified_at.tzinfo is not None
    stale, kept = t.classify(_source(), [_present("main.py", _BLOB_B)], history)
    assert stale == [] and [(k.path, k.reason) for k in kept] == [("main.py", t.KEPT_MODIFIED)]
