# Plugin Publishing Guide

**Issue:** #1803 — Plugin and agent marketplace  
**Audience:** Developers building and distributing AutoBot plugins

This guide covers how to author a plugin, define its manifest, integrate with the built-in catalog, manage per-user configuration, and understand the full install-to-uninstall lifecycle. For the runtime plugin SDK (loading, hooks, inter-plugin communication), see `docs/developer/PLUGIN_SDK.md`.

---

## Plugin Manifest Format (`plugin.json`)

Every plugin must have a `plugin.json` manifest at the root of its directory. This file is the single source of truth for the plugin's identity, dependencies, and catalog metadata.

### Full manifest schema

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "display_name": "My Plugin",
  "description": "One-to-two sentence description shown in the marketplace UI.",
  "author": "Your Name or GitHub username",
  "category": "integration",
  "tags": ["keyword-one", "keyword-two"],
  "entry_point": "plugins.core_plugins.my_plugin.main",
  "dependencies": ["logger-plugin"],
  "hooks": ["on_message_received", "on_agent_complete"],
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "description": "API key for the external service."
      },
      "timeout": {
        "type": "integer",
        "default": 30,
        "minimum": 1,
        "maximum": 300,
        "description": "Request timeout in seconds."
      }
    },
    "required": ["api_key"]
  },
  "source_url": "https://github.com/mrveiss/AutoBot-AI/tree/Dev_new_gui/plugins/core-plugins/my-plugin"
}
```

### Field reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Unique slug identifier. Lowercase, hyphen-separated. Used as the primary key in the catalog and installed set. Must be stable — renaming a published plugin is a breaking change. |
| `version` | string | Yes | Semantic version string (`MAJOR.MINOR.PATCH`). |
| `display_name` | string | Yes | Human-readable name shown in the marketplace UI. |
| `description` | string | Yes | Short description (1–2 sentences). Searched by the catalog full-text filter. |
| `author` | string | Yes | Author name or GitHub username. |
| `category` | string | Yes | One of the valid category slugs (see Categories section). |
| `tags` | array of strings | No | Additional search keywords. Searched by the catalog full-text filter. Defaults to `[]`. |
| `entry_point` | string | Yes | Python dotted-path to the module containing the `Plugin` class (e.g. `plugins.core_plugins.my_plugin.main`). |
| `dependencies` | array of strings | No | Plugin `name` slugs that must be loaded before this plugin. **Not pip packages** — a distribution name here can never be satisfied (#13966). Defaults to `[]`. |
| `python_dependencies` | array of strings | No | Importable **module** names this plugin needs, checked with `importlib.util.find_spec` at load time. Module, not distribution: Pillow is declared as `PIL`. Defaults to `[]`. |
| `hooks` | array of strings | No | Hook names this plugin registers. Informational — used in catalog display and future permission scoping. Defaults to `[]`. |
| `config_schema` | object | No | JSON Schema object describing the plugin's configuration. Validated at load time when config is provided via `POST /api/plugins/{name}/load`. |
| `source_url` | string | No | URL to the plugin source code. Shown in the marketplace UI. Auto-generated for core plugins via `_plugin_source_url()`. |

### Naming rules

- `name` must be unique across the entire catalog.
- Use lowercase letters, digits, and hyphens only: `^[a-z0-9-]+$`.
- Do not use `_v2`, `_fix`, `_new`, or similar suffixes — version changes belong in the `version` field.

---

## Plugin Types

AutoBot does not enforce a strict type enum in the manifest, but by convention plugins fall into the following categories. Use the matching `category` value in your manifest.

| Type | `category` value | Description |
|------|-----------------|-------------|
| Agent extension | `agent` | Adds new agent behaviors or wraps an agent execution loop. |
| Workflow integration | `integration` | Connects AutoBot to external systems (APIs, message queues, databases). |
| Tool wrapper | `tool` | Exposes external tools to AutoBot agents via hook registration. |
| Knowledge connector | `integration` | Indexes or retrieves knowledge from external sources (use `knowledge-base` tag). |
| Observability/analytics | `observability` or `analytics` | Logs, metrics, or audit hooks. |
| UI widget | _(future)_ | Frontend Vue component registered via the widget registry. |
| Example/SDK demo | `example` | Reference implementations for plugin authors. |

---

## Plugin Directory Structure

```
plugins/
├── core-plugins/              # Shipped with AutoBot — included in built-in catalog
│   ├── my-plugin/
│   │   ├── plugin.json        # Manifest (required)
│   │   └── main.py            # Plugin code (must export Plugin = MyPluginClass)
│   └── ...
│
└── community-plugins/         # External or user-supplied plugins
    └── my-custom-plugin/
        ├── plugin.json
        ├── main.py
        └── requirements.txt   # Plugin-specific pip dependencies
```

`core-plugins` are shipped with the repository and automatically populate the marketplace catalog at startup. `community-plugins` are loaded at runtime but are not in the catalog unless explicitly added (see Adding to the Catalog below).

---

## Adding a Plugin to the Built-in Catalog

The current catalog is self-hosted — there is no remote registry. To add a plugin to the catalog that users see in the marketplace UI, add an entry to the `_BUILTIN_CATALOG` list in `autobot-backend/api/marketplace.py`.

### Steps

1. Create the plugin directory and files under `plugins/core-plugins/<your-plugin>/`.

2. Verify `plugin.json` is valid JSON and all required fields are present:

   ```bash
   python -c "import json; json.load(open('plugins/core-plugins/my-plugin/plugin.json'))"
   ```

3. Add a catalog entry to `_BUILTIN_CATALOG` in `autobot-backend/api/marketplace.py`:

   ```python
   {
       "name": "my-plugin",
       "version": "1.0.0",
       "display_name": "My Plugin",
       "description": "One-to-two sentence description.",
       "author": "mrveiss",
       "category": "integration",
       "tags": ["keyword-one", "keyword-two"],
       "entry_point": "plugins.core_plugins.my_plugin.main",
       "dependencies": [],
       "hooks": ["on_message_received"],
       "downloads": 0,
       "rating": 0.0,
       "source_url": _plugin_source_url("my-plugin"),
   },
   ```

   Use `_plugin_source_url("my-plugin")` for the `source_url` — this builds the URL from `config.GITHUB_REPO_URL` and `config.GITHUB_DEFAULT_BRANCH` so it stays correct across forks and branch renames.

4. The `_CATALOG_TTL` is 3600 seconds. After deploying, flush the cached catalog key if you need the new entry to appear immediately:

   ```bash
   redis-cli -n 0 DEL marketplace:catalog
   ```

5. File a GitHub issue linking the plugin to `#1803` as context, then open a PR targeting `Dev_new_gui`.

### Valid categories

The catalog endpoint validates the `category` field against a fixed set. Only these values are accepted:

```
agent, analytics, example, integration, observability, tool
```

The `all` value is accepted as a filter parameter but must not be used as a plugin's own category.

To add a new category, update `_VALID_CATEGORIES` in `autobot-backend/api/marketplace.py` and add the new value to the `GET /marketplace/categories` response (it is derived automatically from `_VALID_CATEGORIES`).

---

## Plugin Lifecycle

The marketplace API manages **installation intent** (which plugins are marked installed). The plugin SDK manages **runtime state** (loaded, enabled, disabled). These are separate concerns.

```
Catalog → Install → Load → Enable → (use) → Disable → Unload → Uninstall
  |          |        |       |                  |         |         |
  |    marketplace   plugin SDK             plugin SDK  plugin SDK  marketplace
  |    POST /install POST /load            POST /disable POST /unload DELETE /install
```

### 1. Install

```bash
curl -X POST http://localhost:8001/marketplace/install \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plugin_name": "my-plugin"}'
```

Records the plugin name in the `marketplace:installed` Redis Set. Increments the download counter in the cached catalog. Does not load the plugin into the runtime.

### 2. Load and activate

```bash
# Load with optional configuration
curl -X POST http://localhost:8001/api/plugins/my-plugin/load \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config": {"api_key": "sk-...", "timeout": 60}}'

# Enable
curl -X POST http://localhost:8001/api/plugins/my-plugin/enable \
  -H "Authorization: Bearer $TOKEN"
```

The plugin manager resolves `entry_point`, imports the module, instantiates `Plugin`, calls `initialize()`, then transitions state to `ENABLED`. Hook registrations made in `initialize()` become active at this point.

### 3. Configure (at runtime)

```bash
curl -X PUT http://localhost:8001/api/plugins/my-plugin/config \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"config": {"api_key": "sk-new", "timeout": 90}}'
```

Configuration is persisted to Redis at `plugin:config:<plugin_name>`. The plugin manager may reload the plugin to apply the new config, depending on implementation.

### 4. Disable and unload

```bash
curl -X POST http://localhost:8001/api/plugins/my-plugin/disable \
  -H "Authorization: Bearer $TOKEN"

curl -X POST http://localhost:8001/api/plugins/my-plugin/unload \
  -H "Authorization: Bearer $TOKEN"
```

`disable()` suspends hook callbacks. `unload()` calls `shutdown()`, removes the plugin from the registry, and releases all resources. Hook registrations made in `initialize()` must be cleaned up in `shutdown()`.

### 5. Uninstall

```bash
curl -X DELETE http://localhost:8001/marketplace/install/my-plugin \
  -H "Authorization: Bearer $TOKEN"
```

Removes the plugin from the `marketplace:installed` Redis Set. Does not affect runtime state — unload the plugin first if it is still loaded.

---

## Per-User Plugin Configuration

Currently plugin configuration is **instance-wide** — there is one configuration per plugin name, shared by all users on the instance. Configuration is stored at:

```
Redis key: plugin:config:<plugin_name>
```

To implement per-user configuration in a plugin, namespace the configuration keys by user ID within the plugin's own `initialize()` or via a custom hook:

```python
async def initialize(self) -> None:
    redis = await get_async_redis_client(database="main")
    # Store per-user overrides under a namespaced key
    user_config_key = f"plugin:config:{self.manifest.name}:user:{user_id}"
    raw = await redis.get(user_config_key)
    if raw:
        user_overrides = json.loads(raw)
        self.effective_config = {**self._config, **user_overrides}
```

A first-class per-user configuration API is tracked in issue #4451.

---

## Plugin Categories and Tagging

### Categories

Choose the single most accurate category for your plugin. Categories drive the marketplace filter UI.

| Category | When to use |
|----------|-------------|
| `agent` | Modifies or extends agent behavior |
| `analytics` | Usage metrics, cost tracking, dashboards |
| `example` | SDK demos, starter templates |
| `integration` | External API bridges, knowledge connectors, MCP wrappers |
| `observability` | Logging, tracing, alerting |
| `tool` | Exposes tools to agents |

### Tags

Tags are free-form search keywords. They supplement the category filter. Guidelines:

- Use existing tags from the catalog when applicable for better discoverability.
- Prefer specific terms: `mcp`, `redis`, `openai`, `knowledge-base` rather than generic ones like `useful`, `plugin`.
- 3–6 tags is typical. More than 10 is noise.
- Tags are searched as case-insensitive substrings by the catalog API.

Common tag vocabulary in the built-in catalog:

```
analytics, audit, debugging, integration, knowledge-base, logging,
mcp, observability, prompts, sdk, telemetry, token-tracking, tools
```

---

## How Install Validates and Stores State

When `POST /marketplace/install` is called:

1. The catalog is fetched from Redis (`marketplace:catalog`). On a cache miss, the built-in catalog is re-seeded.
2. The requested `plugin_name` is looked up by exact match against the `name` field of each catalog entry. A 404 is returned if not found.
3. `SADD marketplace:installed <plugin_name>` writes the name to the installed Set. `SADD` is idempotent for already-installed names.
4. The full catalog JSON is rewritten to Redis with the matching entry's `downloads` counter incremented by 1. The TTL is reset to 3600 s.
5. A 201 response is returned with `{"status": "installed", "plugin": "<name>"}`.

The installed Set key (`marketplace:installed`) has no TTL — it persists indefinitely until items are removed via `DELETE /marketplace/install/{name}` or the key is manually deleted.

---

## Future: Community Registry Path

The current implementation is self-hosted: the catalog is populated from `_BUILTIN_CATALOG` in `marketplace.py` and cached in Redis. The architecture is designed to be upgraded to a remote registry without breaking the API contract.

The planned upgrade path:

1. **Remote catalog fetch** — replace `_get_catalog()` with an HTTP fetch from a community registry URL (configurable via `config.MARKETPLACE_REGISTRY_URL`). The Redis cache layer already provides the abstraction point.
2. **Plugin signatures** — add a `signature` field to the manifest and verify it against a registry public key before allowing install.
3. **Community submissions** — a GitHub-based submission flow where plugin authors open a PR to a `community-registry` repository, triggering automated manifest validation and security scanning.
4. **Per-org install namespacing** — replace the single `marketplace:installed` Set with `marketplace:installed:<org_id>` Sets once multi-org support lands (issue #4451).

For now, to publish a plugin: open a PR to `Dev_new_gui` adding the plugin under `plugins/core-plugins/` and a catalog entry in `marketplace.py`.

---

## Checklist for a New Plugin

Before opening a PR:

- `plugin.json` present, valid JSON, all required fields populated
- `name` is lowercase, hyphen-separated, unique in the catalog
- `category` is one of the valid values
- `entry_point` resolves to an importable module: `python -c "import plugins.core_plugins.my_plugin.main"`
- Module exports `Plugin = MyPluginClass`
- `Plugin` inherits from `BasePlugin` and implements `initialize()` and `shutdown()`
- `shutdown()` unregisters all hooks registered in `initialize()`
- `config_schema` present if the plugin accepts any configuration
- `_BUILTIN_CATALOG` entry added to `autobot-backend/api/marketplace.py`
- `source_url` uses `_plugin_source_url("my-plugin")` helper
- No hardcoded URLs, secrets, or IP addresses in plugin code
- No `print()` calls — use `self._logger`

---

## Related Documentation

- Plugin SDK (runtime loading, hooks, lifecycle API): `docs/developer/PLUGIN_SDK.md`
- Marketplace API reference: `docs/api/MARKETPLACE_API.md`
- Redis client usage: `docs/developer/REDIS_CLIENT_USAGE.md`
- MCP bridge integration: `docs/developer/MCP_BRIDGE_ISOLATION.md`
- Issue #1803: Plugin and agent marketplace
- Issue #730: Plugin SDK architecture
