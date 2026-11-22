# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#17888: agent-search limit bounds come from the shared search defaults, not a matching literal."""

import ast
import inspect

from autobot_shared.ssot_constants import QueryDefaults
from llc.api import companies


def _limit_query_call() -> ast.Call:
    tree = ast.parse(inspect.getsource(companies))
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "search_agents")
    args = handler.args.args
    offset = len(args) - len(handler.args.defaults)
    return handler.args.defaults[[a.arg for a in args].index("limit") - offset]


def test_effective_limit_values_are_unchanged():
    assert QueryDefaults.DEFAULT_TOP_K == 10
    assert QueryDefaults.MAX_SEARCH_LIMIT == 100


def test_limit_bounds_are_bound_to_the_shared_attributes():
    call = _limit_query_call()
    assert ast.unparse(call.args[0]) == "QueryDefaults.DEFAULT_TOP_K"
    le = next(kw.value for kw in call.keywords if kw.arg == "le")
    assert ast.unparse(le) == "QueryDefaults.MAX_SEARCH_LIMIT"


def test_no_local_agent_search_limit_constants():
    assert not hasattr(companies, "_AGENT_SEARCH_DEFAULT_LIMIT")
    assert not hasattr(companies, "_AGENT_SEARCH_MAX_LIMIT")


def test_contrast_a_literal_is_detected():
    call = ast.parse("Query(10, ge=1, le=100)").body[0].value
    assert ast.unparse(call.args[0]) != "QueryDefaults.DEFAULT_TOP_K"
