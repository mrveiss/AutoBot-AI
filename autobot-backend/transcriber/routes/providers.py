# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Transcriber provider selection routes (Issue #10147).

GET  /api/transcriber/providers  — list configured cloud providers + active selection
PATCH /api/transcriber/providers — set the active provider (in-process; doc'd limitation)

Privacy note: never returns API keys or credentials.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from autobot_shared.logging_manager import get_logger
from voice_processing.providers.selection import (
    get_active_provider_id,
    list_available_providers,
    set_active_provider,
)

logger = get_logger(__name__)

router = APIRouter(tags=["transcriber-providers"])


class ProviderInfo(BaseModel):
    id: str
    name: str
    configured: bool
    languages: List[str]


class ProvidersResponse(BaseModel):
    selected: Optional[str]
    providers: List[ProviderInfo]


class SetProviderRequest(BaseModel):
    provider: Optional[str]


@router.get("/providers", response_model=ProvidersResponse)
async def list_providers() -> Dict[str, Any]:
    """List all cloud ASR providers and the currently active selection.

    Only shows metadata (id, name, configured, languages) — never returns keys.
    """
    providers = list_available_providers()
    return {
        "selected": get_active_provider_id(),
        "providers": providers,
    }


@router.patch("/providers")
async def set_provider(body: SetProviderRequest) -> Dict[str, Any]:
    """Set the active cloud ASR provider.

    Persistence limitation: this is in-process only and is lost on restart.
    For persistence across restarts, set TRANSCRIBER_ASR_PROVIDER in the
    backend environment before starting the service.

    Pass {"provider": null} to clear the selection (fall back to local providers).
    """
    try:
        set_active_provider(body.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    logger.info("Cloud ASR provider updated to: %s", body.provider)
    providers = list_available_providers()
    return {
        "selected": get_active_provider_id(),
        "providers": providers,
    }
