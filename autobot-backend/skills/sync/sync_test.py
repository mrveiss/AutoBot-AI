# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for the skill repo sync engine (Phase 3)."""
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


@pytest.mark.anyio
async def test_git_repo_sync_clones_and_delegates(tmp_path, monkeypatch):
    """GitRepoSync shallow-clones repo and delegates discovery to LocalDirSync."""
    from unittest.mock import AsyncMock, MagicMock, patch

    # Create a fake skill directory for LocalDirSync to find
    skills_root = tmp_path / "repo"
    skills_root.mkdir()
    skill_dir = skills_root / "my-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: my-skill\nversion: 1.0.0\ndescription: Test\ntools: [do_x]\n---\n# My Skill\n",
        encoding="utf-8",
    )

    async def fake_create_subprocess(*args, **kwargs):
        """Fake subprocess that succeeds immediately without cloning."""
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(b"", b""))
        return mock_proc

    from skills.sync.git_sync import GitRepoSync

    with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess):
        with patch.object(
            GitRepoSync, "_find_skills_dir", return_value=str(skills_root)
        ):
            sync = GitRepoSync("https://example.com/skills.git")
            packages = await sync.discover()

    assert len(packages) == 1
    assert packages[0]["name"] == "my-skill"


@pytest.mark.anyio
async def test_mcp_client_sync_wraps_tools():
    """MCPClientSync converts remote tool descriptors into skill packages."""
    from unittest.mock import AsyncMock, MagicMock, patch

    fake_response_data = {
        "result": {
            "tools": [
                {"name": "echo", "description": "Echo a message"},
            ]
        }
    }

    mock_resp = AsyncMock()
    mock_resp.json = AsyncMock(return_value=fake_response_data)
    mock_resp.status = 200
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    mock_session = MagicMock()
    mock_session.post = MagicMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=None)

    from skills.sync.mcp_sync import MCPClientSync

    with patch("aiohttp.ClientSession", return_value=mock_session):
        sync = MCPClientSync("http://mcp-server.example.com")
        packages = await sync.discover()

    assert len(packages) == 1
    assert packages[0]["name"] == "echo"
    assert packages[0]["manifest"]["remote_mcp"] == "http://mcp-server.example.com"
