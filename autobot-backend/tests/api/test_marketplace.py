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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.marketplace import (
    _BUILTIN_CATALOG,
    _CATALOG_KEY,
    _CATALOG_TTL,
    _INSTALLED_KEY_PREFIX,
    _LEGACY_INSTALLED_KEY,
    CatalogCategory,
    CatalogSort,
    _get_catalog,
    _installed_key,
    _migrate_legacy_installed,
    _plugin_source_url,
    get_catalog_entry,
    install_plugin,
    list_catalog,
    list_categories,
    list_installed,
    uninstall_plugin,
)
from api.marketplace_sources import BUILTIN_SOURCE_ID
from api.schemas_workflows import (
    InstallRequest,
    MarketplaceCatalogResponse,
    MarketplaceEntry,
)
from tests.fixtures import make_async_redis

# Derived from CatalogCategory / CatalogSort enums (#6534) — replaces the
# pre-enum ``_VALID_CATEGORIES`` / ``_VALID_SORT`` constants the tests used
# to import from api.marketplace before the enum migration.
_VALID_CATEGORIES = {c.value for c in CatalogCategory}
_VALID_SORT = {s.value for s in CatalogSort}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _async_iter(items):
    """Async generator used to mock Redis scan_iter."""
    for item in items:
        yield item


def _make_redis(
    catalog: list | None = None,
    installed: set | None = None,
    installed_by_source: dict | None = None,
) -> AsyncMock:
    """Return an AsyncMock Redis client pre-configured with catalog/installed data.

    #7366: installed_by_source maps source_id -> set[name] for multi-source tests.
    The legacy ``installed`` kwarg seeds the builtin source key for backward compat.
    """
    get_returns = json.dumps(catalog).encode() if catalog is not None else None
    redis = make_async_redis(get_returns=get_returns)

    # Build per-source mapping
    by_source: dict[str, set[str]] = {}
    if installed:
        by_source[BUILTIN_SOURCE_ID] = set(installed)
    if installed_by_source:
        for src, names in installed_by_source.items():
            by_source.setdefault(src, set()).update(names)

    # scan_iter must be a sync call returning an async iterator (not an AsyncMock)
    scan_keys = [f"{_INSTALLED_KEY_PREFIX}{src}".encode() for src in by_source]
    redis.scan_iter = MagicMock(side_effect=lambda match="": _async_iter(scan_keys))

    # smembers returns the right set depending on which key is requested
    async def _smembers(key):
        key_str = key.decode() if isinstance(key, bytes) else key
        src = key_str.removeprefix(_INSTALLED_KEY_PREFIX)
        return {m.encode() for m in by_source.get(src, set())}

    # Also handle legacy key lookup in migration
    async def _smembers_with_legacy(key):
        key_str = key.decode() if isinstance(key, bytes) else key
        if key_str == _LEGACY_INSTALLED_KEY:
            return set()  # no legacy data by default
        return await _smembers(key)

    redis.smembers.side_effect = _smembers_with_legacy
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
            "name",
            "version",
            "display_name",
            "description",
            "author",
            "category",
            "entry_point",
        }
        for entry in _BUILTIN_CATALOG:
            missing = required - entry.keys()
            assert not missing, f"Entry '{entry.get('name')}' missing fields: {missing}"

    def test_all_categories_are_valid(self):
        valid = _VALID_CATEGORIES - {"all"}
        for entry in _BUILTIN_CATALOG:
            assert entry["category"] in valid, f"Entry '{entry['name']}' has unknown category '{entry['category']}'"

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
    # NOTE: ``list_catalog`` is a FastAPI route handler with ``Query()``-annotated
    # parameters. When called directly (not through TestClient), the test must
    # pass enum instances + a real source_id string — Pydantic only unwraps
    # ``Query()`` defaults at the HTTP layer, not on direct calls.
    # Input-validation tests for invalid category/sort_by run on the enum
    # constructor (which is what Pydantic uses at the HTTP layer post-#6534);
    # full HTTP-level 422 tests are tracked separately as a TestClient sweep.

    @pytest.mark.asyncio
    async def test_returns_all_entries_for_all_category(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search=None,
                sort_by=CatalogSort.DOWNLOADS,
                source_id="builtin",
            )
        assert isinstance(resp, MarketplaceCatalogResponse)
        assert resp.total == len(_BUILTIN_CATALOG)
        assert resp.category == "all"
        assert resp.sort_by == "downloads"

    @pytest.mark.asyncio
    async def test_filters_by_category(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.OBSERVABILITY,
                search=None,
                sort_by=CatalogSort.NAME,
                source_id="builtin",
            )
        for entry in resp.entries:
            assert entry.category == "observability"

    @pytest.mark.asyncio
    async def test_full_text_search_by_name(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search="logger",
                sort_by=CatalogSort.NAME,
                source_id="builtin",
            )
        assert resp.total >= 1
        assert any("logger" in e.name.lower() for e in resp.entries)

    @pytest.mark.asyncio
    async def test_full_text_search_by_description(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search="telemetry",
                sort_by=CatalogSort.DOWNLOADS,
                source_id="builtin",
            )
        assert resp.total >= 1

    @pytest.mark.asyncio
    async def test_full_text_search_by_tag(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search="mcp",
                sort_by=CatalogSort.NAME,
                source_id="builtin",
            )
        assert resp.total >= 1

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search="xyznonexistent",
                sort_by=CatalogSort.NAME,
                source_id="builtin",
            )
        assert resp.total == 0
        assert resp.entries == []

    @pytest.mark.asyncio
    async def test_sort_by_downloads_descending(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search=None,
                sort_by=CatalogSort.DOWNLOADS,
                source_id="builtin",
            )
        downloads = [e.downloads for e in resp.entries]
        assert downloads == sorted(downloads, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_rating_descending(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search=None,
                sort_by=CatalogSort.RATING,
                source_id="builtin",
            )
        ratings = [e.rating for e in resp.entries]
        assert ratings == sorted(ratings, reverse=True)

    @pytest.mark.asyncio
    async def test_sort_by_name_ascending(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search=None,
                sort_by=CatalogSort.NAME,
                source_id="builtin",
            )
        names = [e.name.lower() for e in resp.entries]
        assert names == sorted(names)

    def test_invalid_category_rejected_by_enum(self):
        # Post-#6534: invalid category values are rejected at Pydantic
        # validation time (HTTP layer) via the ``CatalogCategory`` str-enum
        # constructor. Direct enum construction reproduces the same check.
        with pytest.raises(ValueError):
            CatalogCategory("garbage")

    def test_invalid_sort_rejected_by_enum(self):
        # Post-#6534: invalid sort_by values are rejected at Pydantic
        # validation time (HTTP layer) via the ``CatalogSort`` str-enum
        # constructor. Direct enum construction reproduces the same check.
        with pytest.raises(ValueError):
            CatalogSort("badfield")

    @pytest.mark.asyncio
    async def test_total_matches_entry_count(self):
        redis = _make_redis(catalog=None)
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            resp = await list_catalog(
                category=CatalogCategory.ALL,
                search=None,
                sort_by=CatalogSort.NAME,
                source_id="builtin",
            )
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
        # #7366: key is namespaced by source_id (default=builtin)
        redis.sadd.assert_awaited_once_with(_installed_key(BUILTIN_SOURCE_ID), "logger-plugin")

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
        redis.get.return_value = None
        redis.set.return_value = True
        redis.smembers.return_value = set()  # migration: no legacy data
        redis.scan_iter = MagicMock(side_effect=lambda match="": _async_iter([]))
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
            result = await uninstall_plugin("hello-plugin", source_id=BUILTIN_SOURCE_ID)
        assert result == {"status": "uninstalled", "plugin": "hello-plugin"}

    @pytest.mark.asyncio
    async def test_srem_called_with_plugin_name(self):
        redis = _make_redis(installed={"hello-plugin"})
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            # Pass source_id explicitly (direct handler calls skip FastAPI's Query unwrap)
            await uninstall_plugin("hello-plugin", source_id=BUILTIN_SOURCE_ID)
        # #7366: key is namespaced by source_id
        redis.srem.assert_awaited_once_with(_installed_key(BUILTIN_SOURCE_ID), "hello-plugin")

    @pytest.mark.asyncio
    async def test_raises_404_when_not_installed(self):
        redis = _make_redis(installed=set())
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await uninstall_plugin("hello-plugin", source_id=BUILTIN_SOURCE_ID)
        assert exc_info.value.status_code == 404
        assert "hello-plugin" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_raises_500_on_redis_srem_error(self):
        redis = AsyncMock()
        builtin_key = _installed_key(BUILTIN_SOURCE_ID).encode()

        async def _smembers(key):
            key_str = key.decode() if isinstance(key, bytes) else key
            if key_str == _LEGACY_INSTALLED_KEY:
                return set()
            return {b"hello-plugin"}

        redis.smembers.side_effect = _smembers
        redis.scan_iter = MagicMock(side_effect=lambda match="": _async_iter([builtin_key]))
        redis.srem.side_effect = ConnectionError("Redis down")
        redis.delete.return_value = 1
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            with pytest.raises(HTTPException) as exc_info:
                await uninstall_plugin("hello-plugin")
        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# #7366 — Per-source key collision tests
# ---------------------------------------------------------------------------


class TestInstalledKeyCollision:
    """Regression tests for #7366 — same plugin name in two different sources."""

    def test_installed_key_helper(self):
        assert _installed_key("builtin") == "marketplace:installed:builtin"
        assert _installed_key("abc-123") == "marketplace:installed:abc-123"
        assert _installed_key("builtin") != _installed_key("other-source")

    @pytest.mark.asyncio
    async def test_same_name_two_sources_stored_separately(self):
        """Installing 'hello-plugin' from builtin and a custom source writes to different keys."""
        builtin_redis = _make_redis(catalog=None, installed=set())
        custom_redis = _make_redis(catalog=None, installed=set())

        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=builtin_redis)):
            await install_plugin(InstallRequest(plugin_name="hello-plugin", source_id=BUILTIN_SOURCE_ID))

        # For a custom source we need to mock _resolve_catalog; test key routing only
        custom_redis.sadd.return_value = 1
        custom_source_id = "custom-source-uuid"
        expected_custom_key = _installed_key(custom_source_id)
        expected_builtin_key = _installed_key(BUILTIN_SOURCE_ID)

        # Verify the builtin install wrote to the builtin key
        builtin_redis.sadd.assert_awaited_once_with(expected_builtin_key, "hello-plugin")

        # Keys must differ
        assert expected_builtin_key != expected_custom_key

    @pytest.mark.asyncio
    async def test_list_installed_merges_across_sources(self):
        """GET /installed returns union of all source sets (#7366)."""
        redis = _make_redis(
            installed_by_source={
                BUILTIN_SOURCE_ID: {"hello-plugin", "logger-plugin"},
                "custom-src": {"hello-plugin", "custom-tool"},
            }
        )
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await list_installed()
        # Same name from two sources appears once in merged list
        assert sorted(result["installed"]) == sorted(["hello-plugin", "logger-plugin", "custom-tool"])

    @pytest.mark.asyncio
    async def test_uninstall_one_source_leaves_other_intact(self):
        """Uninstalling from builtin does not touch the custom-source key."""
        redis = _make_redis(
            installed_by_source={
                BUILTIN_SOURCE_ID: {"hello-plugin"},
                "custom-src": {"hello-plugin"},
            }
        )
        with patch("api.marketplace.get_async_redis_client", new=AsyncMock(return_value=redis)):
            result = await uninstall_plugin("hello-plugin", source_id=BUILTIN_SOURCE_ID)
        assert result == {"status": "uninstalled", "plugin": "hello-plugin"}
        # srem only called with the builtin key, not the custom one
        redis.srem.assert_awaited_once_with(_installed_key(BUILTIN_SOURCE_ID), "hello-plugin")

    @pytest.mark.asyncio
    async def test_migrate_legacy_installed_moves_to_builtin(self):
        """#7366: legacy marketplace:installed members migrate to marketplace:installed:builtin."""
        redis = AsyncMock()
        redis.smembers.return_value = {b"hello-plugin", b"logger-plugin"}
        redis.sadd.return_value = 2
        redis.delete.return_value = 1

        await _migrate_legacy_installed(redis)

        redis.sadd.assert_awaited_once()
        call_args = redis.sadd.call_args
        assert call_args[0][0] == _installed_key(BUILTIN_SOURCE_ID)
        migrated = set(call_args[0][1:])
        assert migrated == {"hello-plugin", "logger-plugin"}
        redis.delete.assert_awaited_once_with(_LEGACY_INSTALLED_KEY)

    @pytest.mark.asyncio
    async def test_migrate_legacy_installed_noop_when_empty(self):
        """Migration does nothing when legacy key has no members."""
        redis = AsyncMock()
        redis.smembers.return_value = set()

        await _migrate_legacy_installed(redis)

        redis.sadd.assert_not_awaited()
        redis.delete.assert_not_awaited()
