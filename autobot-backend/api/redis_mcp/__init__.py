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
from services.mcp_bridge_manifest import MCPBridgeManifest

MANIFEST = MCPBridgeManifest(
    name="redis_mcp",
    version="1.0.0",
    description="Redis Data & Operations - Direct Redis access, vector search, server ops",
    features=[
        "data_access",
        "vector_search",
        "hybrid_search",
        "ops_intelligence",
        "stream_health",
        "rbac_filtering",
    ],
    endpoint="/api/redis/mcp/tools",
)

__all__ = ["router", "MANIFEST"]
