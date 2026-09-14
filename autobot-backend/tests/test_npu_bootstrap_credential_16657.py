# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16657 (owner decision 2026-09-13, in #16627): the unauthenticated NPU bootstrap
returns no Redis credential; the admin-gated pair and repair pushes carry the
password together with its ACL username.

Read from the source with ``ast`` so the payload shapes are pinned without importing
the router.
"""

import ast
from pathlib import Path

_NPU_WORKERS = Path(__file__).resolve().parents[1] / "api" / "npu_workers.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(_NPU_WORKERS.read_text(encoding="utf-8"))
    return next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == name)


def _keys(node: ast.Dict) -> set[str]:
    return {k.value for k in node.keys if isinstance(k, ast.Constant)}


def _redis_block(function_name: str) -> set[str]:
    for node in ast.walk(_function(function_name)):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and key.value == "redis" and isinstance(value, ast.Dict):
                    return _keys(value)
    raise AssertionError(f"{function_name} builds no 'redis' block")


def test_the_unauthenticated_bootstrap_returns_no_redis_credential():
    returned = [n.value for n in ast.walk(_function("_build_worker_redis_config")) if isinstance(n, ast.Return)]
    assert len(returned) == 1 and isinstance(returned[0], ast.Dict)
    keys = _keys(returned[0])
    assert {"host", "port", "db"} <= keys
    assert "password" not in keys and "username" not in keys


def test_the_pair_and_repair_pushes_send_the_username_with_the_password():
    for function_name in ("_build_pairing_config", "_generate_repair_bootstrap_config"):
        assert {"username", "password"} <= _redis_block(function_name), function_name


#: A stand-in, not a credential; the point is only that it never appears in a response.
_SAMPLE = "bootstrap-sample-value-16657"  # pragma: allowlist secret


def test_calling_the_bootstrap_endpoint_returns_no_redis_password(monkeypatch):
    """#16657 AC1: the unauthenticated endpoint itself, called over HTTP, carries no Redis password.

    Unlike the AST checks above, this drives the real router over HTTP. Today's builders never
    read ``config.redis.password``, so the sample is a forward guard: a builder that re-adds a
    credential sourced from the config would fail here.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from api.npu_workers import router
    from autobot_shared.ssot_config import config

    monkeypatch.setattr(config.redis, "password", _SAMPLE)
    app = FastAPI()
    app.include_router(router)

    response = TestClient(app).post(
        "/npu/workers/bootstrap", json={"worker_id": "auto", "platform": "windows", "url": "http://worker:8081"}
    )

    assert response.status_code == 200
    assert _SAMPLE not in response.text
    assert "password" not in response.json()["config"]["redis"]
