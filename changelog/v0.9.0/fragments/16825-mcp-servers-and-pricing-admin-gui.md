---
type: feat
scope: frontend
issue: 16825
pr: 0000
---
Two admin pages for backend features that had no reachable GUI: `/admin/mcp-servers` (full CRUD for user-configured external MCP servers — stdio/SSE/streamable_http transports, Bearer/API-key/Basic credential threading, allowed-role scoping) and `/admin/pricing` (live LLM pricing refresh status per provider, on-demand refresh, and manual price override). Both are read-mostly against existing #11542 and GH#6480/#16228/#16231 backends; no new API surface.
