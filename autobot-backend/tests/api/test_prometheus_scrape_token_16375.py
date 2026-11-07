# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``/api/metrics/prometheus`` admits only the scrape token (#16375, owner decision 2026-10-12).

No token, a wrong token, a non-Bearer credential, or an unset server token: 401.
The right token: the Prometheus text exposition. The refusal log names the
reason and never the value presented.
"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.prometheus_endpoint as endpoint
import monitoring.prometheus_scrape_auth as scrape_auth

_TOKEN = "scrape-token-for-tests-0123456789"  # nosec B105  # test fixture, not a credential
_PATH = "/api/metrics/prometheus"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(scrape_auth.ssot_config.misc, "prometheus_scrape_token", _TOKEN)
    app = FastAPI()
    app.include_router(endpoint.router, prefix=_PATH)
    return TestClient(app)


def test_the_gate_is_on_the_router() -> None:
    gates = [d.dependency for d in endpoint.router.dependencies]
    assert gates == [scrape_auth.require_scrape_token]


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer wrong-token"},
        {"Authorization": f"Basic {_TOKEN}"},
        {"Authorization": f"Bearer {_TOKEN}x"},
        {"Authorization": "Bearer "},
    ],
    ids=["none", "wrong", "not-bearer", "suffixed", "empty"],
)
def test_a_scrape_without_the_token_is_refused(client, headers) -> None:
    response = client.get(_PATH, headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_the_right_token_gets_metrics(client) -> None:
    response = client.get(_PATH, headers={"Authorization": f"Bearer {_TOKEN}"})
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/plain")


def test_an_unset_server_token_refuses_even_an_empty_credential(client, monkeypatch) -> None:
    monkeypatch.setattr(scrape_auth.ssot_config.misc, "prometheus_scrape_token", "")
    assert client.get(_PATH, headers={"Authorization": "Bearer "}).status_code == 401
    assert client.get(_PATH).status_code == 401


def test_the_compare_is_constant_time(monkeypatch) -> None:
    calls = []
    real = scrape_auth.secrets.compare_digest
    monkeypatch.setattr(scrape_auth.secrets, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    monkeypatch.setattr(scrape_auth.ssot_config.misc, "prometheus_scrape_token", _TOKEN)
    assert scrape_auth.scrape_token_matches(_TOKEN)
    assert calls == [1]


def test_a_refusal_never_logs_the_presented_value(client, caplog) -> None:
    presented = "a-leaked-credential-from-elsewhere"
    with caplog.at_level(logging.DEBUG):
        client.get(_PATH, headers={"Authorization": f"Bearer {presented}"})
        client.get(_PATH, headers={"Authorization": f"Bearer {_TOKEN}"})
    assert presented not in caplog.text
    assert _TOKEN not in caplog.text
