# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Default category, type, role and search-mode values (#19335).

Split out of ``ssot_constants`` (a grandfathered file that may not grow) when the knowledge
search modes gained their one allow-list. ``ssot_constants`` re-exports ``CategoryDefaults``,
so every existing ``from autobot_shared.ssot_constants import CategoryDefaults`` keeps working.
"""


class CategoryDefaults:
    """Default category and type values for classification."""

    GENERAL: str = "general"
    IMPORTED: str = "imported"
    UNKNOWN: str = "unknown"
    SEARCH_MODE_HYBRID: str = "hybrid"
    SEARCH_MODE_SEMANTIC: str = "semantic"
    SEARCH_MODE_KEYWORD: str = "keyword"
    SEARCH_MODE_AUTO: str = "auto"
    #: Every mode the knowledge search API accepts -- the ONE allow-list (#19335).
    SEARCH_MODES: tuple[str, ...] = (
        SEARCH_MODE_SEMANTIC,
        SEARCH_MODE_KEYWORD,
        SEARCH_MODE_HYBRID,
        SEARCH_MODE_AUTO,
    )
    QUERY_TYPE_GENERAL: str = "general"
    QUERY_TYPE_TECHNICAL: str = "technical"
    QUERY_TYPE_CODE: str = "code"
    CONTEXT_TYPE_GENERAL: str = "general"
    CONTEXT_TYPE_SECURITY: str = "security"
    CONTEXT_TYPE_RESEARCH: str = "research"
    # CHAT MESSAGE authorship — who wrote a message. NOT an authorization role.
    #
    # Two other vocabularies use the word "role" and share values with this one
    # (#14024): ``autobot_shared.auth.permissions.Role`` (platform RBAC) and
    # ``llc.models.enums.MembershipRole`` (company membership). ``ROLE_USER``
    # holds the same string as ``Role.USER``, and this class is a bare string
    # constant holder, so a value from here satisfies an RBAC parameter with no
    # type error and no test failure.
    #
    # ``tools/tool_registry`` came within one applied lint suggestion of tying an
    # authorization decision to ``ROLE_USER`` (#13934). If a field is consumed by
    # a permission check, it wants ``auth.permissions.Role`` — not these. The
    # overlap is asserted in ``security/roles_do_not_collide_test.py``.
    ROLE_USER: str = "user"
    ROLE_ASSISTANT: str = "assistant"
    ROLE_SYSTEM: str = "system"
    MODE_DEVELOPMENT: str = "development"
    MODE_PRODUCTION: str = "production"
    MODE_TESTING: str = "testing"
