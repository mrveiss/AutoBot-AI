# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Built-in skills have one home; the developer copies are generated (#19341)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from scripts import sync_builtin_skills as sync


def _same_named(root: Path) -> set[str]:
    """Builtin skill directories that also exist under .claude/skills (hyphen or underscore)."""
    dev = {p.name.replace("-", "_") for p in (root / sync.DEV_SKILLS).iterdir() if p.is_dir()}
    builtin = (p for p in (root / sync.BUILTIN).iterdir() if (p / "SKILL.md").is_file())
    return {p.name for p in builtin if p.name.replace("-", "_") in dev}


def test_every_generated_copy_matches_its_canonical_skill() -> None:
    assert sync.drifted() == [], "run python scripts/sync_builtin_skills.py"


def test_every_same_named_pair_is_mirrored_or_a_recorded_homonym() -> None:
    found = _same_named(sync.REPO_ROOT)
    assert found, "no same-named skill pair found -- the scan is not reaching the tree"
    unrecorded = sorted(found - set(sync.MIRRORED) - set(sync.HOMONYMS))
    assert not unrecorded, (
        f"{unrecorded}: a built-in skill and a .claude/skills copy share a name. Add it to MIRRORED "
        "in scripts/sync_builtin_skills.py (and run it), or to HOMONYMS with the reason the texts differ."
    )


def test_every_recorded_entry_still_exists() -> None:
    stale = sorted((set(sync.MIRRORED) | set(sync.HOMONYMS)) - _same_named(sync.REPO_ROOT))
    assert not stale, f"{stale}: recorded in scripts/sync_builtin_skills.py but no longer a same-named pair"


def test_a_crlf_checkout_is_not_drift(tree: Path) -> None:
    copy = tree / sync.DEV_SKILLS / "bugfix" / "SKILL.md"
    copy.write_bytes(copy.read_bytes().replace(b"\n", b"\r\n"))
    assert sync.drifted(tree) == []


def test_no_entry_is_both_mirrored_and_a_homonym() -> None:
    assert not set(sync.MIRRORED) & set(sync.HOMONYMS)


@pytest.fixture()
def tree(tmp_path: Path) -> Path:
    for src, dst in sync.MIRRORED.items():
        (tmp_path / sync.BUILTIN / src).mkdir(parents=True)
        (tmp_path / sync.BUILTIN / src / "SKILL.md").write_text(f"# {src}\n", encoding="utf-8")
        (tmp_path / sync.DEV_SKILLS / dst).mkdir(parents=True)
        shutil.copyfile(tmp_path / sync.BUILTIN / src / "SKILL.md", tmp_path / sync.DEV_SKILLS / dst / "SKILL.md")
    return tmp_path


def test_an_edited_copy_is_reported(tree: Path) -> None:
    copy = tree / sync.DEV_SKILLS / "bugfix" / "SKILL.md"
    copy.write_text("# edited only here\n", encoding="utf-8")
    assert sync.drifted(tree) == [".claude/skills/bugfix/SKILL.md != autobot-backend/skills/builtin/bugfix/SKILL.md"]


def test_a_missing_copy_is_reported(tree: Path) -> None:
    (tree / sync.DEV_SKILLS / "claims-audit" / "SKILL.md").unlink()
    assert len(sync.drifted(tree)) == 1


def test_a_new_unrecorded_pair_is_found(tree: Path) -> None:
    for parent in (sync.BUILTIN / "web_audit", sync.DEV_SKILLS / "web-audit"):
        (tree / parent).mkdir(parents=True)
        (tree / parent / "SKILL.md").write_text("x\n", encoding="utf-8")
    assert "web_audit" in _same_named(tree) - set(sync.MIRRORED) - set(sync.HOMONYMS)
