# Voice Toolset Bundles

**Issue:** #7344  
**Module:** `autobot-backend/api/redis_mcp/rbac.py`  
**Bridge:** `autobot-backend/services/realtime_mcp_bridge.py`

## Overview

Voice sessions (particularly low-latency Realtime sessions) should only receive
a curated subset of MCP tools. Surfacing destructive tools like `redis_delete`
or ops-only tools like `redis_slowlog` to a voice model is a security and
usability risk. Named bundles solve this by declaring which capability classes
are visible per voice context type.

## Bundles

Three bundles are shipped. Select the active bundle with the
`AUTOBOT_VOICE_TOOLSETS` env var (default: `voice_safe`).

| Bundle | Capability tags included | Typical use |
|---|---|---|
| `voice_safe` | `read` | Low-latency Realtime; minimal attack surface |
| `voice_extended` | `read`, `scoped_write` | Standard voice sessions; agent writes to `autobot:agent:*` namespace |
| `voice_admin` | `read`, `scoped_write`, `full`, `approval` | Admin voice sessions; all non-blocked tools |

## Capability Tags

Tools in `TOOL_ACCESS_MATRIX` (rbac.py) are classified by their `ToolAccess`
level. The mapping is:

| ToolAccess | Capability tag |
|---|---|
| `READ` | `read` |
| `SCOPED_WRITE` | `scoped_write` |
| `FULL_WRITE` | `full` |
| `APPROVAL_REQUIRED` | `approval` |
| `BLOCKED` | `blocked` (never included in any bundle) |

This is data-driven: new tools added to `TOOL_ACCESS_MATRIX` are automatically
classified into the correct bundles without any bundle-specific code changes.

## Per-Session Denylist

Individual tools can be removed from any bundle at runtime via the
`AUTOBOT_VOICE_DISABLED_TOOLS` env var (comma-separated tool names):

```
AUTOBOT_VOICE_DISABLED_TOOLS=redis_delete,redis_xadd
```

The denylist is additive — it removes tools that would otherwise appear in the
active bundle. If a tool is already excluded by bundle rules, adding it to the
denylist is a no-op.

## Configuration

| Env var | Default | Description |
|---|---|---|
| `AUTOBOT_VOICE_TOOLSETS` | `voice_safe` | Active bundle name |
| `AUTOBOT_VOICE_DISABLED_TOOLS` | `` (empty) | Comma-separated tool names to block |

## Integration

`RealtimeMCPBridge.list_realtime_tools()` applies bundle + RBAC filtering
before returning schemas to the caller:

```python
from services.realtime_mcp_bridge import get_realtime_bridge

bridge = await get_realtime_bridge(is_admin=user.is_admin)
tools = await bridge.list_realtime_tools()
# tools is already filtered — safe to pass directly to OpenAI Realtime session.update
```

Full MCP transport wiring (tool call routing) is implemented in issue #7343.

## RBAC Interaction

Bundle filtering respects RBAC roles. The `is_admin` flag passed to
`filter_tools_for_bundle()` determines which side of each tool's
`(user_access, admin_access)` tuple is evaluated:

- A regular user with `voice_extended` sees `scoped_write` tools, but only to
  the `autobot:agent:*` namespace (enforced by `validate_key_namespace()`).
- An admin with `voice_extended` sees `full` write tools as well, since their
  access level is promoted to `FULL_WRITE` in the matrix.

## Testing

```bash
cd autobot-backend
pytest api/redis_mcp/voice_bundles_test.py -v
```
