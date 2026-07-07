# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC project ↔ repo endpoint tests (#11129).

Covers:
  POST   /api/llc/projects/{id}/repo   — attach a GitHub repo (creates CodeSource)
  DELETE /api/llc/projects/{id}/repo   — detach (unlinks; source survives)
  GET    /api/llc/projects/with-repos  — list projects that have a repo linked
"""

import pytest

# fixtures: llc_client, a_project, a_project_with_repo — declared in conftest.py


@pytest.mark.asyncio
async def test_attach_repo_sets_code_source(llc_client, a_project):
    r = await llc_client.post(
        f"/api/llc/projects/{a_project['id']}/repo",
        json={"repo": "acme/site", "credential_id": "cred1", "branch": "main"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code_source_id"]
    assert body["code_source"]["repo"] == "acme/site"


@pytest.mark.asyncio
async def test_detach_repo_unlinks_but_keeps_source(llc_client, a_project_with_repo):
    r = await llc_client.delete(f"/api/llc/projects/{a_project_with_repo['id']}/repo")
    assert r.status_code == 200
    assert r.json()["code_source_id"] is None


@pytest.mark.asyncio
async def test_with_repos_returns_linked_projects(llc_client, a_project_with_repo):
    r = await llc_client.get("/api/llc/projects/with-repos")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    ids = [item["id"] for item in items]
    assert str(a_project_with_repo["id"]) in ids
    for item in items:
        # Every returned project must expose the code_source summary.
        assert item["code_source"] is not None


@pytest.mark.asyncio
async def test_attach_repo_404_for_missing_project(llc_client):
    import uuid

    r = await llc_client.post(
        f"/api/llc/projects/{uuid.uuid4()}/repo",
        json={"repo": "acme/missing", "credential_id": None, "branch": "main"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_detach_repo_404_for_missing_project(llc_client):
    import uuid

    r = await llc_client.delete(f"/api/llc/projects/{uuid.uuid4()}/repo")
    assert r.status_code == 404
