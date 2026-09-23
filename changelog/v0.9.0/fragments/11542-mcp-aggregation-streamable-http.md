---
type: refactor
scope: backend
issue: 11542
pr: 0000
---
Extract realtime_mcp_bridge's multi-server discovery, collision-prefixing, and skip-unreachable-server logic into services/mcp_aggregation.py so the voice bridge and the upcoming external MCP server bridge share one implementation; add StreamableHTTPTransport (spec 2025-03-26+) to skills/sync/mcp_transport.py so MCPClient can reach current third-party MCP servers, most of which only speak Streamable HTTP.
