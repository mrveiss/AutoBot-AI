# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The worker's get_http_client must match the shared one it may import (#12656).

`core/npu_integration.py` imports `get_http_client` from `autobot_shared` and
falls back to a locally-defined one when that import fails. The two disagreed:
the shared function is `def`, the fallback was `async def`, and the single call
site did `await get_http_client()`.

That call site can only be right for one of them. Since the worker declares
`-e ../autobot_shared` in its requirements, the import normally succeeds and
binds the **sync** function — so awaiting it raised
`TypeError: object HTTPClientManager can't be used in 'await' expression`
and NPU client initialisation worked only in the degraded fallback path.

Nothing caught it because the two definitions live in forked copies of the same
module and no test exercised the imported branch. These tests pin the contract
from both directions.
"""

import ast
import inspect
from pathlib import Path

import pytest

_WORKER_SRC = Path(__file__).resolve().parent / "npu_integration.py"
_SHARED_SRC = Path(__file__).resolve().parents[2] / "autobot_shared" / "http_client.py"


def _is_async_def(source_path: Path, name: str) -> bool:
    """True when *name* is declared `async def` anywhere in *source_path*."""
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return True
    return False


def _is_sync_def(source_path: Path, name: str) -> bool:
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return True
    return False


def test_shared_get_http_client_is_sync():
    """The contract both sides must agree on — asserted, not assumed."""
    assert _is_sync_def(_SHARED_SRC, "get_http_client")
    assert not _is_async_def(_SHARED_SRC, "get_http_client")


def test_worker_fallback_matches_the_shared_signature():
    """A fallback that differs in async-ness makes the call site unfixable."""
    assert _is_sync_def(_WORKER_SRC, "get_http_client"), "fallback must be `def`, matching autobot_shared"
    assert not _is_async_def(_WORKER_SRC, "get_http_client")


def test_call_sites_do_not_await_it():
    """`await` on the imported (sync) function is a TypeError at runtime."""
    source = _WORKER_SRC.read_text(encoding="utf-8")

    assert "await get_http_client()" not in source


@pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "autobot_shared" / "http_client.py").exists(),
    reason="autobot_shared not present in this checkout",
)
def test_shared_function_is_not_a_coroutine_function_at_runtime():
    """Belt and braces: the AST check above could pass on a re-exported alias."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from autobot_shared.http_client import get_http_client

    assert not inspect.iscoroutinefunction(get_http_client)
