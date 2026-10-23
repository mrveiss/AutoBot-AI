# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Vendor-API integrations are public-only: an internal or private target is refused (#17576, AC4 slice 4).

Every integration's base URL, webhook URL or tenant region is entered by an operator or user and stored as
integration settings, so none of them is a *server-chosen* URL: ``EGRESS_POLICY`` (which trusts the SSOT
internal origins) would let whoever edits the setting aim the server, with its bearer token, at its own
services. The self-hostable tools (Jenkins, GitLab, CircleCI Server, GitHub, and Jira when the admin router builds it) use ``instance_host_egress()`` --
public, plus RFC-1918 only when ``AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS`` is on; loopback and link-local
(metadata) never. Jira built from a tenant's stored ``pm-config`` (LLC), Bitbucket (Cloud API only) and the
SaaS-only vendors use public-only egress. A real HTTP manager with a
mocked session shows whether a request left; DNS is stubbed.
"""

from __future__ import annotations

import socket
from unittest.mock import AsyncMock, MagicMock

import pytest

from autobot_shared import egress_allowlist as al
from autobot_shared.http_client_manager import HTTPClientManager
from autobot_shared.ssot_config import config as ssot
from integrations import (
    cicd_integration,
    cloud_integration,
    communication_integration,
    github_integration,
    microsoft365_integration,
    monitoring_integration,
    notion_integration,
    project_management_integration,
    version_control_integration,
)
from integrations.base import IntegrationConfig

PUBLIC_URL = "https://vendor.example.test/api"
PUBLIC_IP = "93.184.216.34"
PRIVATE_IP = "10.9.9.9"
INTERNAL_URLS = [
    pytest.param(lambda: ssot.backend_url, id="ssot_backend_origin"),
    pytest.param(lambda: "http://127.0.0.1:8001", id="loopback"),
    pytest.param(lambda: "http://10.1.2.3:8001", id="private"),
    pytest.param(lambda: "http://169.254.169.254", id="metadata"),
]
MODULES = [
    cicd_integration,
    cloud_integration,
    communication_integration,
    github_integration,
    microsoft365_integration,
    monitoring_integration,
    notion_integration,
    project_management_integration,
    version_control_integration,
]


_CRED = "placeholder-not-a-credential"  # pragma: allowlist secret


def _cfg(base_url=None, **extra):
    return IntegrationConfig(
        name="t",
        provider="t",
        base_url=base_url,
        api_key=_CRED,
        api_secret=_CRED,
        token=_CRED,
        username="user",
        password=_CRED,
        extra={"subscription_id": "s", "project_id": "p", "workspace": "w", "domain": "d", **extra},
    )


#: id -> (class, builder from the operator-entered URL to a config). The URL lands where the integration reads it.
BASE_URL_SITES = {
    "jenkins": (cicd_integration.JenkinsIntegration, _cfg),
    "gitlab_ci": (cicd_integration.GitLabCIIntegration, _cfg),
    "circleci": (cicd_integration.CircleCIIntegration, _cfg),
    "gitlab_vcs": (version_control_integration.GitLabIntegration, _cfg),
    "bitbucket": (version_control_integration.BitbucketIntegration, _cfg),
    "slack": (communication_integration.SlackIntegration, _cfg),
    "discord": (communication_integration.DiscordIntegration, _cfg),
    "teams_graph": (communication_integration.TeamsIntegration, _cfg),
    "teams_webhook": (communication_integration.TeamsIntegration, lambda u: _cfg(webhook_url=u)),
    "github": (github_integration.GitHubIntegration, _cfg),
    "microsoft365": (microsoft365_integration.Microsoft365Integration, _cfg),
    "notion": (notion_integration.NotionIntegration, _cfg),
    "jira_tenant": (project_management_integration.JiraIntegration, _cfg),
    "jira_admin": (lambda cfg: project_management_integration.JiraIntegration(cfg, instance_host=True), _cfg),
    "trello": (project_management_integration.TrelloIntegration, _cfg),
    "asana": (project_management_integration.AsanaIntegration, _cfg),
}
#: Hosts fixed in the code (vendor constants): the guard still applies, so DNS answering private refuses them.
FIXED_HOST_SITES = {
    "datadog": monitoring_integration.DatadogIntegration,
    "newrelic": monitoring_integration.NewRelicIntegration,
    "aws": cloud_integration.AWSIntegration,
    "azure": cloud_integration.AzureIntegration,
    "gcp": cloud_integration.GCPIntegration,
}


@pytest.fixture(autouse=True)
def _clean_allowlist():
    al.reset_internal_origin_state()
    yield
    al.reset_internal_origin_state()


@pytest.fixture
def net(monkeypatch):
    """Real manager, mocked session; every integration module reaches the manager through it."""
    resp = MagicMock(status=200, headers={})
    resp.json = AsyncMock(return_value={})
    resp.text = AsyncMock(return_value="<x/>")
    resp.read = AsyncMock(return_value=b"")
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.request = AsyncMock(return_value=resp)
    mgr = HTTPClientManager()
    monkeypatch.setattr(mgr, "get_session", AsyncMock(return_value=session))
    for attr in ("_active_requests", "_request_count", "_error_count"):
        monkeypatch.setattr(mgr, attr, getattr(mgr, attr))
    for module in MODULES:
        monkeypatch.setattr(module, "get_http_client", lambda: mgr)
    monkeypatch.setattr("autobot_shared.http_client.get_http_client", lambda: mgr)
    _resolve_to(monkeypatch, PUBLIC_IP)
    return session


def _resolve_to(monkeypatch, ip):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]
    )


def _sent(session):
    return [c.args[1] for c in session.request.await_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize("make_url", INTERNAL_URLS)
@pytest.mark.parametrize("site", BASE_URL_SITES)
async def test_internal_or_private_target_is_refused_before_any_request(site, make_url, net):
    cls, build = BASE_URL_SITES[site]
    await cls(build(make_url())).test_connection()
    assert _sent(net) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("site", BASE_URL_SITES)
async def test_public_target_is_allowed(site, net):
    cls, build = BASE_URL_SITES[site]
    await cls(build(PUBLIC_URL)).test_connection()
    assert _sent(net) and all(u.startswith("https://") for u in _sent(net))


@pytest.mark.asyncio
@pytest.mark.parametrize("site", FIXED_HOST_SITES)
async def test_fixed_vendor_host_resolving_private_sends_no_request(site, net, monkeypatch):
    _resolve_to(monkeypatch, PRIVATE_IP)
    await FIXED_HOST_SITES[site](_cfg()).test_connection()
    assert _sent(net) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("site", FIXED_HOST_SITES)
async def test_fixed_vendor_host_resolving_public_is_allowed(site, net):
    await FIXED_HOST_SITES[site](_cfg()).test_connection()
    assert _sent(net)


ACTIONS = [
    ("jenkins", "list_jobs", {}),
    ("jenkins", "trigger_build", {"job_name": "j"}),
    ("gitlab_ci", "list_pipelines", {"project_id": "1"}),
    ("gitlab_ci", "trigger_pipeline", {"project_id": "1", "ref": "main"}),
    ("circleci", "list_pipelines", {"project_slug": "gh/o/r"}),
    ("gitlab_vcs", "list_projects", {}),
    ("bitbucket", "list_repositories", {}),
    ("bitbucket", "list_pull_requests", {"repo_slug": "r"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("site,action,params", ACTIONS)
async def test_action_paths_and_kwargs_wrappers_are_guarded_too(site, action, params, net):
    """``get_json``/``post_json`` and the Bitbucket ``**kwargs`` wrapper carry the same guard as the health check."""
    cls, build = BASE_URL_SITES[site]
    with pytest.raises(Exception):
        await cls(build("http://169.254.169.254")).execute_action(action, params)
    assert _sent(net) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["jenkins", "gitlab_ci", "circleci", "gitlab_vcs", "github", "jira_admin"])
async def test_instance_hosts_follow_the_private_network_opt_in_but_never_loopback(site, net, monkeypatch):
    monkeypatch.setattr(ssot.feature, "connector_private_network_egress", True)
    cls, build = BASE_URL_SITES[site]
    await cls(build("http://10.1.2.3:8080")).test_connection()
    assert _sent(net)  # the self-hosted instance on a private address is reachable once opted in
    net.request.reset_mock()
    for url in ("http://127.0.0.1:8001", "http://169.254.169.254"):
        await cls(build(url)).test_connection()
    assert _sent(net) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("site", ["bitbucket", "slack", "discord", "microsoft365", "notion", "trello", "asana"])
async def test_saas_vendors_ignore_the_private_network_opt_in(site, net, monkeypatch):
    monkeypatch.setattr(ssot.feature, "connector_private_network_egress", True)
    cls, build = BASE_URL_SITES[site]
    await cls(build("http://10.1.2.3:8080")).test_connection()
    assert _sent(net) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("make_url", INTERNAL_URLS)
async def test_llc_tenant_jira_url_is_public_only_even_with_the_private_network_opt_in(make_url, net, monkeypatch):
    """The LLC test-connection and outbound-dispatch paths build Jira from a DB-stored, tenant-editable URL."""
    from llc.api.companies import _test_pm_connectivity
    from llc.sync.outbound_sync import _dispatch_to_jira

    monkeypatch.setattr(ssot.feature, "connector_private_network_egress", True)
    pm = {"base_url": make_url(), "username": "u", "api_key": _CRED, "project_key": "P"}
    await _test_pm_connectivity("jira", pm)
    await _dispatch_to_jira(pm, "created", {"title": "t"})
    assert _sent(net) == []


@pytest.mark.asyncio
async def test_llc_tenant_jira_public_url_is_allowed(net):
    from llc.api.companies import _test_pm_connectivity

    await _test_pm_connectivity("jira", {"base_url": PUBLIC_URL, "username": "u", "api_key": _CRED})
    assert _sent(net)


def test_admin_router_builds_jira_with_instance_host_trust_and_llc_does_not():
    import inspect

    from api import integration_project_management as admin
    from llc.api import companies
    from llc.sync import outbound_sync

    assert "instance_host=True" in inspect.getsource(admin._get_integration)
    for fn in (companies._test_pm_connectivity, outbound_sync._dispatch_to_jira):
        assert "instance_host" not in inspect.getsource(fn)
