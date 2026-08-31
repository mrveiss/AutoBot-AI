# Marketplace API Reference

**Issue:** #1803 — Plugin and agent marketplace  
**Router prefix:** `/marketplace`  
**Feature tag:** `marketplace`, `plugins`

The Marketplace API provides community catalog browsing and per-instance plugin installation state management. The catalog is seeded from built-in core-plugin manifests and cached in Redis. Installation state (which plugins are marked installed) is persisted in a Redis Set per AutoBot instance.

---

## Authentication

All marketplace endpoints require a valid JWT bearer token in the `Authorization` header.

```
Authorization: Bearer <token>
```

Requests without a valid token receive `401 Unauthorized`.

---

## Base URL

```
http://<backend-host>:8001/marketplace
```

---

## Redis Key Reference

| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `marketplace:catalog` | String (JSON array) | 3600 s (1 h) | Cached catalog; re-seeded from built-ins on miss |
| `marketplace:installed` | Set (string members) | None (persistent) | Plugin names marked as installed on this instance |

The catalog TTL means catalog data may lag up to one hour after a built-in catalog update is deployed. The installed set has no TTL — installation state persists until explicitly removed via the uninstall endpoint.

---

## Endpoints

### GET /marketplace/catalog

List and optionally search or filter the plugin catalog.

**Query parameters**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `category` | string | `all` | Filter by category. See valid values in `GET /marketplace/categories`. |
| `search` | string | _(none)_ | Full-text search across `name`, `description`, and `tags` (case-insensitive substring match). |
| `sort_by` | string | `downloads` | Sort order. Valid values: `downloads`, `rating`, `name`, `newest`. |

The `newest` sort preserves catalog insertion order in reverse (most-recently added first).

**Request**

```
GET /marketplace/catalog?category=observability&sort_by=rating
Authorization: Bearer <token>
```

**Response — 200 OK**

```json
{
  "entries": [
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
      "source_url": "https://github.com/mrveiss/AutoBot-AI/tree/Dev_new_gui/plugins/core-plugins/logger-plugin"
    }
  ],
  "total": 1,
  "category": "observability",
  "sort_by": "rating"
}
```

> `telemetry-prompt-middleware` is not in the catalog. It is built-in
> middleware (`autobot-backend/middleware/builtin/telemetry_prompt_middleware.py`),
> unconditionally registered by `initialization.lifespan._init_builtin_extensions`
> — not a plugin a user installs or uninstalls (#14280).

**Response fields**

| Field | Type | Description |
|-------|------|-------------|
| `entries` | array | Filtered and sorted plugin entries. |
| `total` | integer | Count of entries after filtering (not the full catalog size). |
| `category` | string | The category filter value that was applied. |
| `sort_by` | string | The sort field that was applied. |

**Error responses**

| Status | Condition | `detail` example |
|--------|-----------|-----------------|
| 400 | `category` not in valid set | `"Invalid category 'foo'. Valid: ['agent', 'all', 'analytics', ...]"` |
| 400 | `sort_by` not in valid set | `"Invalid sort_by 'stars'. Valid: ['downloads', 'name', 'newest', 'rating']"` |
| 401 | Missing or invalid token | _(standard auth error)_ |

**Search example**

```
GET /marketplace/catalog?search=mcp&sort_by=name
Authorization: Bearer <token>
```

Returns any plugin whose name, description, or any tag contains the substring `mcp` (case-insensitive).

---

### GET /marketplace/catalog/{name}

Retrieve a single catalog entry by plugin name (slug).

**Path parameter**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | The plugin's `name` field (slug, e.g. `logger-plugin`). |

**Request**

```
GET /marketplace/catalog/mcp-wrapper-plugin
Authorization: Bearer <token>
```

**Response — 200 OK**

```json
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
  "source_url": "https://github.com/mrveiss/AutoBot-AI/tree/Dev_new_gui/plugins/core-plugins/mcp-wrapper-plugin"
}
```

**Error responses**

| Status | Condition | `detail` example |
|--------|-----------|-----------------|
| 404 | Plugin name not in catalog | `"Plugin not found in marketplace: my-missing-plugin"` |
| 401 | Missing or invalid token | _(standard auth error)_ |

---

### GET /marketplace/categories

List all valid category and sort-option values accepted by the catalog endpoint. Useful for populating UI filter dropdowns without hardcoding constants on the client.

**Request**

```
GET /marketplace/categories
Authorization: Bearer <token>
```

**Response — 200 OK**

```json
{
  "categories": ["agent", "all", "analytics", "example", "integration", "observability", "tool"],
  "sort_options": ["downloads", "name", "newest", "rating"]
}
```

Both lists are returned in alphabetical order.

**Error responses**

| Status | Condition |
|--------|-----------|
| 401 | Missing or invalid token |

---

### GET /marketplace/installed

List the names of all plugins currently marked as installed on this AutoBot instance.

**Request**

```
GET /marketplace/installed
Authorization: Bearer <token>
```

**Response — 200 OK**

```json
{
  "installed": ["kb-event-plugin", "logger-plugin"]
}
```

The `installed` array is sorted alphabetically. An empty array is returned when no plugins have been installed.

**Error responses**

| Status | Condition |
|--------|-----------|
| 401 | Missing or invalid token |

**Notes**

- Installation state is instance-wide, not per-user. All authenticated users on the same AutoBot instance share the same installed set.
- The endpoint reads from the `marketplace:installed` Redis Set. A Redis read failure is logged as a warning and returns an empty list rather than a 5xx error, to preserve UI availability.

---

### POST /marketplace/install

Mark a catalog plugin as installed. Validates the plugin exists in the catalog, adds its name to the `marketplace:installed` Redis Set, and increments its download counter in the cached catalog.

**Request**

```
POST /marketplace/install
Authorization: Bearer <token>
Content-Type: application/json

{
  "plugin_name": "logger-plugin"
}
```

**Request body**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `plugin_name` | string | Yes | The `name` (slug) of the plugin to install. Must exist in the catalog. |

**Response — 201 Created**

```json
{
  "status": "installed",
  "plugin": "logger-plugin"
}
```

**Side effects**

1. `SADD marketplace:installed logger-plugin` — records the plugin as installed.
2. The cached catalog entry for the plugin has its `downloads` counter incremented by 1 and the catalog JSON is re-written to Redis with the original TTL.

**Error responses**

| Status | Condition | `detail` example |
|--------|-----------|-----------------|
| 404 | `plugin_name` not in catalog | `"Plugin not found in marketplace: unknown-plugin"` |
| 500 | Redis write failure | `"Failed to record plugin installation"` |
| 401 | Missing or invalid token | _(standard auth error)_ |
| 422 | Missing or malformed request body | _(Pydantic validation error)_ |

**Notes**

- Installing a plugin that is already in the installed set is idempotent at the Redis level (`SADD` is a no-op for existing members), but the download counter will still be incremented and a `201` response is returned.
- This endpoint records intent only. Actual plugin loading into the runtime is handled separately via `POST /api/plugins/{name}/load` (see `PLUGIN_SDK.md`).

---

### DELETE /marketplace/install/{name}

Remove a plugin from the installed set, marking it as uninstalled.

**Path parameter**

| Parameter | Type | Description |
|-----------|------|-------------|
| `name` | string | The plugin slug to uninstall (must be in the installed set). |

**Request**

```
DELETE /marketplace/install/logger-plugin
Authorization: Bearer <token>
```

**Response — 200 OK**

```json
{
  "status": "uninstalled",
  "plugin": "logger-plugin"
}
```

**Error responses**

| Status | Condition | `detail` example |
|--------|-----------|-----------------|
| 404 | Plugin not in installed set | `"Plugin not installed: logger-plugin"` |
| 500 | Redis write failure | `"Failed to remove plugin installation"` |
| 401 | Missing or invalid token | _(standard auth error)_ |

**Notes**

- Uninstalling removes the name from the `marketplace:installed` Set only. It does not unload the plugin from the runtime — use `POST /api/plugins/{name}/unload` for that.
- The download counter in the catalog is not decremented on uninstall.

---

## Error Response Shape

All error responses follow FastAPI's standard `HTTPException` shape:

```json
{
  "detail": "Human-readable error message."
}
```

---

## Curl Quick Reference

```bash
BASE=http://localhost:8001/marketplace
TOKEN=<your-jwt>

# List all plugins sorted by rating
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/catalog?sort_by=rating" | jq .

# Search for MCP-related plugins
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/catalog?search=mcp" | jq .

# Get a single plugin
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/catalog/logger-plugin" | jq .

# Valid categories and sort options
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/categories" | jq .

# List installed plugins
curl -s -H "Authorization: Bearer $TOKEN" "$BASE/installed" | jq .

# Install a plugin
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plugin_name":"logger-plugin"}' \
  "$BASE/install" | jq .

# Uninstall a plugin
curl -s -X DELETE \
  -H "Authorization: Bearer $TOKEN" \
  "$BASE/install/logger-plugin" | jq .
```

---

## Related Documentation

- Plugin runtime management: `docs/developer/PLUGIN_SDK.md`
- Plugin publishing: `docs/developer/PLUGIN_PUBLISHING_GUIDE.md`
- Redis client usage: `docs/developer/REDIS_CLIENT_USAGE.md`
- Feature router registration: `autobot-backend/initialization/router_registry/feature_routers.py` line 474
