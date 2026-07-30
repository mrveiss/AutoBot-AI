# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Guard tests for Issue #12221: connector credential keys must match auth_schema().

Two layers:
  1. Structural guard — for every real (network-backed) KB enterprise connector,
     assert the private attributes it reads from ``ConnectorConfig.config`` map
     1:1 onto the field names its own ``auth_schema()`` declares, so a
     schema-valid request can never leave the connector's real credential
     unset (the original #12221 bug).
  2. End-to-end guard — drive the real ``POST /knowledge_base/connectors``
     handler with ONLY auth_schema-declared credential keys, through the real
     ``ConnectorCredentialStore`` (encrypt -> sanitize -> persist -> decrypt ->
     merge) backed by an in-memory fake secrets backend, and assert the
     decrypted value that reaches the outbound HTTP call is the exact
     credential supplied — proving authentication actually works end-to-end
     without any network access (aiohttp is fully replaced).
"""

import dataclasses
from unittest.mock import patch

import pytest

import knowledge.connectors.confluence  # noqa: F401 — register confluence
import knowledge.connectors.jira  # noqa: F401 — register jira
import knowledge.connectors.slack  # noqa: F401 — register slack
from api import knowledge_connectors as mod
from knowledge.connectors.confluence import ConfluenceConnector
from knowledge.connectors.credential_store import ConnectorCredentialStore
from knowledge.connectors.jira import JiraConnector
from knowledge.connectors.models import ConnectorConfig
from knowledge.connectors.registry import ConnectorRegistry
from knowledge.connectors.slack import SlackConnector
from knowledge.schemas.connectors import CreateConnectorRequest

# ---------------------------------------------------------------------------
# Structural guard: connector-read attrs <-> auth_schema() declared fields
# ---------------------------------------------------------------------------

# Maps each real connector class to {auth_schema field name: private attr it
# must populate}. Kept explicit (not derived) so a future rename of either
# side makes this test fail loudly instead of silently agreeing with itself.
_CONNECTOR_AUTH_ATTR_MAP = {
    SlackConnector: {"token": "_token"},
    ConfluenceConnector: {"username": "_email", "password": "_api_token"},
    JiraConnector: {"username": "_email", "password": "_api_token"},
}

_NON_AUTH_CONFIG = {
    SlackConnector: {"channel_ids": ["C1"]},
    ConfluenceConnector: {"base_url": "https://x.atlassian.net/wiki", "space_keys": ["ENG"]},
    JiraConnector: {"base_url": "https://x.atlassian.net", "project_keys": ["ABC"]},
}


@pytest.mark.parametrize("connector_cls", [SlackConnector, ConfluenceConnector, JiraConnector])
def test_connector_reads_declared_auth_schema_keys(connector_cls):
    """Guard against #12221 regressing: connector reads == auth_schema() keys.

    Builds a config containing ONLY the auth_schema()-declared field names
    (plus the connector's required non-auth config) and asserts every
    declared field lands on the attribute the connector's outbound HTTP
    calls actually use.
    """
    auth_cls = connector_cls.auth_schema()
    declared_fields = {f.name for f in dataclasses.fields(auth_cls)}
    attr_map = _CONNECTOR_AUTH_ATTR_MAP[connector_cls]

    assert declared_fields == set(attr_map), (
        "%s auth_schema() fields %s no longer match the expected credential "
        "keys %s — the connector's __init__ and its auth_schema() have "
        "drifted apart again (Issue #12221)." % (connector_cls.__name__, declared_fields, set(attr_map))
    )

    config = dict(_NON_AUTH_CONFIG[connector_cls])
    for field_name in declared_fields:
        config[field_name] = "value-for-%s" % field_name

    cfg = ConnectorConfig(
        connector_id="guard-1",
        connector_type=connector_cls.connector_type,
        name="Guard",
        config=config,
    )
    connector = connector_cls(cfg)
    for field_name, attr_name in attr_map.items():
        assert getattr(connector, attr_name) == "value-for-%s" % field_name


# ---------------------------------------------------------------------------
# End-to-end guard: create() -> encrypt -> decrypt -> real authenticated call
# ---------------------------------------------------------------------------

# Placeholder credential values only — never real tokens (Issue #12221 tests).
_FAKE_BOT_CREDENTIAL = "test-fake-bot-credential"
_FAKE_API_CREDENTIAL = "test-fake-api-credential"
_FAKE_USERNAME = "bot@example.com"


class _FakeSecretsService:
    """In-memory stand-in for SecretsService — no SQLite, no encryption keys."""

    def __init__(self) -> None:
        self._by_id: dict = {}
        self._next_id = 0

    def create_secret(self, name, secret_type, value, scope="general", created_by=None, **_kwargs):
        self._next_id += 1
        secret_id = "fake-secret-%d" % self._next_id
        self._by_id[secret_id] = {"value": value, "created_by": created_by}
        return {"id": secret_id}

    def get_secret(self, secret_id=None, include_value=True, accessed_by=None, **_kwargs):
        return self._by_id.get(secret_id)


class _FakeAsyncResponse:
    """Minimal async-context-manager response compatible with aiohttp usage."""

    def __init__(self, status: int, body: dict) -> None:
        self.status = status
        self._body = body

    async def json(self, content_type=None):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class _FakeHttpClient:
    """Replaces the shared pooled client — records auth material, never dials out.

    Issue #12979 moved these connectors off per-request ``aiohttp.ClientSession``
    onto ``autobot_shared.http_client``. The seam is now
    ``get_http_client().tracked_request(method, url, **kwargs)``, which yields the
    response, so the stub only needs that one entry point instead of the previous
    per-verb ``get``/``post``/``request`` trio.
    """

    def __init__(self, capture: dict, body: dict, status: int = 200) -> None:
        self._capture = capture
        self._body = body
        self._status = status

    def tracked_request(self, method, url, headers=None, auth=None, **kwargs):
        self._capture["method"] = method
        self._capture["headers"] = headers
        self._capture["auth"] = auth
        return _FakeAsyncResponse(self._status, self._body)


async def _create_via_api(request: CreateConnectorRequest, http_client_patch_target: str, fake_client):
    """Drive the real create_connector() handler with a stubbed secrets backend."""
    store = ConnectorCredentialStore(_FakeSecretsService())
    saved = {}

    async def _fake_save(cfg):
        saved["cfg"] = cfg

    with (
        patch.object(mod, "get_credential_store", return_value=store),
        patch.object(mod, "_save_connector", _fake_save),
        patch(http_client_patch_target, return_value=fake_client),
    ):
        result = await mod.create_connector(request)
    return result, saved["cfg"]


@pytest.mark.asyncio
async def test_create_slack_schema_valid_credentials_authenticate():
    """A #12221-compliant Slack request round-trips the token through auth.test."""
    capture: dict = {}
    fake_client = _FakeHttpClient(capture, {"ok": True}, 200)
    req = CreateConnectorRequest(
        connector_type="slack",
        name="Guard Slack",
        config={"token": _FAKE_BOT_CREDENTIAL, "channel_ids": ["C1"]},
    )
    try:
        result, cfg = await _create_via_api(req, "knowledge.connectors.slack.get_http_client", fake_client)
        assert result["connector_id"] == cfg.connector_id
        assert capture["headers"]["Authorization"] == "Bearer %s" % _FAKE_BOT_CREDENTIAL
        # The credential is encrypted at rest — never echoed in the public config.
        assert "token" not in result["config"]
    finally:
        ConnectorRegistry.remove_instance(cfg.connector_id)


@pytest.mark.asyncio
async def test_create_confluence_schema_valid_credentials_authenticate():
    """A #12221-compliant Confluence request authenticates via BasicAuth(username, password)."""
    capture: dict = {}
    fake_client = _FakeHttpClient(capture, {"results": []}, 200)
    req = CreateConnectorRequest(
        connector_type="confluence",
        name="Guard Confluence",
        config={
            "base_url": "https://guard.atlassian.net/wiki",
            "username": _FAKE_USERNAME,
            "password": _FAKE_API_CREDENTIAL,
            "space_keys": ["ENG"],
        },
    )
    try:
        result, cfg = await _create_via_api(req, "knowledge.connectors.confluence.get_http_client", fake_client)
        assert result["connector_id"] == cfg.connector_id
        assert capture["auth"].login == _FAKE_USERNAME
        assert capture["auth"].password == _FAKE_API_CREDENTIAL
        assert "password" not in result["config"]
    finally:
        ConnectorRegistry.remove_instance(cfg.connector_id)


@pytest.mark.asyncio
async def test_create_jira_schema_valid_credentials_authenticate():
    """A #12221-compliant Jira request authenticates via BasicAuth(username, password)."""
    capture: dict = {}
    fake_client = _FakeHttpClient(capture, {"accountId": "u1"}, 200)
    req = CreateConnectorRequest(
        connector_type="jira",
        name="Guard Jira",
        config={
            "base_url": "https://guard.atlassian.net",
            "username": _FAKE_USERNAME,
            "password": _FAKE_API_CREDENTIAL,
            "project_keys": ["ABC"],
        },
    )
    try:
        result, cfg = await _create_via_api(req, "knowledge.connectors.jira.get_http_client", fake_client)
        assert result["connector_id"] == cfg.connector_id
        assert capture["auth"].login == _FAKE_USERNAME
        assert capture["auth"].password == _FAKE_API_CREDENTIAL
        assert "password" not in result["config"]
    finally:
        ConnectorRegistry.remove_instance(cfg.connector_id)
