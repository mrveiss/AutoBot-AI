# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#6524: regression tests for source-aware install + detail endpoints.

Pin the fix: ``install_plugin`` and ``get_catalog_entry`` must resolve
against the same catalog the user was browsing — they were both hard-wired
to the built-in catalog via ``_get_catalog()``, which made every install
from a user-added marketplace 404.
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest


def test_install_request_has_source_id_field():
    """``InstallRequest`` must accept ``source_id`` so the API can route
    the install to the correct catalog.

    Default = ``BUILTIN_SOURCE_ID`` so existing builtin-only callers don't
    break — opt-in for custom-marketplace installs.
    """
    from api.schemas_workflows import InstallRequest

    fields = InstallRequest.model_fields
    assert (
        "source_id" in fields
    ), "#6524: InstallRequest.source_id missing — install endpoint cannot route to custom catalogs"
    # Default ensures backward compat: a body with only `plugin_name` still
    # validates and resolves against the built-in catalog.
    default = fields["source_id"].default
    assert default == "builtin", f"Expected builtin default; got {default!r}"


def test_resolve_catalog_helper_exists():
    """The shared resolver must exist so list/detail/install all share
    the same source-routing logic — preventing future drift like the
    original #6524 split-brain (list source-aware; install was not).
    """
    from api import marketplace as mod

    assert hasattr(mod, "_resolve_catalog"), "#6524: shared `_resolve_catalog` helper missing"
    assert inspect.iscoroutinefunction(mod._resolve_catalog), "_resolve_catalog must be async"


def test_get_catalog_entry_takes_source_id_query_param():
    """Detail endpoint must accept ``?source_id=`` so deep-links from a
    custom marketplace catalog work.
    """
    from api.marketplace import get_catalog_entry

    sig = inspect.signature(get_catalog_entry)
    assert "source_id" in sig.parameters, "#6524: get_catalog_entry must accept source_id Query param"


def test_install_plugin_takes_install_request_body():
    """``install_plugin`` body type must be ``InstallRequest`` so the new
    ``source_id`` field arrives. Pin against accidental signature drift
    (e.g. someone replacing it with a plain dict body).
    """
    from api.marketplace import install_plugin
    from api.schemas_workflows import InstallRequest

    sig = inspect.signature(install_plugin)
    body_param = sig.parameters.get("body")
    assert body_param is not None, "#6524: install_plugin must keep `body` parameter"
    assert (
        body_param.annotation is InstallRequest
    ), f"#6524: body annotation must be InstallRequest; got {body_param.annotation!r}"


class TestSourceRoutingIsObservedNotGrepped:
    """The bug shape was ``catalog = await _get_catalog()`` inside
    ``install_plugin`` (and ``get_catalog_entry``) — a flat call against the
    built-in catalog regardless of which marketplace the user was browsing.

    These used to assert ``"_resolve_catalog" in inspect.getsource(...)``,
    which proves nothing (#13311): the literal passes from a dead branch and
    fails on any behaviour-preserving refactor. Instead, stub the *seam* the
    routing goes through and observe which catalog the endpoint actually
    consulted, and with which source_id.
    """

    CUSTOM_SOURCE = "11111111-2222-3333-4444-555555555555"
    CUSTOM_ENTRY = {
        "name": "custom-only-plugin",
        "display_name": "Custom Only Plugin",
        "description": "Present ONLY in the user-added catalog",
        "category": "automation",
        "version": "1.0.0",
        "author": "someone",
        "entry_point": "custom_only_plugin:main",
    }

    @pytest.fixture
    def routed(self, monkeypatch):
        """Record every source_id ``_resolve_catalog`` is asked for.

        ``_get_catalog`` (the built-in-only accessor that caused #6524) is
        replaced by an exploding stub: if the endpoint bypasses routing and
        reaches for the built-in catalog directly, the test fails loudly
        instead of quietly returning the wrong catalog.
        """
        from api import marketplace as mod

        asked: list[str] = []

        async def _resolve(source_id):
            asked.append(source_id)
            if source_id == mod.BUILTIN_SOURCE_ID:
                return []
            return [dict(self.CUSTOM_ENTRY)]

        async def _explode():
            raise AssertionError("#6524 regression: endpoint bypassed source routing and called _get_catalog()")

        monkeypatch.setattr(mod, "_resolve_catalog", _resolve)
        monkeypatch.setattr(mod, "_get_catalog", _explode)
        return asked

    @pytest.mark.asyncio
    async def test_install_resolves_against_the_browsed_source(self, routed):
        """An install from a user-added marketplace must succeed — this is the
        headline #6524 symptom (every such install 404'd)."""
        from api.marketplace import install_plugin
        from api.schemas_workflows import InstallRequest

        redis = AsyncMock()
        with patch("api.marketplace.get_async_redis_client", AsyncMock(return_value=redis)):
            result = await install_plugin(
                body=InstallRequest(plugin_name=self.CUSTOM_ENTRY["name"], source_id=self.CUSTOM_SOURCE),
                user={"id": "u1"},
            )

        assert routed == [self.CUSTOM_SOURCE], f"install routed to {routed}, not the browsed source"
        assert result["status"] == "installed"

    @pytest.mark.asyncio
    async def test_install_from_a_source_that_lacks_the_plugin_still_404s(self, routed):
        """The mirror: routing must not become 'try every catalog'.

        ``InstallRequest.source_id`` is a Pydantic default, so an omitted body
        field really does arrive as the built-in source id here.
        """
        from fastapi import HTTPException

        from api.marketplace import install_plugin
        from api.schemas_workflows import InstallRequest

        with pytest.raises(HTTPException) as exc_info:
            await install_plugin(
                body=InstallRequest(plugin_name=self.CUSTOM_ENTRY["name"]),
                user={"id": "u1"},
            )

        assert exc_info.value.status_code == 404
        assert routed == ["builtin"]

    @pytest.mark.asyncio
    async def test_detail_endpoint_resolves_against_the_browsed_source(self, routed):
        """Deep-linking into a custom marketplace entry must resolve (#6524)."""
        from api.marketplace import get_catalog_entry

        entry = await get_catalog_entry(
            plugin_name=self.CUSTOM_ENTRY["name"],
            source_id=self.CUSTOM_SOURCE,
            user={"id": "u1"},
        )

        assert routed == [self.CUSTOM_SOURCE]
        assert entry.name == self.CUSTOM_ENTRY["name"]

    @pytest.mark.asyncio
    async def test_detail_endpoint_declared_default_routes_to_the_builtin_source(self, routed):
        """Backward compat: an omitted ``?source_id=`` must still mean built-in.

        The declared ``Query`` default is read and then *passed through the
        endpoint*, because a direct call bypasses FastAPI's parameter
        resolution — omitting the argument would hand the body a ``Query``
        object and prove nothing.
        """
        from fastapi import HTTPException

        from api.marketplace import BUILTIN_SOURCE_ID, get_catalog_entry

        declared_default = inspect.signature(get_catalog_entry).parameters["source_id"].default.default
        assert declared_default == BUILTIN_SOURCE_ID

        with pytest.raises(HTTPException) as exc_info:
            await get_catalog_entry(
                plugin_name=self.CUSTOM_ENTRY["name"],
                source_id=declared_default,
                user={"id": "u1"},
            )

        assert exc_info.value.status_code == 404
        assert routed == [BUILTIN_SOURCE_ID]
