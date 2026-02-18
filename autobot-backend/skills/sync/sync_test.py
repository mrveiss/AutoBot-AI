# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the skill repo sync engine (Phase 3, Issue #TBD)."""
import os
import tempfile
import textwrap

import pytest
from skills.models import SkillState
from skills.sync.local_sync import LocalDirSync

SAMPLE_SKILL_MD = textwrap.dedent(
    """\
    ---
    name: sample-skill
    version: 1.0.0
    description: A sample skill for testing
    tools: [do_thing]
    ---
    # Sample Skill
    Do a thing.
"""
)

SAMPLE_SKILL_PY = "# skill.py placeholder"


@pytest.fixture
def anyio_backend():
    """Use asyncio backend only (not trio)."""
    return "asyncio"


@pytest.mark.anyio
async def test_local_sync_discovers_skills():
    """LocalDirSync finds SKILL.md in subdirectories and returns packages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "sample-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(SAMPLE_SKILL_MD)
        sync = LocalDirSync(tmpdir)
        packages = await sync.discover()
        assert len(packages) == 1
        assert packages[0]["name"] == "sample-skill"
        assert packages[0]["state"] == SkillState.INSTALLED
        assert "do_thing" in packages[0]["manifest"]["tools"]


@pytest.mark.anyio
async def test_local_sync_includes_skill_py():
    """LocalDirSync includes skill.py content when present."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "with-py")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(SAMPLE_SKILL_MD)
        with open(os.path.join(skill_dir, "skill.py"), "w", encoding="utf-8") as f:
            f.write(SAMPLE_SKILL_PY)
        sync = LocalDirSync(tmpdir)
        packages = await sync.discover()
        assert packages[0]["skill_py"] == SAMPLE_SKILL_PY


@pytest.mark.anyio
async def test_local_sync_skips_dirs_without_skill_md():
    """LocalDirSync ignores directories that don't contain SKILL.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        os.makedirs(os.path.join(tmpdir, "not-a-skill"))
        sync = LocalDirSync(tmpdir)
        packages = await sync.discover()
        assert len(packages) == 0


@pytest.mark.anyio
async def test_local_sync_parses_frontmatter():
    """LocalDirSync correctly parses YAML frontmatter from SKILL.md."""
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = os.path.join(tmpdir, "my-skill")
        os.makedirs(skill_dir)
        with open(os.path.join(skill_dir, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(SAMPLE_SKILL_MD)
        sync = LocalDirSync(tmpdir)
        packages = await sync.discover()
        manifest = packages[0]["manifest"]
        assert manifest["name"] == "sample-skill"
        assert manifest["version"] == "1.0.0"
        assert manifest["description"] == "A sample skill for testing"
