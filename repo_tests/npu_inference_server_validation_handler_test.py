# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""npu_inference_server.py's duplicated 422 handler never echoes the payload
(#16428 security review).

This container has no NPU runtime or `structlog` guaranteed on this checkout
and no autobot_shared either, so `npu_inference_server.py` itself cannot be
imported here. Extracts the handler function's real source by AST line range
instead of retyping it -- this fails the moment the duplicate drifts from
what the file actually contains, which a hand-copied mirror function would
not catch.
"""

from __future__ import annotations

import ast
from pathlib import Path

from repo_tests._paths import repo_root

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

#: Lives in repo_tests/ (#17134): the tree this server sits in is in no pytest
#: testpaths entry and in no CI pytest invocation, so a test placed next to it
#: would never run -- the same silence collection_coverage_test.py exists to
#: remove. Same reasoning, verbatim, as repo_tests/infra_script_imports_resolve_test.py.
_SERVER_PATH = repo_root() / "autobot-infrastructure/autobot-npu-worker/docker/npu_inference_server.py"
_LEAKED_MARKER = "not-a-real-value-but-must-never-appear-in-a-422"  # pragma: allowlist secret


def _extract_handler_source() -> str:
    source = _SERVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_validation_error_without_input":
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError(
        "_validation_error_without_input not found in npu_inference_server.py -- duplicate was removed?"
    )


class _PasswordLikeRequest(BaseModel):
    password: str = Field(..., min_length=8)


@pytest.fixture
def client() -> TestClient:
    namespace: dict = {
        "Request": __import__("fastapi").Request,
        "RequestValidationError": RequestValidationError,
        "JSONResponse": JSONResponse,
    }
    exec(compile(_extract_handler_source(), str(_SERVER_PATH), "exec"), namespace)  # noqa: S102
    handler = namespace["_validation_error_without_input"]

    app = FastAPI()
    app.add_exception_handler(RequestValidationError, handler)

    @app.post("/account")
    async def _create(body: _PasswordLikeRequest):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_the_duplicated_handler_never_echoes_a_short_password(client: TestClient):
    response = client.post("/account", json={"password": _LEAKED_MARKER[:4]})

    assert response.status_code == 422
    assert _LEAKED_MARKER[:4] not in response.text
    assert "input" not in response.text
    assert "ctx" not in response.text
