# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis MCP Bridge — Agent-facing Redis access, vector search, ops intelligence.

Issue #2511: 11th native MCP bridge providing 25 tools across 3 categories:
- Data Access (15 tools): get/set, hash, list, sorted set, stream, scan, type, ttl, delete
- Vector Search (4 tools): create_index, vector_search, hybrid_search, index_info
- Ops Intelligence (6 tools): server_info, dbsize, memory_stats, stream_health,
  client_list, slowlog

RBAC Model:
- Users: Read all + write autobot:agent:* namespace only, read-only ops
- Admins: Full access, destructive ops require approval
"""

from api.redis_mcp.router import router

__all__ = ["router"]
