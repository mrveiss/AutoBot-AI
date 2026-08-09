# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The resolve deletion guard (#13851).

A drift "resolve" is a delete-style rsync, so everything on the host that
source does not have is removed. On a live, fully-synced host a dry run of the
autobot-backend resolve reported **55 deletions** — 34 files under
plugins/core-plugins (the entire plugin subsystem) and the audit logs — because
the drift signal that recommends resolving cannot see who owns those files.

That inverts the usual severity calculation: a noisy detector is normally low
priority, but this one makes "keep the deployment tidy" an actively unsafe
instruction. The guard turns the destructive half of the operation into
something the operator inspects before it happens.

The rsync invocations here run against tmp_path only — no live install is
touched — and the #13312 subprocess guard permits them because they are the
subject of the test rather than an accident of one.
"""

from __future__ import annotations

import asyncio
import importlib.util
import shutil
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _code_sync_import import import_code_sync  # noqa: E402

code_sync = import_code_sync()

_rsync_local_cmd = code_sync._rsync_local_cmd
_parse_rsync_deletions = code_sync._parse_rsync_deletions
_preview_rsync_deletions = code_sync._preview_rsync_deletions
_resolve_deletion_guard = code_sync._resolve_deletion_guard
_with_blocked_paths = code_sync._with_blocked_paths

_HAS_RSYNC = shutil.which("rsync") is not None
_needs_rsync = pytest.mark.skipif(not _HAS_RSYNC, reason="rsync not installed on this host")

# tests/api/conftest.py blocks asyncio.create_subprocess_exec for the whole
# package (#13312) because api/code_sync.py shells out at the LIVE install and
# rsync creates its destination before failing. Its own guidance is to install a
# stand-in "when the invocation itself is under test" — which is exactly this
# file. The stand-in here is the real function, captured at import time before
# the hookwrapper swaps it, and every command it runs is confined to tmp_path,
# so nothing outside the test's own directory is reachable. A faked rsync would
# verify only that the parser matches the fake.
_REAL_SUBPROCESS_EXEC = asyncio.create_subprocess_exec


def _load_real_drift_checker():
    """Real-load services/drift_checker.py, bypassing the conftest MagicMock.

    The root conftest stubs ``services.*``, so ``owned_subtrees`` and
    ``deploy_only_entries`` as seen by api.code_sync return an empty iterator —
    a preview test against those stubs would pass no matter what the deployment
    map says. These tests are specifically about the real map (does the backend
    protect the plugins subtree? the shared symlink?), so they need the real
    module. Loaded standalone, with the dependency-free deploy_artifacts real
    too, and never installed into sys.modules.
    """
    backend_root = Path(__file__).resolve().parents[2]
    services_dir = backend_root / "services"

    da_spec = importlib.util.spec_from_file_location(
        "services.deploy_artifacts", services_dir / "deploy_artifacts.py"
    )
    da = importlib.util.module_from_spec(da_spec)
    da_spec.loader.exec_module(da)

    gt_stub = types.ModuleType("services.git_tracker")
    gt_stub.DEFAULT_REPO_PATH = "/opt/autobot/code_source"

    saved = {k: sys.modules.get(k) for k in ("services.deploy_artifacts", "services.git_tracker")}
    sys.modules["services.deploy_artifacts"] = da
    sys.modules["services.git_tracker"] = gt_stub
    try:
        spec = importlib.util.spec_from_file_location("_drift_checker_guard_test", services_dir / "drift_checker.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for key, value in saved.items():
            if value is None:
                sys.modules.pop(key, None)
            else:
                sys.modules[key] = value
    return module


_REAL_DC = _load_real_drift_checker()


@pytest.fixture
def real_deployment_map(monkeypatch):
    """Point code_sync's exclude builder at the REAL component ownership map."""
    monkeypatch.setattr(code_sync, "owned_subtrees", _REAL_DC.owned_subtrees)
    monkeypatch.setattr(code_sync, "deploy_only_entries", _REAL_DC.deploy_only_entries)


def real_rsync():
    """Re-enable real subprocess spawning for tmp_path-confined rsync runs.

    A context manager, not a fixture: the conftest installs its block in
    ``pytest_runtest_call``, which runs AFTER fixture setup, so a fixture-level
    monkeypatch would be overwritten before the test body ran.
    """
    return patch.object(asyncio, "create_subprocess_exec", _REAL_SUBPROCESS_EXEC)


def _run(coro):
    return asyncio.run(coro)


def _write(path: Path, content: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


# ---------------------------------------------------------------------------
# Parsing — the itemized `*deleting` lines
# ---------------------------------------------------------------------------


def test_parse_extracts_only_deletions() -> None:
    output = (
        "sending incremental file list\n"
        "*deleting   plugins/core-plugins/hello/main.py\n"
        ">f+++++++++ new_file.py\n"
        "*deleting   logs/audit/audit_2026-08-03.jsonl\n"
        "cd+++++++++ some_dir/\n"
    )
    assert _parse_rsync_deletions(output) == [
        "plugins/core-plugins/hello/main.py",
        "logs/audit/audit_2026-08-03.jsonl",
    ]


def test_parse_of_a_clean_run_is_empty() -> None:
    assert _parse_rsync_deletions("sending incremental file list\n\nsent 1 bytes\n") == []


# ---------------------------------------------------------------------------
# Preview — a real rsync dry run against tmp dirs
# ---------------------------------------------------------------------------


@_needs_rsync
def test_preview_reports_a_deployed_file_absent_from_source(tmp_path) -> None:
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    _write(src / "kept.py")
    _write(dep / "kept.py")
    _write(dep / "orphan.py")
    cmd = _rsync_local_cmd(str(tmp_path), "autobot-slm-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert ok is True
    assert deletions == ["orphan.py"]


@_needs_rsync
def test_preview_is_a_dry_run_and_deletes_nothing(tmp_path) -> None:
    """The whole point: previewing must not perform the deletion it reports."""
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    src.mkdir()
    orphan = _write(dep / "orphan.py")
    cmd = _rsync_local_cmd(str(tmp_path), "autobot-slm-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        _run(_preview_rsync_deletions(cmd))
    assert orphan.is_file()


@_needs_rsync
def test_preview_of_an_identical_tree_is_clean(tmp_path) -> None:
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    _write(src / "same.py", b"same")
    _write(dep / "same.py", b"same")
    cmd = _rsync_local_cmd(str(tmp_path), "autobot-slm-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert (ok, deletions) == (True, [])


@_needs_rsync
def test_preview_honours_the_excludes_the_real_sync_will_use(tmp_path) -> None:
    """The preview and the sync are built by the same function, so a protected
    path is neither previewed as a deletion nor actually deleted. A preview
    built from a different exclude list would clear a resolve that then removes
    something the operator was never shown."""
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    src.mkdir()
    _write(dep / "logs" / "audit" / "audit_2026-08-03.jsonl", b"{}")
    _write(dep / ".env", b"SECRET=1")
    cmd = _rsync_local_cmd(str(tmp_path), "autobot-slm-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert (ok, deletions) == (True, [])


def test_failed_preview_is_not_read_as_no_deletions() -> None:
    """A dry run that could not be taken is not evidence that nothing would be
    deleted — the guard must refuse, not proceed."""
    with patch.object(
        code_sync,
        "_preview_rsync_deletions",
        AsyncMock(return_value=(False, [], "rsync: connection unexpectedly closed")),
    ):
        allowed, blocked, message = _run(
            _resolve_deletion_guard("autobot-slm-backend", "/src", [], "/src/c", "/dep/c")
        )
    assert allowed is False
    assert blocked == []
    assert "could not preview deletions" in message


def test_guard_blocks_and_reports_the_paths() -> None:
    doomed = ["plugins/core-plugins/hello/main.py", "logs/audit/audit_2026-08-03.jsonl"]
    with patch.object(code_sync, "_preview_rsync_deletions", AsyncMock(return_value=(True, doomed, ""))):
        allowed, blocked, message = _run(
            _resolve_deletion_guard("autobot-backend", "/src", [], "/src/c", "/dep/c")
        )
    assert allowed is False
    assert blocked == doomed
    assert "would be DELETED" in message
    assert "force=true" in message


def test_guard_allows_a_resolve_that_deletes_nothing() -> None:
    with patch.object(code_sync, "_preview_rsync_deletions", AsyncMock(return_value=(True, [], ""))):
        allowed, blocked, message = _run(
            _resolve_deletion_guard("autobot-backend", "/src", [], "/src/c", "/dep/c")
        )
    assert (allowed, blocked, message) == (True, [], "")


# ---------------------------------------------------------------------------
# The async job carries only a message, so the paths must travel inside it
# ---------------------------------------------------------------------------


def test_blocked_paths_are_inlined_into_the_job_message() -> None:
    message = _with_blocked_paths("Refusing.", ["a.py", "b.py"])
    assert "a.py" in message and "b.py" in message


def test_blocked_path_list_is_capped_with_a_remainder_count() -> None:
    blocked = [f"f{i}.py" for i in range(55)]
    message = _with_blocked_paths("Refusing.", blocked)
    assert "f0.py" in message
    assert "(+35 more)" in message


def test_no_blocked_paths_leaves_the_message_alone() -> None:
    assert _with_blocked_paths("Refusing.", []) == "Refusing."


# ---------------------------------------------------------------------------
# #13851 review: the guard must not fire on entries the DEPLOY itself creates.
#
# A refusal an operator cannot avoid is worse than no guard: it trains everyone
# to pass force=true, which switches the guard off for the deletions it exists
# to catch. These run the real preview against a tree shaped like a deployed
# backend and assert it comes back clean.
# ---------------------------------------------------------------------------


@_needs_rsync
def test_backend_preview_is_clean_with_only_the_shared_symlink(tmp_path, real_deployment_map) -> None:
    """<backend>/autobot_shared is a symlink created by
    _ensure_autobot_shared_symlink (#10912) and absent from code_source. Before
    the exclude, every unforced backend resolve refused over it."""
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    _write(src / "main.py", b"same")
    _write(dep / "main.py", b"same")
    (tmp_path / "shared").mkdir()
    (dep / "autobot_shared").symlink_to(tmp_path / "shared", target_is_directory=True)

    cmd = _rsync_local_cmd(str(tmp_path), "autobot-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert (ok, deletions) == (True, [])
    assert (dep / "autobot_shared").is_symlink(), "the symlink must survive the preview"


@_needs_rsync
def test_backend_preview_is_clean_with_plugins_and_runtime_state(tmp_path, real_deployment_map) -> None:
    """The live-host shape that produced the 55-deletion dry run: the plugin
    subtree another component owns, the audit logs, and the worker registry."""
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    _write(src / "main.py", b"same")
    _write(dep / "main.py", b"same")
    _write(dep / "plugins" / "core-plugins" / "hello" / "main.py", b"plugin code")
    _write(dep / "logs" / "audit" / "audit_2026-08-03.jsonl", b"{}")
    _write(dep / "config" / "npu_workers.yaml", b"workers: []\n")

    cmd = _rsync_local_cmd(str(tmp_path), "autobot-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert (ok, deletions) == (True, [])


@_needs_rsync
def test_npu_worker_preview_protects_the_rendered_script(tmp_path, real_deployment_map) -> None:
    """npu-worker.py is rendered from a .j2 in the role and has no counterpart
    in the component's source dir, so a deleting sync removes the running
    worker script."""
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    src.mkdir()
    _write(dep / "npu-worker.py", b"# rendered by ansible\n")

    cmd = _rsync_local_cmd(str(tmp_path), "autobot-npu-worker", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert (ok, deletions) == (True, [])


@_needs_rsync
def test_a_genuinely_stale_file_is_still_reported(tmp_path, real_deployment_map) -> None:
    """The protections must not blanket everything — an ordinary leftover the
    component's source really does not have is exactly what to refuse on."""
    src = tmp_path / "src"
    dep = tmp_path / "dep"
    src.mkdir()
    _write(dep / "removed_module.py", b"old code")

    cmd = _rsync_local_cmd(str(tmp_path), "autobot-backend", [], source_dir=str(src), dest_dir=str(dep))
    with real_rsync():
        ok, deletions, _ = _run(_preview_rsync_deletions(cmd))
    assert (ok, deletions) == (True, ["removed_module.py"])
