# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
import pytest
import pytest_asyncio
from transcriber.database import Database


@pytest_asyncio.fixture
async def db(tmp_path):
    d = Database(str(tmp_path / "test.db"))
    await d.connect()
    yield d
    await d.close()


@pytest.mark.asyncio
async def test_create_and_get_project(db):
    pid = await db.create_project("My Project", "A test project", user_id="u1")
    assert isinstance(pid, int)
    project = await db.get_project(pid)
    assert project["name"] == "My Project"
    assert project["description"] == "A test project"
    assert project["user_id"] == "u1"


@pytest.mark.asyncio
async def test_list_projects_user_scoped(db):
    await db.create_project("P1", "", user_id="u1")
    await db.create_project("P2", "", user_id="u2")
    results = await db.list_projects(user_id="u1")
    assert len(results) == 1
    assert results[0]["name"] == "P1"


@pytest.mark.asyncio
async def test_delete_project_cascades(db):
    pid = await db.create_project("P", "", user_id="u1")
    rid = await db.create_recording(pid, "file.wav", "/tmp/file.wav", user_id="u1")
    await db.delete_project(pid)
    assert await db.get_project(pid) is None
    assert await db.get_recording(rid) is None
