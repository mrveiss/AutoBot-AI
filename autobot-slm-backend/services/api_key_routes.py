# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which SLM routes accept a user API key: exactly the ones that declare one (#16294).

Owner ruling on #16294 (2026-09-18): the SLM accepts user API keys **only** on an
explicit allow-list of integration routes. Each listed route declares the permission
it requires through ``require_key_permission``. A key is refused with 403 on every
other route, even when its scopes would allow the action.

The list is not kept by hand. It is the set of routes whose dependencies include a
``require_key_permission`` check, found by walking each route's dependency tree,
router-level dependencies included. Declaring the permission and joining the list are
therefore one act, and they cannot drift apart.

**The list ships empty.** No SLM route was found that an external integration calls
with a user key. Node agents use their own ``X-Internal-API-Key``, CI calls only the
unauthenticated health route, and the only API-key docs describe the main backend
(#16294, #16999). ``repo_tests/api_key_scopes_are_enforced_16040_test.py`` pins the
list, so adding a member is a visible, reviewed change.

Free of FastAPI imports except Starlette's ``Match``, so it can be loaded on its own.
"""

from typing import Any, Callable

from starlette.routing import Match

#: Set on the dependency ``require_key_permission`` returns. Its value is the declared permission.
KEY_PERMISSION_MARK = "__autobot_key_permission__"


def mark_key_permission(dependency: Callable, permission: Any) -> Callable:
    """Mark *dependency* as a key check requiring *permission*; return it."""
    setattr(dependency, KEY_PERMISSION_MARK, permission)
    return dependency


def declared_key_permission(dependant: Any) -> Any:
    """The permission a route's dependency tree declares for a key, or None."""
    for sub in getattr(dependant, "dependencies", None) or ():
        found = getattr(sub.call, KEY_PERMISSION_MARK, None)
        if found is None:
            found = declared_key_permission(sub)
        if found is not None:
            return found
    return None


def accepts_api_key(app: Any, scope: dict) -> bool:
    """Whether the route *scope* resolves to declares a key permission.

    A request that matches no route fully, or matches a mount, is not accepted: a key is
    refused there too, never waved through to whatever answers.
    """
    for route in app.router.routes:
        match, _child = route.matches(scope)
        if match is Match.FULL:
            return declared_key_permission(getattr(route, "dependant", None)) is not None
    return False
