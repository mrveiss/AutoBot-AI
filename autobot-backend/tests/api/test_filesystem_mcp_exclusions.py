# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the filesystem MCP bridge's excluded-subtree enforcement (#14081).

Since #14050, an unset AUTOBOT_BASE_DIR resolves ALLOWED_DIRECTORIES to the
whole git checkout, with no exclusion for ``.git/``, ``.env*`` or the
secrets-manager storage path. These tests build a synthetic project tree so
the assertions do not depend on the real repository's contents, then verify:

1. Every excluded subtree is refused even though it sits inside the allowed
   root (the actual vulnerability).
2. Ordinary project files are still reachable (a bridge that refuses
   everything is an outage, not a fix).

Both directions are exercised at the ``_resolve_allowed_path``/
``is_path_allowed`` seam (unit-level) and through the real HTTP endpoint
(``read_text_file_mcp``), matching the established pattern in
``test_filesystem_mcp_resources_prompts.py``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import api.filesystem_mcp as fs_mcp

# Header/key pair the auth gate accepts, mirroring the trusted
# internal-service key mechanism of check_admin_permission (Issue #1145).
_TEST_INTERNAL_KEY = "test-internal-api-key-filesystem-mcp-exclusions"


@pytest.fixture
def fake_project(tmp_path, monkeypatch):
    """Build a project tree with .git/, .env*, and secrets storage.

    Points the bridge's ``ALLOWED_DIRECTORIES``/``_EXCLUDED_ROOTS`` at this
    synthetic tree (via monkeypatch, restored automatically) so the test
    never touches the real checkout's actual VCS history or secrets.
    """
    project = tmp_path / "project"
    git_dir = project / ".git"
    git_dir.mkdir(parents=True)
    git_config = git_dir / "config"
    git_config.write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")

    env_file = project / ".env"
    env_file.write_text("EXAMPLE_TOKEN=not-a-real-secret\n", encoding="utf-8")
    env_local = project / ".env.local"
    env_local.write_text("EXAMPLE_TOKEN=not-a-real-secret-either\n", encoding="utf-8")

    data_dir = project / "data"
    data_dir.mkdir()
    secrets_key = data_dir / "secrets.key"
    secrets_key.write_text("placeholder-key-material\n", encoding="utf-8")
    secrets_json = data_dir / "secrets.json"
    secrets_json.write_text("{}", encoding="utf-8")
    secrets_db = data_dir / "secrets.db"
    secrets_db.write_text("sqlite-stub\n", encoding="utf-8")

    service_keys = data_dir / "service-keys"
    service_keys.mkdir()
    jwt_pem = service_keys / "jwt_rsa_private.pem"
    jwt_pem.write_text("-----BEGIN RSA PRIVATE KEY-----\nplaceholder\n", encoding="utf-8")

    ordinary_file = project / "README.md"
    ordinary_file.write_text("hello world\n", encoding="utf-8")
    ordinary_nested = data_dir / "scheduled_workflows.json"
    ordinary_nested.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(fs_mcp, "ALLOWED_DIRECTORIES", [f"{project}/"])
    monkeypatch.setattr(
        fs_mcp,
        "_EXCLUDED_ROOTS",
        [secrets_key, secrets_json, secrets_db, service_keys],
    )

    return {
        "project": project,
        "git_config": git_config,
        "env_file": env_file,
        "env_local": env_local,
        "secrets_key": secrets_key,
        "secrets_json": secrets_json,
        "secrets_db": secrets_db,
        "jwt_pem": jwt_pem,
        "ordinary_file": ordinary_file,
        "ordinary_nested": ordinary_nested,
    }


class TestExcludedSubtreesUnit:
    """Unit-level checks at the shared resolution seam."""

    @pytest.mark.parametrize(
        "key",
        ["git_config", "env_file", "env_local", "secrets_key", "secrets_json", "secrets_db", "jwt_pem"],
    )
    def test_excluded_path_is_denied(self, fake_project, key):
        """A path under an excluded subtree is refused (#14081 AC1/AC2)."""
        target = str(fake_project[key])

        assert fs_mcp.is_path_allowed(target) is False
        with pytest.raises(ValueError, match="excluded subtree"):
            fs_mcp._resolve_allowed_path(target)

    @pytest.mark.parametrize("key", ["ordinary_file", "ordinary_nested", "project"])
    def test_ordinary_path_still_allowed(self, fake_project, key):
        """Legitimate project files remain reachable (#14081 AC5)."""
        target = str(fake_project[key])

        assert fs_mcp.is_path_allowed(target) is True
        resolved = fs_mcp._resolve_allowed_path(target)
        assert str(resolved) == str(fake_project[key].resolve())

    def test_git_exclusion_is_not_prefix_matched(self, fake_project):
        """A file merely *named* like ``.git`` (not the directory) is unaffected.

        Guards against a naive substring check on ``.git`` that would also
        reject a legitimately named ``.github`` directory or ``foo.git.bak``
        file.
        """
        lookalike_dir = fake_project["project"] / ".github"
        lookalike_dir.mkdir()
        workflow = lookalike_dir / "ci.yml"
        workflow.write_text("name: ci\n", encoding="utf-8")

        assert fs_mcp.is_path_allowed(str(workflow)) is True


@pytest.fixture
def client():
    """TestClient over a minimal app mounting the real filesystem_mcp router.

    Mirrors the pattern in test_filesystem_mcp_resources_prompts.py: the
    admin gate is exercised via dependency_overrides with a header-sensitive
    stub, matching the real check_admin_permission contract (#744/#1145).
    """

    def _admin_gate(request: Request) -> bool:
        if request.headers.get("X-Internal-API-Key") == _TEST_INTERNAL_KEY:
            return True
        raise HTTPException(status_code=401, detail="Authentication required")

    app = FastAPI()
    app.include_router(fs_mcp.router, prefix="/api/filesystem")
    app.dependency_overrides[fs_mcp.check_admin_permission] = _admin_gate
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def admin_headers():
    """Headers granting admin via the trusted internal-service API key."""
    return {"X-Internal-API-Key": _TEST_INTERNAL_KEY}


class TestExcludedSubtreesEndpoint:
    """End-to-end: an authenticated caller still can't reach excluded paths.

    Covers the issue's exact scenario -- an admin/internal-key caller
    attempting to read .git/config or .env through the bridge (#14081 AC4).
    """

    def test_read_git_config_denied(self, client: TestClient, admin_headers, fake_project):
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project["git_config"])},
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_read_env_denied(self, client: TestClient, admin_headers, fake_project):
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project["env_file"])},
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_read_secrets_key_denied(self, client: TestClient, admin_headers, fake_project):
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project["secrets_key"])},
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_read_jwt_key_denied(self, client: TestClient, admin_headers, fake_project):
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project["jwt_pem"])},
            headers=admin_headers,
        )
        assert response.status_code == 403

    def test_read_ordinary_file_still_works(self, client: TestClient, admin_headers, fake_project):
        """The bridge is not a blanket outage -- ordinary files still read (#14081 AC5)."""
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project["ordinary_file"])},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["content"] == "hello world\n"
