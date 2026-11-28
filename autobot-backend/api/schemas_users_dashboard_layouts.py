# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dashboard layout schemas: one document per user and page (#18242).

Home keeps several named dashboards; Company OS keeps one. Each widget carries its kind,
label, config and its place on the 12-column grid (span 4/6/8/12, height in px). List
order is the visual order.
"""

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field

DASHBOARD_PAGES = ("home", "company-os")
MAX_DASHBOARDS = 16
MAX_WIDGETS = 48
MAX_LAYOUT_BYTES = 64 * 1024
_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}\z"


class DashboardWidget(BaseModel):
    """One widget: its kind, label, config and place on the 12-column grid."""

    id: str = Field(..., pattern=_ID_PATTERN)
    type: str = Field(..., pattern=_ID_PATTERN)
    title: str = Field("", max_length=120)
    span: Literal[4, 6, 8, 12] = 6
    height: int = Field(320, ge=160, le=960, description="Widget height in px")
    props: Dict[str, Any] = Field(default_factory=dict)
    refreshInterval: int | None = Field(None, ge=0, le=86_400_000)


class Dashboard(BaseModel):
    """A named dashboard; widget list order is the visual order."""

    id: str = Field(..., pattern=_ID_PATTERN)
    name: str = Field(..., min_length=1, max_length=120)
    widgets: list[DashboardWidget] = Field(default_factory=list, max_length=MAX_WIDGETS)
    createdAt: int = 0
    updatedAt: int = 0


class DashboardLayout(BaseModel):
    """Every dashboard the user keeps on one page; no dashboards means 'use defaults'."""

    dashboards: list[Dashboard] = Field(default_factory=list, max_length=MAX_DASHBOARDS)
    activeId: str | None = Field(None, pattern=_ID_PATTERN)


class DashboardLayoutData(BaseModel):
    """Data payload for the dashboard layout endpoints."""

    page: str
    layout: DashboardLayout
