# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Plugin and Agent Marketplace API

Community catalog for discovering, browsing, and installing plugins and agents.

Issue #1803 - Plugin and agent marketplace: package, share, and install extensions.
"""

import json
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.marketplace_sources import BUILTIN_SOURCE_ID
from api.schemas_workflows import (
    InstallRequest,
    MarketplaceCatalogResponse,
    MarketplaceCategoriesResponse,
    MarketplaceEntry,
    MarketplaceInstalledResponse,
    MarketplacePluginActionResponse,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.ssot_config import config


class CatalogCategory(str, Enum):
    """Marketplace plugin categories (#6534). Pydantic validates Query
    parameters against this enum and OpenAPI emits a proper enum schema so
    generated TypeScript clients get a union type instead of bare `string`.
    """

    ALL = "all"
    EXAMPLE = "example"
    ANALYTICS = "analytics"
    OBSERVABILITY = "observability"
    INTEGRATION = "integration"
    AGENT = "agent"
    TOOL = "tool"
    OTHER = "other"  # closes #6526 — was the silent default in _remote_plugin_to_entry


class CatalogSort(str, Enum):
    DOWNLOADS = "downloads"
    RATING = "rating"
    NAME = "name"
    NEWEST = "newest"


logger = get_logger(__name__)

router = APIRouter()

# Redis keys for marketplace data
_CATALOG_KEY = "marketplace:catalog"
_CATALOG_TTL = 3600  # 1 hour
# #7366: per-source installed SETs — marketplace:installed:{source_id}
# Legacy flat key retained only for one-shot migration on first read.
_INSTALLED_KEY_PREFIX = "marketplace:installed:"
_LEGACY_INSTALLED_KEY = "marketplace:installed"


def _installed_key(source_id: str) -> str:
    return f"{_INSTALLED_KEY_PREFIX}{source_id}"


def _plugin_source_url(slug: str) -> str:
    """Build a source URL for a core plugin from config, avoiding hardcoded paths."""
    repo = getattr(config, "GITHUB_REPO_URL", "https://github.com/mrveiss/AutoBot-AI")
    branch = getattr(config, "GITHUB_DEFAULT_BRANCH", "Dev_new_gui")
    return f"{repo}/tree/{branch}/plugins/core-plugins/{slug}"


# Built-in community catalog — seeded from core-plugins manifests + curated entries.
# In production this would be fetched from a remote registry; for MVP it is stored
# in Redis (populated once) and served from there.
_BUILTIN_CATALOG: list[dict[str, Any]] = [
    {
        "name": "hello-plugin",
        "version": "1.0.0",
        "display_name": "Hello Plugin",
        "description": "Simple example plugin demonstrating basic plugin structure.",
        "author": "AutoBot Team",
        "category": "example",
        "tags": ["example", "sdk"],
        "entry_point": "plugins.core_plugins.hello_plugin.main",
        "dependencies": [],
        "hooks": [],
        "downloads": 142,
        "rating": 4.2,
        "source_url": _plugin_source_url("hello-plugin"),
    },
    {
        "name": "kb-event-plugin",
        "version": "1.0.0",
        "display_name": "Knowledge Base Event Plugin",
        "description": (
            "Hooks into chat and KB events for analytics and audit logging. "
            "Ships as SDK documentation for third-party developers."
        ),
        "author": "mrveiss",
        "category": "analytics",
        "tags": ["knowledge-base", "analytics", "audit"],
        "entry_point": "plugins.core_plugins.kb_event_plugin.main",
        "dependencies": [],
        "hooks": ["on_message_received", "on_kb_search", "on_agent_complete"],
        "downloads": 87,
        "rating": 4.5,
        "source_url": _plugin_source_url("kb-event-plugin"),
    },
    {
        "name": "logger-plugin",
        "version": "1.0.0",
        "display_name": "Logger Plugin",
        "description": "Structured JSON logging for all hook events. Useful for debugging and observability.",
        "author": "mrveiss",
        "category": "observability",
        "tags": ["logging", "observability", "debugging"],
        "entry_point": "plugins.core_plugins.logger_plugin.main",
        "dependencies": [],
        "hooks": ["on_message_received", "on_agent_complete", "on_error"],
        "downloads": 203,
        "rating": 4.7,
        "source_url": _plugin_source_url("logger-plugin"),
    },
    {
        "name": "mcp-wrapper-plugin",
        "version": "1.0.0",
        "display_name": "MCP Wrapper Plugin",
        "description": "Wraps MCP tools as AutoBot plugin hooks for seamless tool integration.",
        "author": "mrveiss",
        "category": "integration",
        "tags": ["mcp", "tools", "integration"],
        "entry_point": "plugins.core_plugins.mcp_wrapper_plugin.main",
        "dependencies": [],
        "hooks": ["on_tool_call", "on_tool_result"],
        "downloads": 176,
        "rating": 4.3,
        "source_url": _plugin_source_url("mcp-wrapper-plugin"),
    },
    {
        "name": "telemetry-prompt-middleware",
        "version": "1.0.0",
        "display_name": "Telemetry Prompt Middleware",
        "description": "Injects telemetry context into prompts and tracks token usage across sessions.",
        "author": "mrveiss",
        "category": "observability",
        "tags": ["telemetry", "prompts", "token-tracking"],
        "entry_point": "plugins.core_plugins.telemetry_prompt_middleware.main",
        "dependencies": [],
        "hooks": ["on_prompt_build", "on_completion"],
        "downloads": 119,
        "rating": 4.1,
        "source_url": _plugin_source_url("telemetry-prompt-middleware"),
    },
]


def _coerce_str(value: Any, fallback: str = "") -> str:
    """Return ``value`` if it's a string, otherwise ``fallback``.

    #6525: untrusted external catalogs may emit ``None`` or non-string types
    where strings are expected. ``dict.get(key, default)`` only fires the
    default when the key is *missing* — present-but-null returns the stored
    ``None`` and downstream ``.replace``/``.title`` calls crash. This coercion
    keeps the response shape strict-string regardless of remote sloppiness.
    """
    return value if isinstance(value, str) else fallback


def _coerce_list(value: Any) -> list:
    """Return ``value`` if it's a list, else an empty list. (#6525)"""
    return value if isinstance(value, list) else []


def _remote_plugin_to_entry(plugin: dict[str, Any], source_name: str) -> dict[str, Any]:
    """Issue #6481: shape an external CatalogPlugin dict to look like a
    MarketplaceEntry. Missing fields get safe defaults so the existing
    response model and frontend continue to work.

    #6525: hardened against three failure modes:
      1. ``dict.get(key, default)`` does NOT fire ``default`` when the key
         exists with value ``None``. ``_coerce_str`` / ``_coerce_list``
         enforce the type contract regardless of remote payload shape.
      2. ``str.title()`` butchers acronyms (``"GIT-tools"`` → ``"Git Tools"``)
         and apostrophes (``"don't"`` → ``"Don'T"``). Prefer an
         upstream-provided ``display_name`` when present; fall back to the
         raw ``name`` (untransformed) only when no display_name is supplied.
      3. (Caller side) one bad entry must not 500 the whole catalog —
         see ``_safe_remote_plugin_to_entry`` wrapper.
    """
    raw_name = _coerce_str(plugin.get("name"))
    raw_display = _coerce_str(plugin.get("display_name"))
    return {
        "name": raw_name,
        "version": _coerce_str(plugin.get("version")),
        # #6525: prefer upstream display_name; fall back to raw name (no
        # destructive .title() transform). Keeps acronyms + apostrophes
        # + non-Latin scripts intact.
        "display_name": raw_display or raw_name,
        "description": _coerce_str(plugin.get("description")),
        "author": _coerce_str(plugin.get("author"), fallback=source_name),
        "category": _coerce_str(plugin.get("category"), fallback=CatalogCategory.OTHER.value),
        "tags": _coerce_list(plugin.get("tags")),
        "entry_point": "",
        "dependencies": [],
        "hooks": [],
        "downloads": 0,
        "rating": 0.0,
        "source_url": _coerce_str(plugin.get("git_url")),
    }


def _safe_remote_plugin_to_entry(plugin: Any, source_name: str) -> dict[str, Any] | None:
    """Per-item wrapper that turns one bad plugin into a logged skip.

    #6525: pre-fix, ``[_remote_plugin_to_entry(p, ...) for p in remote_plugins]``
    let any single malformed entry from a user-added remote marketplace
    raise mid-comprehension and 500 the entire ``/catalog?source_id=...``
    response — trivial DoS surface. Now per-item: bad entries are logged
    and skipped; good entries flow through.
    """
    if not isinstance(plugin, dict):
        logger.warning("Skipping non-dict catalog entry from %r: %r", source_name, type(plugin).__name__)
        return None
    try:
        return _remote_plugin_to_entry(plugin, source_name)
    except Exception as exc:
        # Defensive: even with the type coercions above, a future field
        # added in the remote schema could still raise something we
        # didn't anticipate. Log identifiable context, drop the entry.
        identifier = plugin.get("name") if isinstance(plugin.get("name"), str) else "<unknown>"
        logger.warning(
            "Skipping malformed catalog entry %r from %r: %s",
            identifier,
            source_name,
            exc,
        )
        return None


async def _get_catalog() -> list[dict[str, Any]]:
    """Return catalog from Redis cache, seeding from built-in list if missing."""
    try:
        redis = await get_async_redis_client(database="main")
        raw = await redis.get(_CATALOG_KEY)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Marketplace Redis read failed, using built-in catalog: %s", exc)

    # Seed cache with built-in entries
    try:
        redis = await get_async_redis_client(database="main")
        await redis.set(_CATALOG_KEY, json.dumps(_BUILTIN_CATALOG), ex=_CATALOG_TTL)
    except Exception as exc:
        logger.warning("Marketplace Redis seed failed: %s", exc)

    return _BUILTIN_CATALOG


async def _resolve_catalog(source_id: str) -> list[dict[str, Any]]:
    """#6524: shared catalog resolver used by list/detail/install endpoints.

    For ``source_id == BUILTIN_SOURCE_ID`` returns the cached built-in catalog
    (Redis-cached, seeded from ``_BUILTIN_CATALOG``). Otherwise looks up the
    user-added source by id, fetches its remote catalog, and wraps each entry
    via ``_safe_remote_plugin_to_entry`` to drop malformed payloads (#6525).

    Raises ``HTTPException(404)`` for unknown source_id and ``HTTPException(422)``
    for sources missing a catalog URL — preserves the same error semantics
    that ``list_catalog`` already surfaced (#6527 contract).
    """
    if source_id == BUILTIN_SOURCE_ID:
        return await _get_catalog()

    from api.marketplace_sources import (  # local import: avoid cycle
        fetch_remote_catalog,
        get_source_by_id,
    )

    source = await get_source_by_id(source_id)
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Marketplace source '{source_id}' not found",
        )
    if not source.url:
        # Issue #6527: do NOT silently substitute the built-in catalog —
        # surface the misconfiguration so the operator can fix the source.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Marketplace source '{source.name}' has no catalog URL configured",
        )
    remote_plugins = await fetch_remote_catalog(source.url)
    # #6525: per-item wrapper drops malformed entries instead of failing
    # the whole catalog. One bad apple from a user-added remote
    # marketplace no longer 500s the response.
    return [
        entry for p in remote_plugins for entry in (_safe_remote_plugin_to_entry(p, source.name),) if entry is not None
    ]


@router.get("/catalog", response_model=MarketplaceCatalogResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_catalog",
    error_code_prefix="MARKETPLACE",
)
async def list_catalog(
    category: CatalogCategory = Query(default=CatalogCategory.ALL, description="Filter by category"),
    search: str | None = Query(default=None, description="Full-text search across name, description, tags"),
    sort_by: CatalogSort = Query(default=CatalogSort.DOWNLOADS, description="Sort field"),
    source_id: str = Query(
        default=BUILTIN_SOURCE_ID,
        description=f"Marketplace source id; '{BUILTIN_SOURCE_ID}' or a user-added source UUID (#6481)",
    ),
    # Issue #6481: gate behind auth — non-builtin source_id triggers a server-side
    # fetch of arbitrary URLs (SSRF surface). Anonymous callers should not access this.
    user: dict = Depends(get_current_user),
) -> MarketplaceCatalogResponse:
    """
    List community marketplace catalog.

    Returns all available plugins and agents with optional filtering.

    Issue #1803: Plugin and agent marketplace.
    Issue #6481: ?source_id= selects which marketplace catalog to query.
    Issue #6534: category/sort_by validated by Pydantic via CatalogCategory/CatalogSort enums.
    """
    catalog = await _resolve_catalog(source_id)

    # Filter by category
    if category != CatalogCategory.ALL:
        catalog = [e for e in catalog if e.get("category") == category.value]

    # Full-text search across name, description, tags
    if search:
        q = search.lower()
        catalog = [
            e
            for e in catalog
            if q in e.get("name", "").lower()
            or q in e.get("description", "").lower()
            or any(q in t.lower() for t in e.get("tags", []))
        ]

    # Sort
    if sort_by == CatalogSort.DOWNLOADS:
        catalog = sorted(catalog, key=lambda e: e.get("downloads", 0), reverse=True)
    elif sort_by == CatalogSort.RATING:
        catalog = sorted(catalog, key=lambda e: e.get("rating", 0.0), reverse=True)
    elif sort_by == CatalogSort.NAME:
        catalog = sorted(catalog, key=lambda e: e.get("name", "").lower())
    # CatalogSort.NEWEST keeps insertion order (most recently added last → reverse)

    entries = [MarketplaceEntry(**e) for e in catalog]

    logger.debug(
        "Marketplace catalog: category=%s search=%s sort=%s total=%d",
        category,
        search,
        sort_by,
        len(entries),
    )

    return MarketplaceCatalogResponse(
        entries=entries,
        total=len(entries),
        category=category.value,
        sort_by=sort_by.value,
    )


@router.get("/catalog/{plugin_name}", response_model=MarketplaceEntry)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_catalog_entry",
    error_code_prefix="MARKETPLACE",
)
async def get_catalog_entry(
    plugin_name: str,
    source_id: str = Query(
        default=BUILTIN_SOURCE_ID,
        description=f"Marketplace source id; '{BUILTIN_SOURCE_ID}' or a user-added source UUID (#6481, #6524)",
    ),
    # #6524: align auth posture with list_catalog — non-builtin source_id
    # triggers a server-side fetch of arbitrary URLs (SSRF surface).
    user: dict = Depends(get_current_user),
) -> MarketplaceEntry:
    """
    Get a single marketplace catalog entry by name.

    Issue #1803: Plugin and agent marketplace.
    Issue #6524: ?source_id= selects which marketplace catalog to query —
    detail endpoint must agree with list_catalog and install_plugin.
    """
    catalog = await _resolve_catalog(source_id)
    entry = next((e for e in catalog if e.get("name") == plugin_name), None)

    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found in marketplace: {plugin_name}",
        )

    return MarketplaceEntry(**entry)


@router.get("/categories", response_model=MarketplaceCategoriesResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_categories",
    error_code_prefix="MARKETPLACE",
)
async def list_categories() -> dict[str, list[str]]:
    """
    List valid plugin categories and sort options.

    Issue #1803: Plugin and agent marketplace.
    Issue #6534: derived from CatalogCategory/CatalogSort enums (single source of truth).
    """
    return {
        "categories": sorted(c.value for c in CatalogCategory),
        "sort_options": sorted(s.value for s in CatalogSort),
    }


# ---------------------------------------------------------------------------
# Installed plugin management
# ---------------------------------------------------------------------------


async def _migrate_legacy_installed(redis: Any) -> None:
    """#7366: one-shot migration — move flat marketplace:installed into the
    builtin-source-namespaced key and delete the legacy key."""
    try:
        members = await redis.smembers(_LEGACY_INSTALLED_KEY)
        if not members:
            return
        decoded = [m.decode() if isinstance(m, bytes) else m for m in members]
        dest = _installed_key(BUILTIN_SOURCE_ID)
        await redis.sadd(dest, *decoded)
        await redis.delete(_LEGACY_INSTALLED_KEY)
        logger.info("Marketplace: migrated %d legacy installed entries to %s", len(decoded), dest)
    except Exception as exc:
        logger.warning("Marketplace: legacy installed migration failed (non-fatal): %s", exc)


async def _get_installed() -> set[str]:
    """Return merged set of installed plugin names across all sources.

    #7366: scans marketplace:installed:{source_id} keys and unions their
    members. Runs the legacy-key migration on first call after upgrade.
    """
    try:
        redis = await get_async_redis_client(database="main")
        await _migrate_legacy_installed(redis)
        names: set[str] = set()
        async for key in redis.scan_iter(match=f"{_INSTALLED_KEY_PREFIX}*"):
            key_str = key.decode() if isinstance(key, bytes) else key
            members = await redis.smembers(key_str)
            names.update(m.decode() if isinstance(m, bytes) else m for m in members)
        return names
    except Exception as exc:
        logger.warning("Marketplace: Redis read of installed set failed: %s", exc)
        return set()


@router.get("/installed", response_model=MarketplaceInstalledResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_installed",
    error_code_prefix="MARKETPLACE",
)
async def list_installed() -> dict[str, list[str]]:
    """
    List names of installed marketplace plugins.

    Issue #1803: Plugin and agent marketplace.
    """
    installed = await _get_installed()
    return {"installed": sorted(installed)}


@router.post("/install", status_code=status.HTTP_201_CREATED, response_model=MarketplacePluginActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="install_plugin",
    error_code_prefix="MARKETPLACE",
)
async def install_plugin(
    body: InstallRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """
    Mark a catalog plugin as installed.

    Validates the plugin exists in the resolved catalog (built-in or the
    user-added marketplace identified by ``body.source_id``) then records
    it in the installed set in Redis so the UI can reflect installation state.

    Issue #1803: Plugin and agent marketplace.
    Issue #6524: source_id required so install resolves against the same
    catalog the user was browsing — fixes the headline 404 on every
    custom-marketplace install.
    """
    catalog = await _resolve_catalog(body.source_id)
    entry = next((e for e in catalog if e.get("name") == body.plugin_name), None)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not found in marketplace: {body.plugin_name}",
        )

    try:
        redis = await get_async_redis_client(database="main")
        # #7366: write to per-source key so same name from different sources is stored separately
        await redis.sadd(_installed_key(body.source_id), body.plugin_name)
        # Bump download counter in cached catalog — only meaningful for the
        # built-in catalog (remote catalogs are read-only). Skip otherwise.
        if body.source_id == BUILTIN_SOURCE_ID:
            updated = [
                {**e, "downloads": e.get("downloads", 0) + 1} if e.get("name") == body.plugin_name else e
                for e in catalog
            ]
            await redis.set(_CATALOG_KEY, json.dumps(updated), ex=_CATALOG_TTL)
    except Exception as exc:
        logger.error("Marketplace: install failed for %s: %s", body.plugin_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record plugin installation",
        ) from exc

    logger.info(
        "Marketplace: installed plugin %s from source %s",
        body.plugin_name,
        body.source_id,
    )
    return {"status": "installed", "plugin": body.plugin_name}


@router.delete("/install/{plugin_name}", response_model=MarketplacePluginActionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="uninstall_plugin",
    error_code_prefix="MARKETPLACE",
)
async def uninstall_plugin(
    plugin_name: str,
    source_id: str = Query(
        default=BUILTIN_SOURCE_ID,
        description=f"Marketplace source id; '{BUILTIN_SOURCE_ID}' or a user-added source UUID (#7366)",
    ),
) -> dict[str, str]:
    """
    Remove a marketplace plugin from the installed set.

    Issue #1803: Plugin and agent marketplace.
    Issue #7366: source_id param targets the correct per-source key.
    """
    installed = await _get_installed()
    if plugin_name not in installed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Plugin not installed: {plugin_name}",
        )

    try:
        redis = await get_async_redis_client(database="main")
        # #7366: remove from the specific source key
        await redis.srem(_installed_key(source_id), plugin_name)
    except Exception as exc:
        logger.error("Marketplace: uninstall failed for %s: %s", plugin_name, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to remove plugin installation",
        ) from exc

    logger.info("Marketplace: uninstalled plugin %s from source %s", plugin_name, source_id)
    return {"status": "uninstalled", "plugin": plugin_name}
