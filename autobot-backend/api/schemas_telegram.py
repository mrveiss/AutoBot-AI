# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Telegram bot configuration schemas (MVA-2074, #19010).

Split out of ``api/schemas_system.py``, which is frozen at its grandfathered
size and may not grow to take the ingest-mode field.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class TelegramBotConfigRequest(BaseModel):
    """Request to configure Telegram bot."""

    bot_token: str = Field(..., description="Telegram Bot API token")
    webhook_url: Optional[str] = Field(None, description="Webhook URL (optional)")
    ingest_mode: Literal["webhook", "polling"] = Field(
        "webhook",
        description="How updates arrive: a public webhook, or outbound getUpdates polling (#19010)",
    )

    @model_validator(mode="after")
    def _polling_takes_no_webhook(self) -> "TelegramBotConfigRequest":
        if self.ingest_mode == "polling" and self.webhook_url:
            raise ValueError("webhook_url must be empty in polling ingest mode")
        return self


class TelegramBotConfigResponse(BaseModel):
    """Response for Telegram bot configuration."""

    status: str
    message: str
    webhook_url: Optional[str] = None
    ingest_mode: Optional[Literal["webhook", "polling"]] = None
