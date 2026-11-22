# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20761: a non-ASCII credential is a 401 over HTTP, never a 500."""

from unittest.mock import patch

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from monitoring import prometheus_scrape_auth as mod

_TOKEN = "t" * 32  # pragma: allowlist secret


@pytest.fixture
def client():
    app = FastAPI()

    @app.get("/metrics", dependencies=[Depends(mod.require_scrape_token)])
    def metrics() -> dict:
        return {"ok": True}

    with patch.object(mod, "ssot_config") as cfg:
        cfg.misc.prometheus_scrape_token = _TOKEN
        yield TestClient(app, raise_server_exceptions=False)


def _get(client, token: str):
    return client.get("/metrics", headers={"Authorization": b"Bearer " + token.encode("utf-8")})


def test_non_ascii_token_is_401(client) -> None:
    assert _get(client, "é" * 32).status_code == 401


def test_ascii_mismatch_is_401(client) -> None:
    assert _get(client, "x" * 32).status_code == 401


def test_correct_token_passes(client) -> None:
    assert _get(client, _TOKEN).status_code == 200
