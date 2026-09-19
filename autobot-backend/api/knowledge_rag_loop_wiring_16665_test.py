# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""knowledge_rag_loop's 3 routes were extracted out of api/knowledge_rag.py
(#16665, to stay under its grandfathered line-count ceiling) and re-mounted
via router.include_router(), not re-registered in feature_routers.py's
FEATURE_ROUTER_CONFIGS -- so they must still resolve to the exact same
final path, tags and auth dependency as before the move.
"""

from api.knowledge_rag import router as knowledge_rag_router
from auth_middleware import get_current_user
from autobot_shared.api_routing.router_routes import effective_routes

_EXPECTED = {
    ("GET", "/loop/status"): "get_loop_status",
    ("POST", "/loop/approve"): "approve_loop_variant",
    ("POST", "/loop/reject"): "reject_loop_variant",
}


def _dependency_calls(dependant) -> list:
    calls: list = []
    stack = [dependant]
    seen: set[int] = set()
    while stack:
        node = stack.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        for dep in getattr(node, "dependencies", None) or ():
            call = getattr(dep, "call", None)
            if call is not None:
                calls.append(call)
            stack.append(dep)
    return calls


def test_every_loop_route_is_mounted_under_knowledge_rag_with_its_original_path():
    mounted_by_path = {}
    for mounted in effective_routes(knowledge_rag_router):
        for method in mounted.methods - {"HEAD"}:
            mounted_by_path[(method, mounted.path)] = mounted

    missing = set(_EXPECTED) - set(mounted_by_path)
    assert not missing, f"loop routes not mounted at their original path: {missing}"

    for key, endpoint_name in _EXPECTED.items():
        mounted = mounted_by_path[key]
        assert (
            mounted.route.endpoint.__name__ == endpoint_name
        ), f"{key} resolves to {mounted.route.endpoint.__name__!r}, expected {endpoint_name!r}"
        assert "knowledge-rag-loop" in mounted.route.tags, f"{key} lost its tag: {mounted.route.tags}"
        assert get_current_user in _dependency_calls(mounted.route.dependant), f"{key} lost its auth dependency"
