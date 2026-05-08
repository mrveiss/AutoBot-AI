# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for the Marketplace Catalog API (Issue #4521 / #1803)

Covers:
- GET /catalog — listing with category/search/sort
- GET /catalog/{plugin_name} — single entry retrieval
- GET /categories — valid categories and sort options
- GET /installed — list installed plugins
- POST /install — install a plugin (validates existence, bumps download, records in set)
- DELETE /install/{plugin_name} — uninstall a plugin
- Error cases: invalid category, invalid sort_by, not found, Redis failure fallback
- Built-in seed data: correctness of _BUILTIN_CATALOG entries and _plugin_source_url helper
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api.marketplace import (
    InstallRequest,
    MarketplaceCatalogResponse,
    MarketplaceEntry,
    _BUILTIN_CATALOG,
    _CATALOG_KEY,
    _CATALOG_TTL,
    _INSTALLED_KEY,
    _VALID_CATEGORIES,
    _VALID_SORT,
    _get_catalog,
    _plugin_source_url,
    get_catalog_entry,
    install_plugin,
    list_catalog,
    list_categories,
    list_installed,
    uninstall_plugin,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis(catalog: list | None = None, installed: set | None = None) -> AsyncMock:
    """Return an AsyncMock Redis client pre-configured with catalog/installed data."""
    redis = AsyncMock()
    if catalog is not None:
        redis.get.return_value = json.dumps(catalog).encode()
    else:
        redis.get.return_value = None
    members = {m.encode() for m in (installed or set())}
    redis.smembers.return_value = members
    redis.set.return_value = True
    redis.sadd.return_value = 1
    redis.srem.return_value = 1
    return redis


# ---------------------------------------------------------------------------
# _plugin_source_url
# ---------------------------------------------------------------------------


class TestPluginSourceUrl:
    def test_returns_string(self):
        url = _plugin_source_url("hello-plugin")
        assert isinstance(url, str)

    def test_contains_slug(self):
        url = _plugin_source_url("my-slug")
        assert "my-slug" in url

    def test_contains_github(self):
        url = _plugin_source_url("test")
        assert "github.com" in url or "http" in url

    def test_different_slugs_differ(self):
        assert _plugin_source_url("a") != _plugin_source_url("b")


# ---------------------------------------------------------------------------
# _BUILTIN_CATALOG seed data integrity
# ---------------------------------------------------------------------------


class TestBuiltinCatalog:
    """Validate the hardcoded seed entries are well-formed."""

    def test_catalog_not_empty(self):
        assert len(_BUILTIN_CATALOG) > 0

    def test_all_entries_have_required_fields(self):
        required = {
            "name", "version", "display_name", "description",
            "author", "category", "entry_point",
        }
        for entry in _BUILTIN_CATALOG:
            missing = required - entry.keys()
            assert not missing, f"Entry '{entry.get('name')}' missing fields: {missing}"

    def test_all_categories_are_valid(self):
        valid = _VALID_CATEGORIES - {"all"}
        for entry in _BUILTIN_CATALOG:
            assert entry["category"] in valid, (
                f"Entry '{entry['name']}' has unknown category '{entry['category']}'"
            )

    def test_all_names_unique(self):
        names = [e["name"] for e in _BUILTIN_CATALOG]
        assert len(names) == len(set(names)), "Duplicate plugin names in _BUILTIN_CATALOG"

    def test_downloads_non_negative(self):
        for entry in _BUILTIN_CATALOG:
            assert entry.get("downloads", 0) >= 0

    def test_rating_in_range(self):
        for entry in _BUILTIN_CATALOG:
            rating = entry.get("rating", 0.0)
            assert 0.0 <= rating <= 5.0, f"Rating {rating} out of [0, 5] for '{entry['name']}'"

    def test_source_url_not_empty(self):
        for entry in _BUILTIN_CATALOG:
            assert entry.get("source_url"), f"Empty source_url for '{entry['name']}'"

    def test_entry_is_valid_marketplace_entry(self):
        """All built-in entries must be parseable as MarketplaceEntry."""
        for raw in _BUILTIN_CATALOG:
            entry = MarketplaceEntry(**raw)
            assert entry.name == raw["name"]


# ---------------------------------------------------------------------------
# _get_catalog
# ---------------------------------------------------------------------------


class TestGetCatalog:
    @pytest.mark.asyncio
    async def test_returns_redis_data_when_cached(self):
        catalog_data = [{"name": "cached-plugin", "version": "1.0.0"}]
        redis = _make_redis(catalog=catalog_data)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await _get_catalog()
        assert result == catalog_data

    @pytest.mark.asyncio
    async def test_falls_back_to_builtin_when_cache_empty(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await _get_catalog()
        assert result == _BUILTIN_CATALOG

    @pytest.mark.asyncio
    async def test_seeds_redis_when_cache_empty(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            await _get_catalog()
        redis.set.assert_awaited_once()
        call_args = redis.set.call_args
        assert call_args[0][0] == _CATALOG_KEY
        assert call_args[1]["ex"] == _CATALOG_TTL

    @pytest.mark.asyncio
    async def test_falls_back_to_builtin_on_redis_error(self):
        redis = AsyncMock()
        redis.get.side_effect = ConnectionError("Redis down")
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await _get_catalog()
        assert result == _BUILTIN_CATALOG


# ---------------------------------------------------------------------------
# GET /catalog — list_catalog
# ---------------------------------------------------------------------------


class TestListCatalog:
    @pytest.mark.asyncio
    async def test_returns_all_entries_for_all_category(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search=None, sort_by="downloads")
        assert isinstance(resp, MarketplaceCatalogResponse)
        assert resp.total == len(_BUILTIN_CATALOG)
        assert resp.category == "all"
        assert resp.sort_by == "downloads"

    @pytest.mark.asyncio
    async def test_filters_by_category(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="observability", search=None, sort_by="name")
        for entry in resp.entries:
            assert entry.category == "observability"

    @pytest.mark.asyncio
    async def test_full_text_search_by_name(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search="logger", sort_by="name")
        assert resp.total >= 1
        assert any("logger" in e.name.lower() for e in resp.entries)

    @pytest.mark.asyncio
    async def test_full_text_search_by_description(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search="telemetry", sort_by="downloads")
        assert resp.total >= 1

    @pytest.mark.asyncio
    async def test_full_text_search_by_tag(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search="mcp", sort_by="name")
        assert resp.total >= 1

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search="xyznonexistent", sort_by="name")
        assert resp.total == 0
        assert resp.entries == []

    @pytest.mark.asyncio
    async def test_sort_by_downloads_descending(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search=None, sort_by="downloads")
        downloads = [e.downloads for e in resp.entries]
        assert downloads == sorted(downloads, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_rating_descending(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search=None, sort_by="rating")
        ratings = [e.rating for e in resp.entries]
        assert ratings == sorted(ratings, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_name_ascending(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search=None, sort_by="name")
        names = [e.name.lower() for e in resp.entries]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_invalid_category_raises_400(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await list_catalog(category="garbage", search=None, sort_by="downloads")
        assert exc_info.value.status_code == 400
        assert "Invalid category" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_invalid_sort_raises_400(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await list_catalog(category="all", search=None, sort_by="badfield")
        assert exc_info.value.status_code == 400
        assert "Invalid sort_by" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_total_matches_entry_count(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(category="all", search=None, sort_by="name")
        assert resp.total == len(resp.entries)


# ---------------------------------------------------------------------------
# GET /catalog/{plugin_name} — get_catalog_entry
# ---------------------------------------------------------------------------


class TestGetCatalogEntry:
    @pytest.mark.asyncio
    async def test_returns_known_entry(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            entry = await get_catalog_entry("hello-plugin")
        assert isinstance(entry, MarketplaceEntry)
        assert entry.name == "hello-plugin"

    @pytest.mark.asyncio
    async def test_raises_404_for_unknown(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await get_catalog_entry("no-such-plugin")
        assert exc_info.value.status_code == 404
        assert "no-such-plugin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_returns_entry_from_redis_cache(self):
        custom_catalog = [
            {
                "name": "custom-plugin",
                "version": "2.0.0",
                "display_name": "Custom",
                "description": "Custom plugin",
                "author": "mrveiss",
                "category": "tool",
                "tags": ["custom"],
                "entry_point": "plugins.custom",
                "dependencies": [],
                "hooks": [],
                "downloads": 10,
                "rating": 3.0,
                "source_url": "https://example.com",
            }
        ]
        redis = _make_redis(catalog=custom_catalog)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            entry = await get_catalog_entry("custom-plugin")
        assert entry.name == "custom-plugin"
        assert entry.version == "2.0.0"


# ---------------------------------------------------------------------------
# GET /categories — list_categories
# ---------------------------------------------------------------------------


class TestListCategories:
    @pytest.mark.asyncio
    async def test_returns_categories_and_sort_options(self):
        result = await list_categories()
        assert "categories" in result
        assert "sort_options" in result

    @pytest.mark.asyncio
    async def test_categories_sorted(self):
        result = await list_categories()
        assert result["categories"] == sorted(result["categories"])

    @pytest.mark.asyncio
    async def test_sort_options_sorted(self):
        result = await list_categories()
        assert result["sort_options"] == sorted(result["sort_options"])

    @pytest.mark.asyncio
    async def test_all_valid_categories_present(self):
        result = await list_categories()
        assert set(result["categories"]) == _VALID_CATEGORIES

    @pytest.mark.asyncio
    async def test_all_valid_sort_options_present(self):
        result = await list_categories()
        assert set(result["sort_options"]) == _VALID_SORT


# ---------------------------------------------------------------------------
# GET /installed — list_installed
# ---------------------------------------------------------------------------


class TestListInstalled:
    @pytest.mark.asyncio
    async def test_empty_when_none_installed(self):
        redis = _make_redis(installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await list_installed()
        assert result == {"installed": []}

    @pytest.mark.asyncio
    async def test_returns_sorted_installed_list(self):
        redis = _make_redis(installed={"logger-plugin", "hello-plugin"})
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await list_installed()
        assert result["installed"] == sorted(["hello-plugin", "logger-plugin"])

    @pytest.mark.asyncio
    async def test_returns_empty_on_redis_error(self):
        redis = AsyncMock()
        redis.smembers.side_effect = ConnectionError("Redis down")
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await list_installed()
        assert result == {"installed": []}


# ---------------------------------------------------------------------------
# POST /install — install_plugin
# ---------------------------------------------------------------------------


class TestInstallPlugin:
    @pytest.mark.asyncio
    async def test_installs_known_plugin(self):
        redis = _make_redis(catalog=None, installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await install_plugin(InstallRequest(plugin_name="hello-plugin"))
        assert result == {"status": "installed", "plugin": "hello-plugin"}

    @pytest.mark.asyncio
    async def test_sadd_called_with_plugin_name(self):
        redis = _make_redis(catalog=None, installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            await install_plugin(InstallRequest(plugin_name="logger-plugin"))
        redis.sadd.assert_awaited_once_with(_INSTALLED_KEY, "logger-plugin")

    @pytest.mark.asyncio
    async def test_download_counter_incremented(self):
        redis = _make_redis(catalog=None, installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            await install_plugin(InstallRequest(plugin_name="logger-plugin"))
        # The updated catalog is serialised and stored back via redis.set
        redis.set.assert_awaited()
        # Decode the stored catalog and verify downloads incremented
        call_args = redis.set.call_args
        stored_raw = call_args[0][1]
        stored_catalog = json.loads(stored_raw)
        plugin = next(e for e in stored_catalog if e["name"] == "logger-plugin")
        original = next(e for e in _BUILTIN_CATALOG if e["name"] == "logger-plugin")
        assert plugin["downloads"] == original["downloads"] + 1

    @pytest.mark.asyncio
    async def test_raises_404_for_unknown_plugin(self):
        redis = _make_redis(catalog=None, installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await install_plugin(InstallRequest(plugin_name="ghost-plugin"))
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_raises_500_on_redis_write_error(self):
        redis = AsyncMock()
        # First call (get_catalog): returns nothing → fallback to builtin
        redis.get.return_value = None
        redis.set.return_value = True  # seed succeeds
        # Second client call for sadd → fails
        redis.sadd.side_effect = ConnectionError("Redis down")
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await install_plugin(InstallRequest(plugin_name="hello-plugin"))
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# DELETE /install/{plugin_name} — uninstall_plugin
# ---------------------------------------------------------------------------


class TestUninstallPlugin:
    @pytest.mark.asyncio
    async def test_uninstalls_installed_plugin(self):
        redis = _make_redis(installed={"hello-plugin"})
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await uninstall_plugin("hello-plugin")
        assert result == {"status": "uninstalled", "plugin": "hello-plugin"}

    @pytest.mark.asyncio
    async def test_srem_called_with_plugin_name(self):
        redis = _make_redis(installed={"hello-plugin"})
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            await uninstall_plugin("hello-plugin")
        redis.srem.assert_awaited_once_with(_INSTALLED_KEY, "hello-plugin")

    @pytest.mark.asyncio
    async def test_raises_404_when_not_installed(self):
        redis = _make_redis(installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await uninstall_plugin("hello-plugin")
        assert exc_info.value.status_code == 404
        assert "hello-plugin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_raises_500_on_redis_srem_error(self):
        redis = AsyncMock()
        redis.smembers.return_value = {b"hello-plugin"}
        redis.srem.side_effect = ConnectionError("Redis down")
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await uninstall_plugin("hello-plugin")
        assert exc_info.value.status_code == 500
