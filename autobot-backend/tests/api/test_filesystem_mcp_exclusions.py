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

from pathlib import Path

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
    envrc = project / ".envrc"
    envrc.write_text("export EXAMPLE_TOKEN=not-a-real-secret\n", encoding="utf-8")
    env_example = project / ".env.example"
    env_example.write_text("EXAMPLE_TOKEN=\n", encoding="utf-8")
    env_sample = project / ".env.sample"
    env_sample.write_text("EXAMPLE_TOKEN=\n", encoding="utf-8")
    env_template = project / ".env.template"
    env_template.write_text("EXAMPLE_TOKEN=\n", encoding="utf-8")

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
        "envrc": envrc,
        "env_example": env_example,
        "env_sample": env_sample,
        "env_template": env_template,
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

    @pytest.mark.parametrize("key", ["env_example", "env_sample", "env_template"])
    def test_committed_env_templates_are_not_over_blocked(self, fake_project, key):
        """``.env.example``/``.env.sample``/``.env.template`` are allowed (review follow-up).

        These carry no real credential material by convention and are
        commonly committed to the repo -- a bare ``.env*`` denylist also
        catching them is an over-block, not a security requirement.
        """
        target = str(fake_project[key])

        assert fs_mcp.is_path_allowed(target) is True

    def test_envrc_still_denied(self, fake_project):
        """``.envrc`` (direnv) commonly carries real exports -- stays denied."""
        assert fs_mcp.is_path_allowed(str(fake_project["envrc"])) is False


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


class TestRealResolverAgreement:
    """The real secrets-store classes must land inside the real exclusion list.

    Review finding on this PR: an earlier version of the fix derived
    ``_EXCLUDED_ROOTS`` from ``ssot_config.config.path.data_path`` while
    ``SecretsManager``/``SecretsService`` still resolved their storage
    through the legacy ``utils.paths_manager.get_data_path()`` -- which
    reads an unset ``config.yaml`` "paths" key and silently falls back to a
    CWD-relative ``"data/..."`` string. In the deployed topology (the
    backend's systemd ``WorkingDirectory`` sits one level below
    ``AUTOBOT_BASE_DIR``) the two resolvers disagreed, so the exclusion list
    protected a path nothing ever wrote to and the live secrets store stayed
    reachable through the bridge.

    These tests instantiate the *real* classes -- not a monkeypatched
    ``_EXCLUDED_ROOTS`` and not a hand-picked path -- and check the real,
    untouched ``fs_mcp.is_path_allowed`` against whatever those classes
    actually compute. The only stubbing is the unrelated encryption/DB I/O
    (so the test never writes real key material into the checkout); the
    path-resolution code under test always runs for real.

    Deterministic regardless of the CWD pytest happens to be invoked from:
    explicitly ``chdir``s into ``<base_dir>/autobot-backend`` to reproduce
    the deployed topology rather than relying on ambient CWD, which could
    accidentally coincide with base_dir and mask the bug.
    """

    @pytest.fixture(autouse=True)
    def _deployed_topology_cwd(self, monkeypatch):
        """Match the systemd WorkingDirectory being one level below base_dir."""
        backend_cwd = Path(fs_mcp.config.base_dir) / "autobot-backend"
        monkeypatch.chdir(backend_cwd)

    @pytest.fixture(autouse=True)
    def _no_stray_secrets_artifacts(self):
        """Clean up any secrets-store file this test session causes to be
        (re-)provisioned (#14081 review).

        ``api.secrets`` provisions a module-level ``SecretsManager`` singleton
        at import time (pre-existing design, unrelated to this fix), which
        auto-generates a real encryption key the first time the module is
        imported and no key file exists yet. Importing it here (to reach the
        real, unmocked path-resolution code) can be that first import in an
        isolated test run. Removes only files that did not exist before this
        test and were created during it -- never touches a real,
        pre-existing store.
        """
        data_dir = fs_mcp.config.path.data_path
        candidates = [data_dir / "secrets.key", data_dir / "secrets.json", data_dir / "secrets.db"]
        pre_existing = {p for p in candidates if p.exists()}
        yield
        for p in candidates:
            if p.exists() and p not in pre_existing:
                p.unlink()

    def test_secrets_manager_storage_is_excluded_by_the_real_bridge(self):
        import api.secrets as secrets_api

        # api.secrets provisions a module-level singleton (`secrets_manager`)
        # at import time (pre-existing design, tracked separately -- see
        # #14081 PR discussion) -- reference it directly rather than
        # constructing a second instance, so this test adds no additional
        # encryption-key file I/O beyond what importing the module already
        # does elsewhere in the suite.
        manager = secrets_api.secrets_manager

        assert fs_mcp.is_path_allowed(manager.key_file) is False, (
            f"SecretsManager's real encryption key path {manager.key_file!r} is "
            "reachable through the filesystem MCP bridge."
        )
        assert fs_mcp.is_path_allowed(manager.secrets_file) is False, (
            f"SecretsManager's real secrets store path {manager.secrets_file!r} is "
            "reachable through the filesystem MCP bridge."
        )

    def test_secrets_service_storage_is_excluded_by_the_real_bridge(self, monkeypatch):
        import services.secrets_service as secrets_service_module

        # Stub only the encryption/DB-init I/O -- the path computation this
        # test guards runs unmodified in the real __init__.
        monkeypatch.setattr(
            secrets_service_module.SecretsService,
            "_init_encryption",
            lambda self, encryption_key=None: None,
        )
        monkeypatch.setattr(secrets_service_module.SecretsService, "_init_database", lambda self: None)

        service = secrets_service_module.SecretsService()

        assert fs_mcp.is_path_allowed(service.db_path) is False, (
            f"SecretsService's real database path {service.db_path!r} is "
            "reachable through the filesystem MCP bridge."
        )
