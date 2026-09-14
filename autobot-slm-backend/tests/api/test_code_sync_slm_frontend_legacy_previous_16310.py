# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310 — the pre-#15610 ``dist.previous/`` rollback directory is a real
directory copy, not a symlink, and the ``dist-<id>/`` pruner in
``_prune_old_builds`` never matches it (no ``dist-`` prefix) -- so it survived
every publish since the #15610 symlink layout landed. ``_remove_legacy_previous``
retires it, only once ``current``/``previous`` are both the new-layout symlinks,
so nothing can still be relying on it for a rollback.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from services.slm_frontend_build import _remove_legacy_previous  # noqa: E402


def _bundle(frontend_dir: Path, build_id: str) -> Path:
    bundle = frontend_dir / f"dist-{build_id}"
    bundle.mkdir(parents=True)
    (bundle / "index.html").write_text(build_id, encoding="utf-8")
    return bundle


def _plant_legacy_previous(frontend_dir: Path) -> Path:
    legacy = frontend_dir / "dist.previous"
    legacy.mkdir()
    (legacy / "index.html").write_text("legacy", encoding="utf-8")
    return legacy


def test_legacy_previous_removed_once_current_and_previous_are_symlinks(tmp_path) -> None:
    frontend_dir = tmp_path / "autobot-slm-frontend"
    frontend_dir.mkdir()
    _bundle(frontend_dir, "aaa")
    _bundle(frontend_dir, "bbb")
    (frontend_dir / "current").symlink_to("dist-bbb")
    (frontend_dir / "previous").symlink_to("dist-aaa")
    legacy = _plant_legacy_previous(frontend_dir)

    _remove_legacy_previous(frontend_dir)

    assert not legacy.exists(), "dist.previous/ must be removed once both symlinks exist (#16310)"


def test_legacy_previous_survives_before_previous_link_exists(tmp_path) -> None:
    """First publish under #15610: only `current` exists yet -- leave it."""
    frontend_dir = tmp_path / "autobot-slm-frontend"
    frontend_dir.mkdir()
    _bundle(frontend_dir, "aaa")
    (frontend_dir / "current").symlink_to("dist-aaa")
    legacy = _plant_legacy_previous(frontend_dir)

    _remove_legacy_previous(frontend_dir)

    assert legacy.is_dir(), "no `previous` symlink yet -- dist.previous/ must survive"


def test_legacy_previous_survives_when_absent(tmp_path) -> None:
    """No-op, does not raise, when there is nothing to remove."""
    frontend_dir = tmp_path / "autobot-slm-frontend"
    frontend_dir.mkdir()
    _bundle(frontend_dir, "aaa")
    _bundle(frontend_dir, "bbb")
    (frontend_dir / "current").symlink_to("dist-bbb")
    (frontend_dir / "previous").symlink_to("dist-aaa")

    _remove_legacy_previous(frontend_dir)  # must not raise

    assert not (frontend_dir / "dist.previous").exists()


def test_a_dist_previous_symlink_is_left_alone(tmp_path) -> None:
    """Only a real directory copy is a target -- a symlink named the same is
    not the pre-#15610 layout and must not be unlinked by this cleanup."""
    frontend_dir = tmp_path / "autobot-slm-frontend"
    frontend_dir.mkdir()
    _bundle(frontend_dir, "aaa")
    _bundle(frontend_dir, "bbb")
    (frontend_dir / "current").symlink_to("dist-bbb")
    (frontend_dir / "previous").symlink_to("dist-aaa")
    (frontend_dir / "dist.previous").symlink_to("dist-aaa")

    _remove_legacy_previous(frontend_dir)

    assert (frontend_dir / "dist.previous").is_symlink()
