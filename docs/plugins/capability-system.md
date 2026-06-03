# Plugin Capability System

> **Issue**: [#9049](https://github.com/mrveiss/AutoBot-AI/issues/9049)  
> **Status**: Implemented  
> **Version**: 1.0.0

## Overview

AutoBot's plugin capability system provides **capability-based security** for plugins. Each plugin must declare required permissions in its manifest, operators explicitly approve capabilities during install, and the runtime enforces declared capabilities at every API call.

## Key Concepts

### Capabilities

A **capability** is a permission to access a specific AutoBot subsystem or resource. Capabilities follow the pattern `<domain>:<action>`:

| Capability | Access Granted |
|------------|----------------|
| `kb:read` | Read from Knowledge Base |
| `kb:write` | Write to Knowledge Base |
| `kb:admin` | Admin operations on KB |
| `llm:call` | Call LLM providers (OpenAI, Anthropic, etc.) |
| `llm:embedding` | Generate embeddings |
| `llm:fine_tune` | Fine-tune models |
| `filesystem:read` | Read files from disk |
| `filesystem:write` | Write files to disk |
| `filesystem:delete` | Delete files from disk |
| `network:outbound` | Make outbound HTTP requests |
| `network:inbound` | Accept inbound HTTP requests |
| `database:read` | Read from AutoBot database |
| `database:write` | Write to AutoBot database |
| `database:admin` | Database admin operations |
| `agent:read` | Read agent metadata |
| `agent:execute` | Execute agent tasks |
| `agent:admin` | Create/delete agents |
| `system:env` | Access environment variables |
| `system:process` | Spawn processes |
| `system:admin` | System-level admin operations |
| `redis:read` | Read from Redis |
| `redis:write` | Write to Redis |
| `workflow:read` | Read workflow definitions |
| `workflow:execute` | Execute workflows |

**Minimal-capability principle**: Plugins should declare only the capabilities they actually need. A hello-world plugin that just logs a message requires zero capabilities.

### Trust Tiers

Trust tiers indicate the source and review status of a plugin:

| Tier | Meaning | Auto-Grant |
|------|---------|------------|
| `official` | Built by AutoBot core team | ✅ Yes |
| `verified` | Reviewed and approved by AutoBot team | ❌ No (requires operator approval) |
| `community` | Community-submitted, unverified | ❌ No |
| `unverified` | Newly uploaded, not yet reviewed | ❌ No |

**Auto-grant behavior**: Only `official` plugins automatically receive their declared capabilities at load time. All other plugins require explicit operator approval via the `/plugins/{name}/approve-capabilities` endpoint.

## Plugin Manifest

Each plugin declares capabilities in its `plugin.json` manifest:

```json
{
  "name": "image-generation-plugin",
  "version": "1.0.0",
  "display_name": "Image Generation Plugin",
  "description": "Generate images via DALL-E 3, Flux, Stable Diffusion",
  "author": "mrveiss",
  "entry_point": "plugins.core_plugins.image_generation_plugin.main",
  
  "capabilities": ["llm:call", "network:outbound", "system:env"],
  "trust_tier": "official",
  
  "config_schema": { ... },
  "required_env": [ ... ]
}
```

**Fields**:
- `capabilities`: Array of capability strings (required, can be empty `[]`)
- `trust_tier`: One of `official`, `verified`, `community`, `unverified` (defaults to `community`)

## Operator Workflow

### 1. Install Plugin

```bash
# Upload ZIP
curl -X POST http://localhost:8001/api/plugins/install/upload \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@my-plugin.zip"

# Or clone from Git
curl -X POST http://localhost:8001/api/plugins/install/git \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/user/my-plugin.git"}'
```

### 2. Discover Available Plugins

```bash
curl -X GET http://localhost:8001/api/plugins/discover \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Check Capability Requirements

```bash
curl -X GET http://localhost:8001/api/plugins/my-plugin/capabilities \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "plugin_name": "my-plugin",
  "trust_tier": "community",
  "required_capabilities": ["kb:read", "llm:call", "network:outbound"],
  "granted_capabilities": [],
  "pending_approval": ["kb:read", "llm:call", "network:outbound"]
}
```

### 4. Approve Capabilities

After reviewing the plugin's required capabilities:

```bash
curl -X POST http://localhost:8001/api/plugins/my-plugin/approve-capabilities \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": ["kb:read", "llm:call", "network:outbound"]
  }'
```

Response:
```json
{
  "status": "success",
  "message": "Granted 3 capabilities to plugin my-plugin",
  "granted": ["kb:read", "llm:call", "network:outbound"]
}
```

### 5. Load Plugin

```bash
curl -X POST http://localhost:8001/api/plugins/my-plugin/load \
  -H "Authorization: Bearer $TOKEN"
```

If capabilities are not yet approved, the plugin loads but cannot call any protected APIs. The operator must approve capabilities first.

## Enforcement

### Runtime Checks

Every protected API call in a plugin must call `CapabilityChecker.check()`:

```python
from plugin_sdk.capabilities import Capability, CapabilityChecker

checker = CapabilityChecker()

async def my_plugin_function():
    # Check capability before calling KB
    await checker.check(
        plugin_name="my-plugin",
        capability=Capability.KB_READ,
        operation="kb_query",
        metadata={"collection": "documents"}
    )
    
    # If capability not granted, raises CapabilityError
    # Otherwise, proceeds with KB query
    result = await kb_client.query(...)
    return result
```

### Capability Violations

If a plugin attempts an undeclared capability:

1. `CapabilityChecker.check()` raises `CapabilityError`
2. The violation is logged to the audit stream: `plugin:capability:audit`
3. The operator sees the violation in the audit log UI
4. The plugin's API call fails with `403 Forbidden`

## Audit Log

### Viewing Audit Log

```bash
curl -X GET 'http://localhost:8001/api/plugins/audit?limit=50' \
  -H "Authorization: Bearer $TOKEN"
```

Response:
```json
{
  "entries": [
    {
      "timestamp": "2026-05-31T19:00:00Z",
      "plugin_name": "my-plugin",
      "capability": "kb:read",
      "granted": true,
      "operation": "kb_query",
      "metadata": "{\"collection\": \"documents\"}"
    },
    {
      "timestamp": "2026-05-31T18:59:00Z",
      "plugin_name": "malicious-plugin",
      "capability": "filesystem:delete",
      "granted": false,
      "operation": "file_delete",
      "metadata": "{\"path\": \"/etc/passwd\"}"
    }
  ],
  "total": 2
}
```

**Audit retention**: The audit log stream retains the last 10,000 entries (Redis `XADD MAXLEN 10000`).

### Monitoring Violations

Operators should monitor the audit log for `granted: false` entries, which indicate capability violations. Repeated violations from a plugin may indicate:

- Bug in the plugin (calling wrong API)
- Malicious behavior (attempting unauthorized access)
- Outdated capability declarations

**Action**: Review the plugin's code, update its capabilities if legitimate, or uninstall if malicious.

## Developer Guide

### Creating a Capability-Aware Plugin

1. **Declare capabilities in `plugin.json`**:

```json
{
  "name": "my-plugin",
  "capabilities": ["kb:read", "llm:call"],
  "trust_tier": "community",
  ...
}
```

2. **Import and use `CapabilityChecker`**:

```python
from plugin_sdk.base import BasePlugin
from plugin_sdk.capabilities import Capability, CapabilityChecker

class MyPlugin(BasePlugin):
    def __init__(self, manifest, config=None):
        super().__init__(manifest, config)
        self.checker = CapabilityChecker()
    
    async def query_knowledge_base(self, query: str):
        # Check capability before API call
        await self.checker.check(
            plugin_name=self.manifest.name,
            capability=Capability.KB_READ,
            operation="kb_query",
            metadata={"query": query}
        )
        
        # Proceed with actual API call
        result = await kb_client.query(query)
        return result
```

3. **Handle `CapabilityError`**:

```python
from plugin_sdk.capabilities import CapabilityError

try:
    result = await self.query_knowledge_base("test")
except CapabilityError as exc:
    self._logger.error(
        "Missing capability: %s for plugin %s",
        exc.capability,
        exc.plugin_name
    )
    # Return error to caller or degrade gracefully
```

### Testing Capabilities

```python
import pytest
from plugin_sdk.capabilities import Capability, CapabilityChecker, CapabilityError

@pytest.mark.asyncio
async def test_capability_enforcement():
    checker = CapabilityChecker()
    
    # Without grant, check() raises CapabilityError
    with pytest.raises(CapabilityError):
        await checker.check(
            "my-plugin",
            Capability.KB_READ,
            operation="test"
        )
    
    # Grant capability
    checker.grant_capabilities("my-plugin", [Capability.KB_READ])
    
    # Now check() succeeds
    await checker.check(
        "my-plugin",
        Capability.KB_READ,
        operation="test"
    )
```

## Migration Guide

### Updating Existing Plugins

For plugins created before the capability system:

1. **Add `capabilities` field** to `plugin.json`:
   ```json
   {
     "capabilities": [],
     "trust_tier": "official"
   }
   ```

2. **Audit plugin code** for AutoBot API calls:
   - KB queries → add `kb:read` or `kb:write`
   - LLM calls → add `llm:call`
   - HTTP requests → add `network:outbound`
   - File I/O → add `filesystem:read`, `filesystem:write`, `filesystem:delete`

3. **Add capability checks** before protected API calls (see Developer Guide above)

4. **Test** with capabilities granted and denied to ensure proper enforcement

### Backward Compatibility

The capability system is **opt-in by default**:
- Plugins without `capabilities` field default to `[]` (no capabilities)
- `trust_tier` defaults to `community`
- Official plugins (in `plugins/core-plugins/`) default to `trust_tier: official` and auto-grant capabilities

No breaking changes for existing plugins — they continue to load, but will fail if they call protected APIs without declaring capabilities.

## Security Considerations

1. **Review all community plugins**: Never auto-approve capabilities for `community` or `unverified` plugins. Manually review code before granting permissions.

2. **Minimal capabilities**: Only grant what the plugin actually needs. A plugin requesting `database:admin` when it only needs `database:read` is suspicious.

3. **Monitor audit log**: Set up alerts for capability violations. Repeated violations = potential security threat.

4. **Trust tier verification**: `verified` tier should only be granted after thorough code review by AutoBot security team.

5. **Capability escalation**: A plugin granted `kb:read` should never be able to escalate to `kb:write` without explicit operator re-approval.

## API Reference

See `/autobot-backend/plugin_manager.py` for full endpoint documentation:

- `GET /plugins/{name}/capabilities` - View capability requirements and approval status
- `POST /plugins/{name}/approve-capabilities` - Approve capabilities for a plugin
- `GET /plugins/audit?limit=N` - Fetch capability audit log

## Related Issues

- [#730](https://github.com/mrveiss/AutoBot-AI/issues/730) - Plugin SDK foundation
- [#6464](https://github.com/mrveiss/AutoBot-AI/issues/6464) - 3rd-party plugin install
- [#6971](https://github.com/mrveiss/AutoBot-AI/issues/6971) - Plugin env var status
- [#9049](https://github.com/mrveiss/AutoBot-AI/issues/9049) - Capability manifest (this feature)
