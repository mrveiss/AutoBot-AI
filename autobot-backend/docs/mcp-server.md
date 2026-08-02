# AutoBot MCP Server

Exposes AutoBot's KB, memory graph, and agent introspection as an MCP server for external clients (Claude Code, Cline, Gemini CLI, etc.).

## Transports

**stdio** (default — used by Claude Code / Cline):
```bash
AUTOBOT_MCP_TOKEN="$MCP_SECRET:kb,memory,agents" python -m mcp.autobot_mcp_main
```

**HTTP** (standalone aiohttp on port 8200):
```bash
AUTOBOT_MCP_TOKEN="$MCP_SECRET:kb,memory,agents" python -m mcp.autobot_mcp_main --http
```

The HTTP transport is also available via the FastAPI backend at `POST /api/mcp/tool`.

## Auth

Token format: `<secret>:<scope1>,<scope2>`

Set the shared secret via `AUTOBOT_MCP_TOKEN` (the part before the first `:`).

> **The secret is the entire check.** A caller presenting a valid secret chooses its
> own scopes from the token string, so anyone holding it has every scope regardless
> of what you intended to grant. Generate a real one and never commit it:
>
> ```bash
> export MCP_SECRET="$(openssl rand -hex 32)"
> ```
>
> There is **no default** (#13263). Left unset, the HTTP path rejects every request
> rather than authenticating everyone — earlier revisions shipped a default that
> made `:kb,memory,agents` valid from any caller.
>
> For HTTP clients, prefer admin-minted tokens from the MCP token API over this
> long-lived shared secret.

Available scopes: `kb`, `memory`, `agents`.

Pass as `Authorization: Bearer <token>` for HTTP, or set `AUTOBOT_MCP_TOKEN` for stdio.

## Tools

| Tool | Scope | Description |
|---|---|---|
| `kb.search` | `kb` | Hybrid search over the knowledge base |
| `kb.get_document` | `kb` | Fetch a full KB document by ID |
| `kb.list_categories` | `kb` | Return the KB category tree |
| `kb.list_tags` | `kb` | List all indexed tags |
| `memory.entity_lookup` | `memory` | Fetch a memory-graph entity + relations by name |
| `memory.timeline` | `memory` | Entities related to an entity, sorted by time |
| `memory.related` | `memory` | Neighbour traversal up to a given depth |
| `memory.verbatim_search` | `memory` | Search verbatim conversation chunks |
| `agents.list` | `agents` | List all known agent IDs and descriptions |
| `agents.diary_summary` | `agents` | Recent diary entries for an agent |

## Claude Code / Cline configuration

Add to your MCP config (e.g. `.claude/mcp.json`):
```json
{
  "mcpServers": {
    "autobot": {
      "command": "python",
      "args": ["-m", "mcp.autobot_mcp_main"],
      "cwd": "/opt/autobot/autobot-backend",
      "env": { "AUTOBOT_MCP_TOKEN": "<your-secret>:kb,memory,agents" }
    }
  }
}
```

## Rate limiting

50 requests per 60-second window per token. Excess requests receive HTTP 429 / JSON-RPC error code `-32029`.
