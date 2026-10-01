# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Shaping a call graph into nodes, edges and metrics.

Extracted from ``endpoints/call_graph.py`` (#17651). That module is
grandfathered in a **shrink-only** size ratchet and the deadline-bounded scan
pushed it over, so the rule is to split rather than raise a ceiling.

These six functions were the largest self-contained piece: they take the
``functions``/``call_edges`` the AST walk produced and shape them into the
response's nodes, orphans, deduplicated edges and caller/callee metrics. No
router, no config, no logger, no AST -- they referenced nothing from the module
they came out of, which is what made them the clean cut.

Behaviour is unchanged. Names are public here and imported under their original
private names at the call site, so no call site moved.
"""

from __future__ import annotations

from typing import Dict, List


def get_connected_func_ids(call_edges: List[Dict]) -> set:
    """Get set of function IDs that appear in call edges."""
    connected_funcs = set()
    for edge in call_edges:
        connected_funcs.add(edge["from"])
        if edge["resolved"]:
            connected_funcs.add(edge["to"])
    return connected_funcs


def build_function_node(func_id: str, info: Dict) -> Dict:
    """Build a single function node dict from function info."""
    return {
        "id": func_id,
        "name": info["name"],
        "full_name": info["full_name"],
        "module": info["module"],
        "class": info["class"],
        "file": info["file"],
        "line": info["line"],
        "is_async": info["is_async"],
    }


def build_connected_nodes(
    functions: Dict[str, Dict],
    call_edges: List[Dict],
) -> List[Dict]:
    """Build graph nodes from connected functions (Issue #281: extracted)."""
    connected_funcs = get_connected_func_ids(call_edges)

    nodes = []
    for func_id, info in functions.items():
        if func_id in connected_funcs:
            nodes.append(build_function_node(func_id, info))
    return nodes


def build_orphaned_nodes(
    functions: Dict[str, Dict],
    call_edges: List[Dict],
) -> List[Dict]:
    """
    Build list of orphaned functions (defined but never called or calling).

    Orphaned functions are those that:
    - Are not callers (don't appear in edge 'from')
    - Are not callees (don't appear in edge 'to' with resolved=True)

    Returns:
        List of orphaned function nodes sorted by module/file for easier review.
    """
    connected_funcs = get_connected_func_ids(call_edges)

    orphaned = []
    for func_id, info in functions.items():
        if func_id not in connected_funcs:
            orphaned.append(build_function_node(func_id, info))

    # Sort by module then name for easier review
    orphaned.sort(key=lambda x: (x["module"] or "", x["name"] or ""))
    return orphaned


def deduplicate_edges(call_edges: List[Dict]) -> List[Dict]:
    """Deduplicate edges and add call counts (Issue #281: extracted)."""
    call_counts = {}
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        call_counts[key] = call_counts.get(key, 0) + 1

    unique_edges = []
    seen_edges = set()
    for edge in call_edges:
        key = (edge["from"], edge["to"])
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(
                {
                    "from": edge["from"],
                    "to": edge["to"],
                    "to_name": edge["to_name"],
                    "resolved": edge["resolved"],
                    "count": call_counts[key],
                }
            )
    return unique_edges


def calculate_metrics(unique_edges: List[Dict]) -> tuple:
    """Calculate call metrics and top callers/callees (Issue #281: extracted)."""
    outgoing_calls = {}
    incoming_calls = {}
    for edge in unique_edges:
        outgoing_calls[edge["from"]] = outgoing_calls.get(edge["from"], 0) + edge["count"]
        if edge["resolved"]:
            incoming_calls[edge["to"]] = incoming_calls.get(edge["to"], 0) + edge["count"]

    top_callers = sorted(
        [{"function": k, "calls": v} for k, v in outgoing_calls.items()],
        key=lambda x: x["calls"],
        reverse=True,
    )[:10]

    top_called = sorted(
        [{"function": k, "calls": v} for k, v in incoming_calls.items()],
        key=lambda x: x["calls"],
        reverse=True,
    )[:10]

    return top_callers, top_called
