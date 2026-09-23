---
type: fix
scope: backend
issue: 16449
---
`autobot-backend/mcp/` (AutoBot's own MCP server code) is renamed to `autobot-backend/mcp_server/`. It permanently shadowed the real `mcp` PyPI SDK for every module with `autobot-backend/` on `sys.path`, so the installed dependency was unreachable by its own name from anywhere in the backend. No behaviour change — every import updated to the new name, a regression guard added.
