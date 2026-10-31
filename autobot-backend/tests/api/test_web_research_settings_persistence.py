# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""/api/web-research settings are saved where the researcher reads them and applied live (#19226).

Before #19226, PUT /settings wrote the limits to ``agents.research.*`` (read by nothing at
runtime) and dropped the privacy flags. /enable and /disable imported a module that does not
exist, so they switched the live researcher, then failed with 500 before saving.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import config
from agents.web_researcher import WebResearcher
from api.web_research_settings import SAVED_NOT_APPLIED, router
from services import web_research_config
from services.config_service import ConfigService
from services.web_research_config_test import FakeConfigManager


@pytest.fixture
def manager(monkeypatch) -> FakeConfigManager:
    fake = FakeConfigManager()
    monkeypatch.setattr(config, "config_manager", fake, raising=False)
    monkeypatch.setattr(ConfigService, "clear_cache", staticmethod(lambda: None))
    return fake


def _client(researcher) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.state.web_researcher = researcher
    return TestClient(app)


def test_put_saves_every_sent_field_and_get_reads_it_back(manager):
    client = _client(researcher=None)
    sent = {"max_results": 9, "anonymize_requests": False, "daily_limit": 20, "preferred_method": "advanced"}
    response = client.put("/api/web-research/settings", json=sent)
    assert response.status_code == 200
    assert {k: response.json()["settings"][k] for k in sent} == sent
    got = client.get("/api/web-research/settings").json()["settings"]
    assert {k: got[k] for k in sent} == sent
    assert got["timeout_seconds"] == web_research_config.DEFAULTS["timeout_seconds"]


def test_put_applies_saved_limits_to_the_running_researcher(manager):
    researcher = WebResearcher({"max_results": 5, "timeout_seconds": 30})
    client = _client(researcher)
    sent = {"max_results": 11, "timeout_seconds": 60, "rate_limit_requests": 9, "rate_limit_window": 120}
    assert client.put("/api/web-research/settings", json=sent).status_code == 200
    assert researcher.max_results_default == 11
    assert researcher.timeout_seconds == 60
    assert (researcher._rl_max_requests, researcher._rl_window_seconds) == (9, 120)


@pytest.mark.parametrize(
    "body", [{"max_results": 0}, {"timeout_seconds": 500}, {"preferred_method": "magic"}, {"x": 1}]
)
def test_put_refuses_an_out_of_range_or_unknown_setting(manager, body):
    response = _client(researcher=None).put("/api/web-research/settings", json=body)
    assert response.status_code == 422
    assert manager.saves == 0


@pytest.mark.parametrize("path,enabled", [("/api/web-research/enable", True), ("/api/web-research/disable", False)])
def test_enable_and_disable_are_saved_and_applied(manager, path, enabled):
    researcher = MagicMock(enabled=enabled)
    researcher.enable_research = AsyncMock(return_value=True)
    researcher.disable_research = AsyncMock(return_value=True)
    response = _client(researcher).post(path)
    assert response.status_code == 200
    assert response.json()["enabled"] is enabled
    assert manager.data["web_research"]["enabled"] is enabled
    assert web_research_config.load_settings(manager)["enabled"] is enabled


def test_a_failed_save_leaves_the_live_researcher_untouched(manager, monkeypatch):
    def broken_save():
        raise OSError("disk full")

    monkeypatch.setattr(manager, "save_settings", broken_save)
    researcher = MagicMock(enabled=True)
    researcher.disable_research = AsyncMock(return_value=True)
    response = _client(researcher).post("/api/web-research/disable")
    assert response.status_code == 500
    researcher.disable_research.assert_not_awaited()


def test_status_reports_the_saved_method_not_a_constant(manager):
    web_research_config.save_settings(manager, {"preferred_method": "api_based"})
    researcher = MagicMock()
    researcher.health_check = AsyncMock(return_value={"enabled": True})
    researcher.get_circuit_breaker_status = MagicMock(return_value={})
    researcher.get_cache_stats = AsyncMock(return_value={"cache_size": 0})
    assert _client(researcher).get("/api/web-research/status").json()["preferred_method"] == "api_based"


def test_put_saved_but_not_applied_live_says_so(manager):
    researcher = MagicMock()
    researcher.apply_settings = MagicMock(side_effect=RuntimeError("researcher busy"))
    response = _client(researcher).put("/api/web-research/settings", json={"max_results": 7})
    assert response.status_code == 200
    assert response.json()["status"] == SAVED_NOT_APPLIED
    assert "after a restart" in response.json()["message"]
    assert manager.data["web_research"]["max_results"] == 7


def test_enable_saved_but_not_applied_live_says_so(manager):
    researcher = MagicMock(enabled=False)
    researcher.enable_research = AsyncMock(side_effect=RuntimeError("researcher busy"))
    response = _client(researcher).post("/api/web-research/enable")
    assert response.status_code == 200
    assert response.json()["status"] == SAVED_NOT_APPLIED
    assert response.json()["enabled"] is False
    assert manager.data["web_research"]["enabled"] is True
