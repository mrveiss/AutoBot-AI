# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Schemas for the OAuth bundle strip proposal API (#13630). Ids and counts only, never values."""

from pydantic import BaseModel, Field


class OAuthBundleStripPreviewResponse(BaseModel):
    """Dry run. ``outcomes``: outcome -> {provider -> count}; ``stripped`` means 'would be stripped'.

    ``bundle_ids``: outcome -> record ids of the stored OAuth bundles (ids, never values).
    """

    outcomes: dict[str, dict[str, int]]
    bundle_ids: dict[str, list[str]]


class OAuthBundleStripRequest(BaseModel):
    """Propose the strip. A backup reference (snapshot / export id) is mandatory."""

    backup_reference: str = Field(min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=2000)


class OAuthBundleStripRequestResponse(BaseModel):
    approval_id: str
    status: str
    action: str
