# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the filesystem MCP bridge's excluded-subtree enforcement (#14081, #14124).

Since #14050, an unset AUTOBOT_BASE_DIR resolves ALLOWED_DIRECTORIES to the
whole git checkout, with no exclusion for ``.git/``, ``.env*`` or the data
directory. #14081 first excluded four exact filenames under the data
directory (``secrets.key``/``secrets.json``/``secrets.db``/``service-keys``).
#14124 widened that to the whole data-directory *subtree*, because a
filename denylist missed:

- SQLite sidecars (``secrets.db-journal``, ``secrets.db-wal``) and a store
  backup (``secrets.json.bak``) -- same plaintext-equivalent rows, different
  names
- the SSO/SAML signing key (``security/sso_keys/private_key.pem``)
- the threat-detection engine's pickle (``security/user_profiles.pkl``) --
  the sharp one: ``pickle.load()`` on a bridge-writable file is arbitrary
  code execution, not disclosure

These tests build a synthetic project tree so the assertions do not depend
on the real repository's contents, then verify:

1. Every excluded subtree/sidecar is refused even though it sits inside the
   allowed root -- for both read (``read_text_file_mcp``) and write
   (``write_file_mcp``), the actual vulnerability.
2. Ordinary project files are still reachable (a bridge that refuses
   everything is an outage, not a fix).

Both directions are exercised at the ``_resolve_allowed_path``/
``is_path_allowed`` seam (unit-level) and through the real HTTP endpoints,
matching the established pattern in ``test_filesystem_mcp_resources_prompts.py``.

Per #14124's own review note: the two "resolvers" here (``ALLOWED_DIRECTORIES``
and ``_EXCLUDED_ROOTS``) are monkeypatched to point at *this* synthetic tree,
computed with the same ``os.path.realpath`` normalization the real module
uses -- never a hand-typed boolean substitute for ``_is_excluded_path``. Every
assertion below still runs the real, unmodified ``_is_excluded_path``,
``_resolve_allowed_path``, ``is_path_allowed`` and ``_validated_path``.

Fixture content below is deliberately generic placeholder text rather than
PEM-formatted key material: the tests exercise *path* exclusion, not content
handling, and a local secret-scanning hook flags PEM header strings even as
inert test fixtures.
"""

from __future__ import annotations

import os
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
    """Build a project tree with .git/, .env*, and a realistic data directory.

    Points the bridge's ``ALLOWED_DIRECTORIES``/``_EXCLUDED_ROOTS`` at this
    synthetic tree (via monkeypatch, restored automatically) so the test
    never touches the real checkout's actual ``.git`` or data directory.
    """
    project = tmp_path / "project"
    git_dir = project / ".git"
    git_dir.mkdir(parents=True)
    git_config = git_dir / "config"
    git_config.write_text("[core]\n\trepositoryformatversion = 0\n", encoding="utf-8")

    env_file = project / ".env"
    env_file.write_text("EXAMPLE_TOKEN=not-a-real-secret\n", encoding="utf-8")

    data_dir = project / "data"
    data_dir.mkdir()

    secrets_key = data_dir / "secrets.key"
    secrets_key.write_text("placeholder-key-material\n", encoding="utf-8")
    secrets_json = data_dir / "secrets.json"
    secrets_json.write_text("{}", encoding="utf-8")
    secrets_db = data_dir / "secrets.db"
    secrets_db.write_text("sqlite-stub\n", encoding="utf-8")

    # #14124: sidecars and a backup a filename denylist never caught.
    secrets_db_wal = data_dir / "secrets.db-wal"
    secrets_db_wal.write_text("sqlite-wal-stub\n", encoding="utf-8")
    secrets_db_journal = data_dir / "secrets.db-journal"
    secrets_db_journal.write_text("sqlite-journal-stub\n", encoding="utf-8")
    secrets_json_bak = data_dir / "secrets.json.bak"
    secrets_json_bak.write_text("{}", encoding="utf-8")

    service_keys = data_dir / "service-keys"
    service_keys.mkdir()
    jwt_pem = service_keys / "jwt_rsa_private.pem"
    jwt_pem.write_text("placeholder-rsa-key-material\n", encoding="utf-8")

    # #14124: material written by subsystems other than the secrets manager,
    # under the same data directory -- the two paths the issue names.
    security_dir = data_dir / "security"
    sso_keys_dir = security_dir / "sso_keys"
    sso_keys_dir.mkdir(parents=True)
    sso_private_key = sso_keys_dir / "private_key.pem"
    sso_private_key.write_text("placeholder-sso-signing-key-material\n", encoding="utf-8")

    user_profiles_pkl = security_dir / "user_profiles.pkl"
    # Real content is irrelevant -- the point under test is that the bridge
    # never reads or writes this path at all, regardless of what pickle.load()
    # would do with it.
    user_profiles_pkl.write_bytes(b"placeholder-pickle-stub-bytes")

    ordinary_file = project / "README.md"
    ordinary_file.write_text("hello world\n", encoding="utf-8")

    monkeypatch.setattr(fs_mcp, "ALLOWED_DIRECTORIES", [f"{project}/"])
    monkeypatch.setattr(
        fs_mcp,
        "_EXCLUDED_ROOTS",
        [Path(os.path.realpath(str(data_dir)))],
    )

    return {
        "project": project,
        "data_dir": data_dir,
        "git_config": git_config,
        "env_file": env_file,
        "secrets_key": secrets_key,
        "secrets_json": secrets_json,
        "secrets_db": secrets_db,
        "secrets_db_wal": secrets_db_wal,
        "secrets_db_journal": secrets_db_journal,
        "secrets_json_bak": secrets_json_bak,
        "jwt_pem": jwt_pem,
        "sso_private_key": sso_private_key,
        "user_profiles_pkl": user_profiles_pkl,
        "ordinary_file": ordinary_file,
    }


_EXCLUDED_KEYS = [
    "git_config",
    "env_file",
    "secrets_key",
    "secrets_json",
    "secrets_db",
    "secrets_db_wal",
    "secrets_db_journal",
    "secrets_json_bak",
    "jwt_pem",
    "sso_private_key",
    "user_profiles_pkl",
]


class TestExcludedSubtreesUnit:
    """Unit-level checks at the shared resolution seam."""

    @pytest.mark.parametrize("key", _EXCLUDED_KEYS)
    def test_excluded_path_is_denied(self, fake_project, key):
        """A path under an excluded subtree is refused (#14081/#14124 AC1/AC2/AC3)."""
        target = str(fake_project[key])

        assert fs_mcp.is_path_allowed(target) is False
        with pytest.raises(ValueError, match="excluded subtree"):
            fs_mcp._resolve_allowed_path(target)

    def test_data_directory_itself_is_denied(self, fake_project):
        """The data directory as a whole is refused, not just files under it."""
        assert fs_mcp.is_path_allowed(str(fake_project["data_dir"])) is False

    @pytest.mark.parametrize("key", ["ordinary_file", "project"])
    def test_ordinary_path_still_allowed(self, fake_project, key):
        """Legitimate project files remain reachable (#14081/#14124 AC5)."""
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

    def test_data_lookalike_is_not_prefix_matched(self, fake_project):
        """A sibling directory merely *named* like ``data`` (e.g. ``database/``)
        is unaffected -- guards against a naive substring/startswith check on
        the ``data`` component instead of a proper ``relative_to`` containment
        check.
        """
        lookalike_dir = fake_project["project"] / "database"
        lookalike_dir.mkdir()
        seed = lookalike_dir / "seed.sql"
        seed.write_text("-- seed\n", encoding="utf-8")

        assert fs_mcp.is_path_allowed(str(seed)) is True


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


class TestExcludedSubtreesReadEndpoint:
    """End-to-end reads: an authenticated caller still can't reach excluded paths.

    Covers the issue's exact scenario -- an admin/internal-key caller
    attempting to read secrets-adjacent material through the bridge
    (#14081 AC4, #14124 AC "refused for read and write").
    """

    @pytest.mark.parametrize("key", _EXCLUDED_KEYS)
    def test_read_excluded_path_denied(self, client: TestClient, admin_headers, fake_project, key):
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project[key])},
            headers=admin_headers,
        )
        assert response.status_code == 403, f"{key} was reachable for read through the bridge"

    def test_read_ordinary_file_still_works(self, client: TestClient, admin_headers, fake_project):
        """The bridge is not a blanket outage -- ordinary files still read (#14081/#14124 AC5)."""
        response = client.post(
            "/api/filesystem/mcp/read_text_file",
            json={"path": str(fake_project["ordinary_file"])},
            headers=admin_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["content"] == "hello world\n"


class TestExcludedSubtreesWriteEndpoint:
    """End-to-end writes: the same exclusion holds for the mutating endpoint.

    #14124's acceptance criteria are explicit that write, not just read, must
    be refused -- the sharp finding (a bridge-writable pickle the
    threat-detection engine deserializes) is a write-only exploit.
    """

    @pytest.mark.parametrize("key", _EXCLUDED_KEYS)
    def test_write_excluded_path_denied(self, client: TestClient, admin_headers, fake_project, key):
        response = client.post(
            "/api/filesystem/mcp/write_file",
            json={"path": str(fake_project[key]), "content": "attacker-controlled"},
            headers=admin_headers,
        )
        assert response.status_code == 403, f"{key} was writable through the bridge"

    def test_write_new_file_under_data_directory_denied(self, client: TestClient, admin_headers, fake_project):
        """A *new* path under the data directory is denied too, not just
        pre-existing files -- guards against a check keyed on file identity
        rather than the subtree.
        """
        target = fake_project["data_dir"] / "not_yet_created.pkl"
        response = client.post(
            "/api/filesystem/mcp/write_file",
            json={"path": str(target), "content": "attacker-controlled"},
            headers=admin_headers,
        )
        assert response.status_code == 403
        assert not target.exists()

    def test_write_ordinary_file_still_works(self, client: TestClient, admin_headers, fake_project):
        """The bridge is not a blanket outage for writes either."""
        target = fake_project["project"] / "new_ordinary_file.txt"
        response = client.post(
            "/api/filesystem/mcp/write_file",
            json={"path": str(target), "content": "hello write\n"},
            headers=admin_headers,
        )
        assert response.status_code == 200
        assert target.read_text(encoding="utf-8") == "hello write\n"


class TestRealResolverAgreement:
    """The real data-directory resolvers must land inside the real exclusion.

    #14124: two resolvers name the data directory in this codebase --
    ``ssot_config.config.path.data_path`` (SecretsManager/SecretsService) and
    ``constants.path_constants.PATH.DATA_DIR`` (SSO signing key,
    threat-detection pickle, security policies, tool-output spill). #14110's
    own history is the reason this class of test exists at all: an earlier
    round of that PR derived its exclusion from one resolver while the real
    secrets store wrote through a different one, so the exclusion list
    protected a path nothing ever touched.

    These tests check the real, unmonkeypatched ``fs_mcp.is_path_allowed``
    against what the real resolvers actually compute -- not a hand-picked
    path and not a re-implementation of the check.
    """

    @pytest.fixture(autouse=True)
    def _no_stray_secrets_artifacts(self):
        """Clean up any secrets-store file this test session causes to be
        (re-)provisioned (carried from #14081 review).

        ``SecretsManager.ensure_initialized()`` mints a real encryption key
        the first time it runs if none exists yet -- exercising the real,
        unmocked path-resolution code this class guards requires calling it
        for real. Removes only files that did not exist before this test and
        were created during it -- never touches a real, pre-existing store.
        """
        data_dir = fs_mcp.config.path.data_path
        candidates = [data_dir / "secrets.key", data_dir / "secrets.json", data_dir / "secrets.db"]
        pre_existing = {p for p in candidates if p.exists()}
        yield
        for p in candidates:
            if p.exists() and p not in pre_existing:
                p.unlink()

    def test_ssot_data_path_is_excluded(self):
        assert fs_mcp.is_path_allowed(str(fs_mcp.config.path.data_path)) is False

    def test_legacy_path_constants_data_dir_is_excluded(self):
        assert fs_mcp.is_path_allowed(str(fs_mcp.LEGACY_DATA_ROOT.DATA_DIR)) is False

    def test_sso_signing_key_location_is_excluded(self):
        """The exact path sso_integration.py resolves for its keys directory."""
        sso_keys_dir = fs_mcp.LEGACY_DATA_ROOT.get_data_path("security", "sso_keys")
        assert fs_mcp.is_path_allowed(str(sso_keys_dir / "private_key.pem")) is False

    def test_threat_detection_profile_storage_location_is_excluded(self):
        """The exact path threat_detection/engine.py resolves for its pickle."""
        profile_storage_path = fs_mcp.LEGACY_DATA_ROOT.get_data_path("security", "user_profiles.pkl")
        assert fs_mcp.is_path_allowed(str(profile_storage_path)) is False

    def test_secrets_manager_storage_is_excluded_by_the_real_bridge(self):
        import api.secrets as secrets_api

        # api.secrets provisions a module-level singleton (`secrets_manager`)
        # -- reference it directly rather than constructing a second
        # instance. Construction does not touch disk (#14081 review round 4,
        # #14110): trigger the same one-time initialization the app's
        # startup lifespan runs explicitly, so key_file/secrets_file are
        # populated. Any real key material this mints is removed by the
        # class-level cleanup fixture above.
        manager = secrets_api.secrets_manager
        manager.ensure_initialized()

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
