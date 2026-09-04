# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The served bundle is checked, not just the process (#15462).

Each case is a state the live system was actually in, or one step away from it.
The one that matters is `test_a_directory_holding_only_a_favicon_is_unhealthy`:
that is precisely what `/slm/` served 403 from for hours while `/api/health`
reported `healthy`, because every field in that response described a process.
"""

from __future__ import annotations

from pathlib import Path

from services.frontend_bundle_health import frontend_bundle_status


def test_a_complete_bundle_is_healthy(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>ok</title>", encoding="utf-8")
    (tmp_path / "assets").mkdir()

    assert frontend_bundle_status(tmp_path) == "healthy"


def test_a_directory_holding_only_a_favicon_is_unhealthy(tmp_path: Path) -> None:
    """The exact live state: the directory exists, so every "is it deployed"
    check passes, and there is no entry point for nginx to serve."""
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")

    status = frontend_bundle_status(tmp_path)

    assert status.startswith("unhealthy")
    assert "index.html" in status


def test_a_missing_directory_is_not_applicable_not_unhealthy(tmp_path: Path) -> None:
    """A node that serves no UI is not a broken node.

    Backend-only nodes and every developer checkout have no build output. If
    that read as unhealthy, this probe would be degraded by default everywhere
    and would be ignored — which is how the signals that already existed
    stopped being informative.
    """
    assert frontend_bundle_status(tmp_path / "never-deployed").startswith("not_applicable")


def test_a_truncated_index_is_unhealthy(tmp_path: Path) -> None:
    """A zero-byte index.html serves a blank page with a 200, which is worse
    than a 403: monitoring sees success and the user sees nothing."""
    (tmp_path / "index.html").write_text("", encoding="utf-8")

    assert frontend_bundle_status(tmp_path).startswith("unhealthy")


def test_the_reason_names_no_filesystem_path(tmp_path: Path) -> None:
    """`/api/health` on this service is public — the reason must be actionable
    without disclosing where the install lives."""
    (tmp_path / "favicon.svg").write_text("<svg/>", encoding="utf-8")

    status = frontend_bundle_status(tmp_path)

    assert str(tmp_path) not in status
    assert "/" not in status.replace("index.html", "")


def test_the_default_directory_comes_from_the_ssot(monkeypatch) -> None:
    """Not a hardcoded /opt path: the install location is configuration."""
    from services import frontend_bundle_health as module

    resolved = module.bundle_dir()

    # #15610 replaced the served directory with an atomically-flipped pointer,
    # so the name is whichever of the two this node actually has. Both are
    # resolved through the SSOT, which is what this test is about.
    assert resolved.name in {"current", "dist"}
    assert resolved.parent.name == "autobot-slm-frontend"


def test_the_pointer_is_preferred_over_the_legacy_directory(monkeypatch, tmp_path) -> None:
    """A node that has both must be read through the pointer, not the old path.

    During the rollout a node carries `dist` from its last deploy and `current`
    from this one. Reading `dist` there would report the health of a bundle
    nginx has stopped serving — the failure would be a *stale* healthy, which is
    worse than an error because nothing looks wrong.
    """
    from services import frontend_bundle_health as module

    root = tmp_path / "autobot-slm-frontend"
    (root / "current").mkdir(parents=True)
    (root / "dist").mkdir()
    monkeypatch.setattr(module.config.path, "resolve", lambda rel: tmp_path / rel)

    assert module.bundle_dir().name == "current"


def test_a_node_with_only_the_legacy_directory_still_resolves(monkeypatch, tmp_path) -> None:
    """The fallback is what lets a not-yet-migrated node keep reporting."""
    from services import frontend_bundle_health as module

    root = tmp_path / "autobot-slm-frontend"
    (root / "dist").mkdir(parents=True)
    monkeypatch.setattr(module.config.path, "resolve", lambda rel: tmp_path / rel)

    assert module.bundle_dir().name == "dist"
