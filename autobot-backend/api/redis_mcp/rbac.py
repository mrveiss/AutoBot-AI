# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RBAC filtering for Redis MCP Bridge tools.

Issue #2511: Role-based permission filtering for Redis MCP tools.

Roles:
- user: Read all + write autobot:agent:* namespace only, no client_list/slowlog
- admin: Full access, destructive ops (delete) require approval
"""

from enum import Enum

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Namespace that non-admin users are allowed to write to
AGENT_NAMESPACE_PREFIX = "autobot:agent:"


class ToolAccess(str, Enum):
    """Access levels for Redis MCP tools."""

    READ = "read"
    SCOPED_WRITE = "scoped"  # Write only to autobot:agent:* namespace
    FULL_WRITE = "full"
    APPROVAL_REQUIRED = "approval"
    BLOCKED = "blocked"


# Tool access matrix: tool_name -> (user_access, admin_access)
TOOL_ACCESS_MATRIX = {
    # Data Access — read tools
    "redis_get": (ToolAccess.READ, ToolAccess.READ),
    "redis_hget": (ToolAccess.READ, ToolAccess.READ),
    "redis_hgetall": (ToolAccess.READ, ToolAccess.READ),
    "redis_lrange": (ToolAccess.READ, ToolAccess.READ),
    "redis_zrange": (ToolAccess.READ, ToolAccess.READ),
    "redis_xrange": (ToolAccess.READ, ToolAccess.READ),
    "redis_scan_keys": (ToolAccess.READ, ToolAccess.READ),
    "redis_type": (ToolAccess.READ, ToolAccess.READ),
    "redis_ttl": (ToolAccess.READ, ToolAccess.READ),
    # Data Access — write tools
    "redis_set": (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE),
    "redis_hset": (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE),
    "redis_lpush": (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE),
    "redis_rpush": (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE),
    "redis_xadd": (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE),
    "redis_delete": (ToolAccess.SCOPED_WRITE, ToolAccess.APPROVAL_REQUIRED),
    # Vector Search — index creation restricted for users (#2511)
    "redis_vector_create_index": (ToolAccess.SCOPED_WRITE, ToolAccess.FULL_WRITE),
    "redis_vector_search": (ToolAccess.READ, ToolAccess.READ),
    "redis_hybrid_search": (ToolAccess.READ, ToolAccess.READ),
    "redis_vector_index_info": (ToolAccess.READ, ToolAccess.READ),
    # Ops Intelligence
    "redis_server_info": (ToolAccess.READ, ToolAccess.READ),
    "redis_dbsize": (ToolAccess.READ, ToolAccess.READ),
    "redis_memory_stats": (ToolAccess.READ, ToolAccess.READ),
    "redis_stream_health": (ToolAccess.READ, ToolAccess.READ),
    "redis_client_list": (ToolAccess.BLOCKED, ToolAccess.READ),
    "redis_slowlog": (ToolAccess.BLOCKED, ToolAccess.READ),
}


def get_tool_access(tool_name: str, is_admin: bool) -> ToolAccess:
    """Return the access level for a tool given the user's role."""
    entry = TOOL_ACCESS_MATRIX.get(tool_name)
    if entry is None:
        return ToolAccess.BLOCKED
    user_access, admin_access = entry
    return admin_access if is_admin else user_access


def check_tool_permission(tool_name: str, is_admin: bool) -> tuple[bool, str | None]:
    """Check if a tool call is permitted.

    Returns:
        (allowed, error_message) — allowed is True if the call can proceed.
    """
    access = get_tool_access(tool_name, is_admin)
    if access == ToolAccess.BLOCKED:
        return False, f"Tool '{tool_name}' is not available for your role"
    return True, None


def validate_key_namespace(key: str, is_admin: bool, access: ToolAccess) -> tuple[bool, str | None]:
    """Validate that a key write is within the allowed namespace.

    Scoped-write users can only write to keys prefixed with autobot:agent:*.
    Admins with full access have no restriction.
    """
    if access == ToolAccess.FULL_WRITE:
        return True, None
    if access == ToolAccess.SCOPED_WRITE and not is_admin:
        if not key.startswith(AGENT_NAMESPACE_PREFIX):
            return False, (
                f"Write denied: key '{key}' is outside the " f"allowed namespace '{AGENT_NAMESPACE_PREFIX}*'"
            )
    return True, None


# ---------------------------------------------------------------------------
# Voice-context toolset bundles (#7344)
# ---------------------------------------------------------------------------

# Tool capability tags for bundle membership (data-driven, not name-based)
# New tools auto-classify based on their declared ToolAccess level.
_BUNDLE_TAG_MAP: dict[str, set[str]] = {
    "voice_safe": {"read"},  # read-only tools only
    "voice_extended": {"read", "scoped_write"},  # read + scoped writes
    "voice_admin": {"read", "scoped_write", "full", "approval"},  # all non-blocked
}

# Map ToolAccess → capability tag
_ACCESS_TO_TAG: dict[ToolAccess, str] = {
    ToolAccess.READ: "read",
    ToolAccess.SCOPED_WRITE: "scoped_write",
    ToolAccess.FULL_WRITE: "full",
    ToolAccess.APPROVAL_REQUIRED: "approval",
    ToolAccess.BLOCKED: "blocked",
}


def get_tool_capability_tag(tool_name: str, is_admin: bool) -> str:
    """Return the capability tag for a tool given the user's role."""
    access = get_tool_access(tool_name, is_admin)
    return _ACCESS_TO_TAG.get(access, "blocked")


def filter_tools_for_bundle(
    tools: list[str],
    bundle: str,
    is_admin: bool,
    disabled_tools: list[str] | None = None,
) -> list[str]:
    """Filter tool names by the active voice bundle.

    Args:
        tools: All tool names to consider
        bundle: Bundle name — one of voice_safe, voice_extended, voice_admin
        is_admin: Whether the current user has admin role
        disabled_tools: Additional tool names explicitly disabled (per-bundle override)

    Returns:
        Filtered list of tool names permitted in this bundle for this role.
    """
    allowed_tags = _BUNDLE_TAG_MAP.get(bundle, _BUNDLE_TAG_MAP["voice_safe"])
    denied = set(disabled_tools or [])
    result = []
    for tool in tools:
        if tool in denied:
            continue
        tag = get_tool_capability_tag(tool, is_admin)
        if tag in allowed_tags:
            result.append(tool)
    logger.debug(
        "voice_bundle bundle=%s is_admin=%s tools_in=%d tools_out=%d",
        bundle,
        is_admin,
        len(tools),
        len(result),
    )
    return result


# ---------------------------------------------------------------------------
# Per-user bundle resolution (GH#8605)
# Resolution order: user DB override → role default → global env default
# ---------------------------------------------------------------------------

# Role-based default bundles
_ROLE_DEFAULT_BUNDLE: dict[str, str] = {
    "admin": "voice_admin",
    "user": "voice_safe",
}

_VALID_BUNDLES = frozenset(_BUNDLE_TAG_MAP.keys())
VALID_BUNDLES: frozenset = _VALID_BUNDLES


async def resolve_bundle_for_user(user_id: str, role: str = "user") -> tuple[str, str]:
    """Return (bundle_name, resolution) for a user.

    Resolution values: 'user_override' | 'role_default' | 'global_env'
    """
    # 1. Check per-user DB override
    try:
        from database.session import get_async_session  # noqa: PLC0415
        from sqlalchemy import text  # noqa: PLC0415

        async with get_async_session() as session:
            row = await session.execute(
                text("SELECT bundle_name FROM user_voice_bundle WHERE user_id = :uid"),
                {"uid": str(user_id)},
            )
            result = row.fetchone()
            if result is not None:
                return result[0], "user_override"
    except Exception:
        logger.debug("resolve_bundle_for_user: DB lookup failed, falling through")

    # 2. Role default
    role_bundle = _ROLE_DEFAULT_BUNDLE.get(role)
    if role_bundle:
        return role_bundle, "role_default"

    # 3. Global env default
    import os  # noqa: PLC0415

    env_bundle = os.getenv("AUTOBOT_VOICE_TOOLSETS", "voice_safe")
    if env_bundle not in _VALID_BUNDLES:
        env_bundle = "voice_safe"
    return env_bundle, "global_env"
