# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared media-generation Pydantic schemas (GH#12710).

`ProviderStatus`/`ProvidersResponse` were byte-identical duplicates in
api/image_generation.py and api/video_generation.py (provider-availability
listing for the `GET /providers` endpoints). Single-sourced here so both
routers import the same model instead of maintaining two copies.
"""

from typing import List, Optional

from pydantic import BaseModel


class ProviderStatus(BaseModel):
    """Availability of a single media-generation provider (image or video)."""

    name: str
    available: bool
    reason: Optional[str] = None


class ProvidersResponse(BaseModel):
    """Response for GET /providers — list of provider availability statuses."""

    providers: List[ProviderStatus]
