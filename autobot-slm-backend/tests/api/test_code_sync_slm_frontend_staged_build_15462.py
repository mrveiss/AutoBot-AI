# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15462 — the SLM self-sync-from-code-source path must publish atomically
and fail loudly, matching the staged publish update-all-nodes.yml already
does (#15430).

Before this fix, ``_build_slm_frontend`` (formerly in ``api/code_sync.py``,
now ``build_slm_frontend`` in ``services/slm_frontend_build.py`` — moved out
of the router module in the #15462 review, since it was pushing
``code_sync.py`` over its grandfathered line-count ceiling, #14236) built
straight into the served ``dist/`` via a plain ``npm run build`` and
swallowed every failure with ``logger.warning`` + ``return`` — the exact
live incident this issue is about (a directory holding only
``favicon.svg``, all services green).
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio  # noqa: E402

from services.slm_frontend_build import (  # noqa: E402
    _npm_build_slm_staged,
    _publish_staged_slm_build,
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


def _seed_existing_dist(frontend_dir: Path, marker: str) -> None:
    dist = frontend_dir / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(marker, encoding="utf-8")


# ---------------------------------------------------------------------------
# Publish is atomic: dist/ is untouched unless dist.staging has an index.html
# ---------------------------------------------------------------------------


def test_publish_refuses_when_staged_build_has_no_index_html(tmp_path) -> None:
    """A build that reports success but writes nothing (the live #15462
    shape) must not be published — dist/ must stay exactly as it was."""
    frontend_dir = tmp_path
    _seed_existing_dist(frontend_dir, "OLD-WORKING-BUNDLE")
    (frontend_dir / "dist.staging").mkdir()
    (frontend_dir / "dist.staging" / "favicon.svg").write_text("<svg/>", encoding="utf-8")

    result = _run(_publish_staged_slm_build(str(frontend_dir)))

    assert result is False
    assert (frontend_dir / "dist" / "index.html").read_text(encoding="utf-8") == "OLD-WORKING-BUNDLE"
    assert not (frontend_dir / "dist.previous").exists()


def test_publish_swaps_dist_when_staged_build_is_complete(tmp_path) -> None:
    """A successful staged build IS published, and the old bundle survives as
    dist.previous rather than being deleted outright."""
    frontend_dir = tmp_path
    _seed_existing_dist(frontend_dir, "OLD-WORKING-BUNDLE")
    (frontend_dir / "dist.staging").mkdir()
    (frontend_dir / "dist.staging" / "index.html").write_text("NEW-BUNDLE", encoding="utf-8")

    result = _run(_publish_staged_slm_build(str(frontend_dir)))

    assert result is True
    assert (frontend_dir / "dist" / "index.html").read_text(encoding="utf-8") == "NEW-BUNDLE"
    assert (frontend_dir / "dist.previous" / "index.html").read_text(encoding="utf-8") == "OLD-WORKING-BUNDLE"


# ---------------------------------------------------------------------------
# A failed npm build is reported loudly, never swallowed
# ---------------------------------------------------------------------------


def test_npm_build_staged_returns_false_and_logs_error_on_nonzero_rc(tmp_path, caplog) -> None:
    import logging

    caplog.set_level(logging.ERROR, logger="services.slm_frontend_build")
    with patch("asyncio.create_subprocess_exec", side_effect=_fake_exec_factory(build_rc=1)):
        result = _run(_npm_build_slm_staged(str(tmp_path)))

    assert result is False
    assert any("frontend build failed" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# End-to-end: a build failure never publishes and build_slm_frontend
# reports False instead of the old None-always-"succeeded" shape
# ---------------------------------------------------------------------------


def test_build_slm_frontend_returns_false_and_leaves_dist_when_build_fails(tmp_path) -> None:
    _seed_existing_dist(tmp_path, "OLD-WORKING-BUNDLE")

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
    assert (tmp_path / "dist" / "index.html").read_text(encoding="utf-8") == "OLD-WORKING-BUNDLE"
    assert not (tmp_path / "dist.staging").exists() or not (tmp_path / "dist.staging" / "index.html").exists()
