# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Instance hosts are validated once at config-store time (#13625 item 3).

Rule 8 asks for this here rather than per request: the per-request check costs a
DNS lookup on every call and still races, because the guard resolves and then
aiohttp resolves again independently. Rejecting at store time means an
unreachable-by-policy host never gets persisted in the first place.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

import api.knowledge_connectors as mod


def _cfg(**config):
    class _C:
        def __init__(self, cfg):
            self.config = cfg

    return _C(config)


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["base_url", "gitlab_url", "gitea_url", "nextcloud_url"])
async def test_private_instance_host_is_rejected_when_the_opt_in_is_off(key, monkeypatch):
    """Default posture: a private instance host cannot be stored."""
    monkeypatch.setattr(mod, "_INSTANCE_HOST_KEYS", ("base_url", "gitlab_url", "gitea_url", "nextcloud_url"))
    with pytest.raises(HTTPException) as exc:
        await mod._validate_instance_hosts(_cfg(**{key: "https://10.0.0.5/api"}))
    assert exc.value.status_code == 422
    assert "AUTOBOT_CONNECTOR_PRIVATE_NETWORK_EGRESS" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_private_instance_host_is_accepted_with_the_opt_in(monkeypatch):
    """A self-hosted instance on RFC-1918 is the case the opt-in exists for."""
    import knowledge.connectors.base as base

    monkeypatch.setattr(base, "instance_host_egress", lambda: True)
    await mod._validate_instance_hosts(_cfg(base_url="https://10.0.0.5/api"))


@pytest.mark.asyncio
async def test_cloud_metadata_is_refused_even_with_the_opt_in(monkeypatch):
    """#13625: the opt-in permits RFC-1918 only — never the hard blocks.

    If this ever passes, the opt-in has become an SSRF bypass reachable from
    connector configuration.
    """
    import knowledge.connectors.base as base

    monkeypatch.setattr(base, "instance_host_egress", lambda: True)
    for url in ("http://169.254.169.254/latest/meta-data/", "http://127.0.0.1:8080/x"):
        with pytest.raises(HTTPException) as exc:
            await mod._validate_instance_hosts(_cfg(base_url=url))
        assert exc.value.status_code == 422, url


@pytest.mark.asyncio
async def test_public_host_passes():
    # An IP literal, deliberately: a hostname needs DNS, and the guard fails
    # closed when resolution is unavailable — which would make this test pass or
    # fail on whether the runner has egress rather than on the code.
    await mod._validate_instance_hosts(_cfg(base_url="https://93.184.216.34/wiki"))


@pytest.mark.asyncio
async def test_config_without_an_instance_host_is_untouched():
    """Connectors with no host key (gdrive, slack, notion) must not be blocked."""
    await mod._validate_instance_hosts(_cfg(source_type="mydrive", sync_subfolders=True))
