# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15462 — the SLM self-sync-from-code-source path must publish atomically
and fail loudly, matching the publish the shared Ansible task file does
(#15430, #15557, #15610).

Before this fix, ``_build_slm_frontend`` (formerly in ``api/code_sync.py``,
now ``build_slm_frontend`` in ``services/slm_frontend_build.py`` — moved out
of the router module in the #15462 review, since it was pushing
``code_sync.py`` over its grandfathered line-count ceiling, #14236) built
straight into the served ``dist/`` via a plain ``npm run build`` and
swallowed every failure with ``logger.warning`` + ``return`` — the exact
live incident this issue is about (a directory holding only
``favicon.svg``, all services green).

#15610 removed the last window in that publish. It used to be two renames
(``dist`` -> ``dist.previous``, then ``dist.staging`` -> ``dist``) with no
served directory in between. It is now a single ``rename(2)`` over the
``current`` symlink, and ``test_publish_replaces_current_with_one_rename``
below asserts that as behaviour — not as a code shape — by watching every
filesystem operation the publish performs on the served name.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio  # noqa: E402

import services.slm_frontend_build as slm_frontend_build  # noqa: E402
from services.slm_frontend_build import (  # noqa: E402
    _npm_build_slm,
    _publish_build,
    _seed_current_from_legacy_dist,
    build_slm_frontend,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _fake_exec_factory(build_rc: int):
    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 0 if cmd[:2] != ("npm", "run") else build_rc
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    return _fake_exec


def _seed_bundle(frontend_dir: Path, build_id: str, marker: str) -> Path:
    """Write a build directory in the #15610 layout and return it."""
    bundle = frontend_dir / f"dist-{build_id}"
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text(marker, encoding="utf-8")
    return bundle


def _seed_published(frontend_dir: Path, build_id: str, marker: str) -> Path:
    """A node that already serves a bundle: `current` points at it."""
    bundle = _seed_bundle(frontend_dir, build_id, marker)
    (frontend_dir / "current").symlink_to(bundle.name)
    return bundle


def _served(frontend_dir: Path) -> str:
    return (frontend_dir / "current" / "index.html").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Publish is atomic: `current` is untouched unless the build has an index.html
# ---------------------------------------------------------------------------


def test_publish_refuses_when_build_has_no_index_html(tmp_path) -> None:
    """A build that reports success but writes nothing (the live #15462
    shape) must not be published — `current` must stay exactly where it was."""
    frontend_dir = tmp_path
    _seed_published(frontend_dir, "20260101T000000000Z", "OLD-WORKING-BUNDLE")
    broken = frontend_dir / "dist-20260102T000000000Z"
    broken.mkdir()
    (broken / "favicon.svg").write_text("<svg/>", encoding="utf-8")

    result = _run(_publish_build(str(frontend_dir), "20260102T000000000Z"))

    assert result is False
    assert _served(frontend_dir) == "OLD-WORKING-BUNDLE"
    assert not (frontend_dir / "previous").exists()


def test_publish_flips_current_and_keeps_the_replaced_bundle_as_previous(tmp_path) -> None:
    """A successful build IS published, and the bundle it replaces stays
    reachable as `previous` — the rollback target `dist.previous` used to be."""
    frontend_dir = tmp_path
    _seed_published(frontend_dir, "20260101T000000000Z", "OLD-WORKING-BUNDLE")
    _seed_bundle(frontend_dir, "20260102T000000000Z", "NEW-BUNDLE")

    result = _run(_publish_build(str(frontend_dir), "20260102T000000000Z"))

    assert result is True
    assert _served(frontend_dir) == "NEW-BUNDLE"
    assert (frontend_dir / "previous" / "index.html").read_text(encoding="utf-8") == "OLD-WORKING-BUNDLE"
    assert os.readlink(frontend_dir / "current") == "dist-20260102T000000000Z"


def test_publish_replaces_current_with_one_rename(tmp_path) -> None:
    """#15610, as behaviour: the served name is only ever *replaced*.

    The defect was a publish that unlinked the served name and created it
    again, leaving a window in which it resolved to nothing. Watching every
    replace/unlink/rmtree the publish performs is what distinguishes a fix
    from a rename of the same two-step dance: a second `replace` onto
    `current`, or any `unlink` of it, is the window coming back.
    """
    frontend_dir = tmp_path
    _seed_published(frontend_dir, "20260101T000000000Z", "OLD-WORKING-BUNDLE")
    _seed_bundle(frontend_dir, "20260102T000000000Z", "NEW-BUNDLE")

    events: list[tuple[str, str]] = []
    real_replace, real_unlink, real_rmtree = os.replace, Path.unlink, shutil.rmtree

    def _spy_replace(src, dst, *args, **kwargs):
        events.append(("replace", Path(dst).name))
        return real_replace(src, dst, *args, **kwargs)

    def _spy_unlink(self, *args, **kwargs):
        events.append(("unlink", self.name))
        return real_unlink(self, *args, **kwargs)

    def _spy_rmtree(path, *args, **kwargs):
        events.append(("rmtree", Path(path).name))
        return real_rmtree(path, *args, **kwargs)

    with (
        patch.object(slm_frontend_build.os, "replace", _spy_replace),
        patch.object(Path, "unlink", _spy_unlink),
        patch.object(slm_frontend_build.shutil, "rmtree", _spy_rmtree),
    ):
        assert _run(_publish_build(str(frontend_dir), "20260102T000000000Z")) is True

    assert [e for e in events if e == ("replace", "current")] == [
        ("replace", "current")
    ], f"the served name must be replaced exactly once, by one rename(2); saw {events!r}"
    assert (
        "unlink",
        "current",
    ) not in events, f"the publish unlinked the served name — that is the #15610 window, restored: {events!r}"
    assert ("rmtree", "current") not in events, f"the publish removed the served name: {events!r}"
    assert _served(frontend_dir) == "NEW-BUNDLE"


def test_publish_prunes_to_the_bound_but_never_a_reachable_bundle(tmp_path) -> None:
    """Retention is bounded, and never at the expense of what is reachable.

    A rollback points `current` at an older bundle, so "inside the newest N"
    and "not in use" are different questions. Pruning the bundle being served
    is the outage this module exists to prevent.
    """
    frontend_dir = tmp_path
    for day, marker in ((1, "OLDEST"), (2, "OLDER"), (3, "OLD"), (4, "SERVING")):
        _seed_bundle(frontend_dir, f"2026010{day}T000000000Z", marker)
    # Rolled back: `current` is NOT the newest bundle.
    (frontend_dir / "current").symlink_to("dist-20260101T000000000Z")
    _seed_bundle(frontend_dir, "20260105T000000000Z", "NEW-BUNDLE")

    with patch.object(slm_frontend_build, "_RELEASE_KEEP", 2):
        assert _run(_publish_build(str(frontend_dir), "20260105T000000000Z")) is True

    survivors = sorted(p.name for p in frontend_dir.iterdir() if p.is_dir() and not p.is_symlink())
    assert survivors == [
        "dist-20260101T000000000Z",  # `previous` — the bundle just replaced
        "dist-20260104T000000000Z",  # inside the kept window
        "dist-20260105T000000000Z",  # `current`
    ], survivors
    assert _served(frontend_dir) == "NEW-BUNDLE"


# ---------------------------------------------------------------------------
# Migration: a pre-#15610 dist/ is adopted, never renamed out from under nginx
# ---------------------------------------------------------------------------


def test_seed_adopts_a_legacy_dist_and_leaves_it_in_place(tmp_path) -> None:
    legacy = tmp_path / "dist"
    legacy.mkdir()
    (legacy / "index.html").write_text("LEGACY-BUNDLE", encoding="utf-8")

    _seed_current_from_legacy_dist(tmp_path)

    assert os.readlink(tmp_path / "current") == "dist"
    assert legacy.is_dir(), "the legacy directory must not be renamed — nginx may still name it"
    assert _served(tmp_path) == "LEGACY-BUNDLE"


def test_seed_does_not_move_current_once_it_exists(tmp_path) -> None:
    _seed_published(tmp_path, "20260101T000000000Z", "PUBLISHED")
    (tmp_path / "dist").mkdir()
    (tmp_path / "dist" / "index.html").write_text("STALE-LEGACY", encoding="utf-8")

    _seed_current_from_legacy_dist(tmp_path)

    assert _served(tmp_path) == "PUBLISHED"


# ---------------------------------------------------------------------------
# A failed npm build is reported loudly, never swallowed
# ---------------------------------------------------------------------------


def test_npm_build_returns_false_and_logs_error_on_nonzero_rc(tmp_path, caplog) -> None:
    import logging

    caplog.set_level(logging.ERROR, logger="services.slm_frontend_build")
    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec_factory(build_rc=1)):
        result = _run(_npm_build_slm(str(tmp_path), "20260102T000000000Z"))

    assert result is False
    assert any("frontend build failed" in rec.message for rec in caplog.records)


def test_npm_build_targets_its_own_directory_never_the_served_path(tmp_path) -> None:
    """vite empties its outDir before writing, so the served path is the one
    place the build must never target (#15430)."""
    seen: list[tuple] = []

    async def _fake_exec(*cmd, **kw):
        seen.append(cmd)
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec):
        assert _run(_npm_build_slm(str(tmp_path), "20260102T000000000Z")) is True

    out_dir = seen[0][seen[0].index("--outDir") + 1]
    assert out_dir == "dist-20260102T000000000Z"
    assert out_dir not in ("current", "dist"), "the build must not target the served path"


# ---------------------------------------------------------------------------
# End-to-end: a build failure never publishes and build_slm_frontend
# reports False instead of the old None-always-"succeeded" shape
# ---------------------------------------------------------------------------


def test_build_slm_frontend_returns_false_and_keeps_serving_when_build_fails(tmp_path) -> None:
    _seed_published(tmp_path, "20260101T000000000Z", "OLD-WORKING-BUNDLE")

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        if cmd[:3] == ("sudo", "chown", "-R"):
            proc.returncode = 0
        elif cmd[:2] == ("npm", "ci"):
            proc.returncode = 0
        else:
            proc.returncode = 1  # npm run build:slm fails
        proc.communicate = AsyncMock(return_value=(b"", b"build blew up"))
        return proc

    with (
        patch("services.slm_frontend_build._SLM_FRONTEND_DIR", str(tmp_path)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        result = _run(build_slm_frontend())

    assert result is False
    assert _served(tmp_path) == "OLD-WORKING-BUNDLE"
    assert os.readlink(tmp_path / "current") == "dist-20260101T000000000Z"


def test_build_slm_frontend_keeps_a_legacy_node_serving_when_the_build_fails(tmp_path) -> None:
    """The migration case: `current` has to resolve before the build runs, so
    a failure on the deploy that migrates a node still leaves the previous
    bundle serving (#15557's invariant, under #15610's layout)."""
    legacy = tmp_path / "dist"
    legacy.mkdir()
    (legacy / "index.html").write_text("LEGACY-BUNDLE", encoding="utf-8")

    async def _fake_exec(*cmd, **kw):
        proc = MagicMock()
        proc.returncode = 0 if cmd[:2] != ("npm", "run") else 1
        proc.communicate = AsyncMock(return_value=(b"", b"build blew up"))
        return proc

    with (
        patch("services.slm_frontend_build._SLM_FRONTEND_DIR", str(tmp_path)),
        patch("asyncio.create_subprocess_exec", side_effect=_fake_exec),
    ):
        assert _run(build_slm_frontend()) is False

    assert _served(tmp_path) == "LEGACY-BUNDLE"
