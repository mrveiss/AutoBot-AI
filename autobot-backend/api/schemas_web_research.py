# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for api/web_research_settings.py, moved out of schemas_workflows.py (#19226).

The settings models declare every setting the API reads and writes, so the published
OpenAPI contract, and the SLM's generated types, carry the real shape. Defaults and stored
keys live in services/web_research_config.py.
"""

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

WebResearchMethod = Literal["basic", "advanced", "api_based"]


class WebResearchSettings(BaseModel):
    """Every web research setting, as GET /web-research/settings returns it."""

    enabled: bool
    require_user_confirmation: bool
    preferred_method: str
    max_results: int
    timeout_seconds: int
    auto_research_threshold: float
    rate_limit_requests: int
    rate_limit_window: int
    daily_limit: int
    quality_threshold: float
    store_results_in_kb: bool
    filter_adult_content: bool
    anonymize_requests: bool


class WebResearchSettingsUpdate(BaseModel):
    """PUT /web-research/settings body: only the fields sent are changed (#19226)."""

    model_config = {"extra": "forbid"}

    enabled: bool | None = None
    require_user_confirmation: bool | None = None
    preferred_method: WebResearchMethod | None = None
    max_results: int | None = Field(None, ge=1, le=50)
    timeout_seconds: int | None = Field(None, ge=5, le=120)
    auto_research_threshold: float | None = Field(None, ge=0, le=1)
    rate_limit_requests: int | None = Field(None, ge=1, le=100)
    rate_limit_window: int | None = Field(None, ge=10, le=3600)
    daily_limit: int | None = Field(None, ge=1)
    quality_threshold: float | None = Field(None, ge=0, le=1)
    store_results_in_kb: bool | None = None
    filter_adult_content: bool | None = None
    anonymize_requests: bool | None = None


class WebResearchStatusData(BaseModel):
    """Response data for get_research_status."""

    status: str
    enabled: bool
    preferred_method: str | None = None
    health: Dict[str, Any] | None = None
    circuit_breakers: Dict[str, Any] | None = None
    cache_stats: Dict[str, Any] | None = None
    timestamp: str
    message: str | None = None


class WebResearchToggleData(BaseModel):
    """Response data for enable_web_research and disable_web_research."""

    status: str
    message: str
    enabled: bool
    timestamp: str


class WebResearchSettingsData(BaseModel):
    """Response data for get_research_settings."""

    status: str
    settings: WebResearchSettings
    timestamp: str


class WebResearchSettingsUpdateData(BaseModel):
    """Response data for update_research_settings: the full set after the change."""

    status: str
    message: str
    settings: WebResearchSettings
    timestamp: str


class WebResearchTestData(BaseModel):
    """Response data for test_web_research."""

    status: str
    test_query: str
    result: Any | None = None
    error: str | None = None
    timestamp: str


class WebResearchCacheClearData(BaseModel):
    """Response data for clear_research_cache and reset_circuit_breakers."""

    status: str
    message: str
    timestamp: str


class WebResearchUsageStatsData(BaseModel):
    """Response data for get_usage_stats."""

    status: str
    stats: Dict[str, Any]
    timestamp: str
