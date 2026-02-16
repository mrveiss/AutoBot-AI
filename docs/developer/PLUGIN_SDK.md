# Plugin SDK Developer Guide
## Building Extensible Plugins for AutoBot

**Issue #730** - Plugin SDK for extensible tool architecture

---

## Overview

The AutoBot Plugin SDK allows you to create modular, self-contained extensions that can be loaded dynamically without modifying core code.

### Key Features

- **Dynamic loading** - Plugins discovered and loaded at runtime
- **Lifecycle management** - Initialize, enable, disable, reload, shutdown
- **Hook system** - Event-based extensibility
- **Type-safe** - Pydantic models and Python type hints
- **Isolation** - Plugins run independently
- **Configuration** - Per-plugin config stored in Redis

---

## Quick Start

### 1. Create Plugin Directory

```bash
mkdir -p plugins/core-plugins/my-plugin
cd plugins/core-plugins/my-plugin
```

### 2. Create Plugin Manifest (`plugin.json`)

```json
{
  "name": "my-plugin",
  "version": "1.0.0",
  "display_name": "My Plugin",
  "description": "Description of what my plugin does",
  "author": "Your Name",
  "entry_point": "plugins.core_plugins.my_plugin.main",
  "dependencies": [],
  "config_schema": {
    "type": "object",
    "properties": {
      "setting1": {
        "type": "string",
        "default": "value"
      }
    }
  },
  "hooks": []
}
```

### 3. Create Plugin Code (`main.py`)

```python
from typing import Dict, Optional
from plugin_sdk.base import BasePlugin, PluginManifest

class MyPlugin(BasePlugin):
    def __init__(self, manifest: PluginManifest, config: Optional[Dict] = None):
        super().__init__(manifest, config)
        self.my_setting = config.get("setting1", "default") if config else "default"

    async def initialize(self) -> None:
        """Initialize plugin resources."""
        self._logger.info("MyPlugin initializing...")
        # Setup code here
        self._logger.info("MyPlugin initialized!")

    async def shutdown(self) -> None:
        """Clean up plugin resources."""
        self._logger.info("MyPlugin shutting down...")
        # Cleanup code here

# Export plugin class
Plugin = MyPlugin
```

### 4. Load Plugin via API

```bash
# Discover plugins
curl -X GET http://localhost:8001/api/plugins/discover

# Load plugin
curl -X POST http://localhost:8001/api/plugins/my-plugin/load \
  -H "Content-Type: application/json" \
  -d '{"config": {"setting1": "custom_value"}}'

# Enable plugin
curl -X POST http://localhost:8001/api/plugins/my-plugin/enable
```

---

## Core Components

### BasePlugin

All plugins must inherit from `BasePlugin` and implement:

- `async def initialize()` - Setup resources
- `async def shutdown()` - Cleanup resources

Optional lifecycle methods:

- `async def enable()` - Called when plugin enabled
- `async def disable()` - Called when plugin disabled
- `async def reload()` - Hot-reload (default: shutdown + initialize)

### PluginManifest

Pydantic model defining plugin metadata:

```python
{
    "name": "unique-plugin-id",
    "version": "1.0.0",
    "display_name": "Human Readable Name",
    "description": "What this plugin does",
    "author": "Author Name",
    "entry_point": "python.module.path",
    "dependencies": ["other-plugin"],  # Load order
    "config_schema": {...},            # JSON schema
    "hooks": ["hook_name"]             # Hooks provided
}
```

### PluginRegistry

Singleton for managing loaded plugins:

```python
from plugin_sdk.base import PluginRegistry

registry = PluginRegistry()

# Get plugin
plugin = registry.get_plugin("my-plugin")

# List all plugins
all_plugins = registry.get_all_plugins()

# Get enabled plugins
enabled = registry.get_enabled_plugins()
```

---

## Hooks System

Plugins can register callbacks for system events:

### Registering Hooks

```python
from plugin_sdk.hooks import Hook, HookRegistry

class MyPlugin(BasePlugin):
    async def initialize(self):
        hook_registry = HookRegistry()

        # Register for agent execution
        hook_registry.register_hook(
            Hook.ON_AGENT_EXECUTE.value,
            self._on_agent_execute,
            plugin_name=self.manifest.name
        )

    async def _on_agent_execute(self, agent_name: str, **kwargs):
        """Called when agent executes."""
        self._logger.info("Agent executed: %s", agent_name)

    async def shutdown(self):
        # Unregister hooks
        hook_registry = HookRegistry()
        hook_registry.unregister_hook(
            Hook.ON_AGENT_EXECUTE.value,
            plugin_name=self.manifest.name
        )
```

### Available Hooks

| Hook | When Triggered | Arguments |
|------|----------------|-----------|
| `ON_STARTUP` | System startup | - |
| `ON_SHUTDOWN` | System shutdown | - |
| `ON_AGENT_EXECUTE` | Agent starts execution | `agent_name`, kwargs |
| `ON_AGENT_COMPLETE` | Agent finishes | `agent_name`, `result` |
| `ON_AGENT_ERROR` | Agent error | `agent_name`, `error` |
| `ON_TOOL_CALL` | Tool called | `tool_name`, kwargs |
| `ON_TOOL_COMPLETE` | Tool finishes | `tool_name`, `result` |
| `ON_TOOL_ERROR` | Tool error | `tool_name`, `error` |
| `ON_MESSAGE_RECEIVED` | Chat message received | `message`, kwargs |
| `ON_MESSAGE_SENT` | Chat message sent | `message`, kwargs |

### Calling Hooks (For Core Code)

```python
from plugin_sdk.hooks import Hook, HookRegistry

hook_registry = HookRegistry()

# Call hook (async)
results = await hook_registry.call_hook(
    Hook.ON_AGENT_EXECUTE.value,
    agent_name="MyAgent",
    params={"foo": "bar"}
)
```

---

## Configuration

### Plugin Configuration

Plugins receive configuration via `config` parameter:

```python
class MyPlugin(BasePlugin):
    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self.api_key = config.get("api_key") if config else None
        self.timeout = config.get("timeout", 30) if config else 30
```

### Config Schema

Define JSON schema in manifest for validation:

```json
{
  "config_schema": {
    "type": "object",
    "properties": {
      "api_key": {
        "type": "string",
        "description": "API key for external service"
      },
      "timeout": {
        "type": "integer",
        "default": 30,
        "minimum": 1,
        "maximum": 300
      }
    },
    "required": ["api_key"]
  }
}
```

### Updating Config at Runtime

```bash
# Update via API
curl -X PUT http://localhost:8001/api/plugins/my-plugin/config \
  -H "Content-Type: application/json" \
  -d '{"config": {"api_key": "new_key", "timeout": 60}}'
```

Configuration is persisted in Redis at `plugin:config:{plugin_name}`.

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/plugins` | GET | List loaded plugins |
| `/api/plugins/discover` | GET | Discover available plugins |
| `/api/plugins/{name}/load` | POST | Load plugin |
| `/api/plugins/{name}/unload` | POST | Unload plugin |
| `/api/plugins/{name}/reload` | POST | Reload plugin |
| `/api/plugins/{name}/enable` | POST | Enable plugin |
| `/api/plugins/{name}/disable` | POST | Disable plugin |
| `/api/plugins/{name}` | GET | Get plugin info |
| `/api/plugins/{name}/config` | GET | Get plugin config |
| `/api/plugins/{name}/config` | PUT | Update plugin config |

---

## Examples

### Example 1: Hello Plugin (Simple)

See: `plugins/core-plugins/hello-plugin/`

Basic plugin demonstrating lifecycle methods.

### Example 2: Logger Plugin (Hooks)

See: `plugins/core-plugins/logger-plugin/`

Logs system events using hook system.

### Example 3: MCP Wrapper Plugin (Integration)

See: `plugins/core-plugins/mcp-wrapper-plugin/`

Wraps MCP tools for plugin-based access.

---

## Best Practices

### 1. Resource Management

- Always clean up in `shutdown()`
- Use context managers where possible
- Release file handles, connections, threads

### 2. Error Handling

- Catch exceptions in plugin methods
- Use `self._logger` for logging
- Don't crash the main system

```python
async def initialize(self):
    try:
        self.connection = await connect_to_service()
    except Exception as e:
        self._logger.error("Failed to connect: %s", e)
        raise  # Or handle gracefully
```

### 3. Dependencies

- List plugin dependencies in manifest
- Check dependency versions if needed
- Fail fast if dependencies missing

### 4. Configuration

- Provide sensible defaults
- Validate config in `__init__`
- Document all config options in schema

### 5. Testing

- Test plugin lifecycle (load, enable, disable, unload)
- Test with missing/invalid config
- Test dependency resolution

---

## Troubleshooting

### Plugin Not Loading

**Check logs:**
```bash
tail -f /var/log/autobot/backend.log | grep plugin
```

**Common issues:**
- Entry point path incorrect
- Missing dependencies
- Syntax errors in plugin code
- Invalid manifest JSON

### Plugin Not Discovered

**Check plugin directories:**
```bash
ls -la /opt/autobot/plugins/core-plugins/
```

**Ensure `plugin.json` exists and is valid JSON:**
```bash
cat plugins/my-plugin/plugin.json | jq .
```

### Hooks Not Working

**Verify hook registration:**
```python
from plugin_sdk.hooks import HookRegistry
registry = HookRegistry()
print(registry.get_all_hooks())  # Should list your hooks
```

**Check plugin is enabled:**
```bash
curl http://localhost:8001/api/plugins/my-plugin
# status should be "enabled"
```

---

## Advanced Topics

### Inter-Plugin Communication

Plugins can access each other via registry:

```python
from plugin_sdk.base import PluginRegistry

registry = PluginRegistry()
other_plugin = registry.get_plugin("other-plugin")

if other_plugin and other_plugin.status == PluginStatus.ENABLED:
    result = await other_plugin.some_method()
```

### Custom Hook Types

Define custom hooks in your plugin:

```python
from plugin_sdk.hooks import HookRegistry

# In your plugin
hook_registry = HookRegistry()

# Register custom hook
hook_registry.register_hook(
    "my_plugin:custom_event",
    self._handle_custom_event,
    plugin_name=self.manifest.name
)

# Call custom hook
await hook_registry.call_hook("my_plugin:custom_event", data="foo")
```

### Hot Reload Development

Enable hot reload for faster development:

```bash
# Make changes to plugin code
vim plugins/my-plugin/main.py

# Reload without restart
curl -X POST http://localhost:8001/api/plugins/my-plugin/reload
```

---

## Plugin Directory Structure

```
plugins/
├── core-plugins/              # Built-in plugins (shipped with AutoBot)
│   ├── hello-plugin/
│   │   ├── plugin.json       # Manifest
│   │   └── main.py           # Plugin code
│   ├── logger-plugin/
│   └── mcp-wrapper-plugin/
│
└── community-plugins/         # External/user plugins
    └── my-custom-plugin/
        ├── plugin.json
        ├── main.py
        └── requirements.txt  # Plugin-specific dependencies
```

---

## Security Considerations

### Sandboxing (Future)

Current MVP does not sandbox plugins. Future versions will add:
- Resource limits (CPU, memory)
- Filesystem access restrictions
- Network access controls
- API permission scoping

### Trusted Plugins Only

- Only load plugins from trusted sources
- Review plugin code before loading
- Use plugin signatures (future)

### Configuration Security

- Don't store secrets in `plugin.json`
- Use environment variables or secrets manager
- Encrypt sensitive config in Redis (future)

---

## Migration Guide

### Migrating MCP Tools to Plugins

1. Create plugin manifest
2. Wrap MCP tool calls in plugin methods
3. Register hooks for tool events
4. Test plugin lifecycle

See `mcp-wrapper-plugin` for example.

---

## References

- **Core SDK**: `autobot-shared/plugin_sdk/`
- **Plugin Manager API**: `autobot-user-backend/plugin_manager.py`
- **Example Plugins**: `plugins/core-plugins/`
- **Issue #730**: Plugin SDK architecture discussion

---

**Document Version:** 1.0
**Last Updated:** 2026-02-16
**Issue:** #730
