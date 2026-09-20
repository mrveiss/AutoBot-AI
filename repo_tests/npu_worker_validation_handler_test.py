# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""npu_worker.py's duplicated 422 handler never echoes the payload
(#16428 security review).

`PairRequest.config: Dict[str, Any]` (`api_schemas.py`) can carry pairing
secrets the main host sends. This module ships inside the standalone Windows
PyInstaller package (confirmed the live one via `installer/npu_worker.spec`
and `scripts/install.ps1`, both of which name only this copy -- a second,
differently-shaped `npu_worker.py` under
`autobot-infrastructure/shared/scripts/utilities/` is referenced by no
deploy manifest found and is tracked separately, #17112) and has real,
heavy sibling-module dependencies (OpenVINO, ONNX Runtime) not guaranteed
here, so it cannot be imported directly. Extracts the handler function's
real source by AST line range instead of retyping it -- this fails the
moment the duplicate drifts from what the file actually contains, which a
hand-copied mirror function would not catch.
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
_SERVER_PATH = repo_root() / "autobot-npu-worker/resources/windows-npu-worker/app/npu_worker.py"
_LEAKED_MARKER = "not-a-real-value-but-must-never-appear-in-a-422"  # pragma: allowlist secret


def _extract_handler_source() -> str:
    source = _SERVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_validation_error_without_input":
            return "\n".join(lines[node.lineno - 1 : node.end_lineno])
    raise AssertionError("_validation_error_without_input not found in npu_worker.py -- duplicate was removed?")


class _PairRequestLike(BaseModel):
    """Mirrors PairRequest's shape closely enough to reproduce the exact
    failure mode without importing api_schemas.py (which imports worker
    modules with the same heavy OpenVINO/ONNX dependencies)."""

    worker_id: str
    main_host: str
    config: dict | None = Field(None)


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

    @app.post("/pair")
    async def _pair(body: _PairRequestLike):
        return {"ok": True}

    return TestClient(app, raise_server_exceptions=False)


def test_the_duplicated_handler_never_echoes_the_pairing_config(client: TestClient):
    """The concrete case c0's review named: config carries pairing secrets."""
    response = client.post(
        "/pair",
        # main_host omitted (required) -- guarantees a validation error
        # regardless of Pydantic's own coercion rules, while config (with
        # the secret) is still part of the submitted, echo-able body.
        json={"worker_id": "w-1", "config": {"pairing_secret": _LEAKED_MARKER}},
    )

    assert response.status_code == 422
    assert _LEAKED_MARKER not in response.text
    assert "input" not in response.text
    assert "ctx" not in response.text
