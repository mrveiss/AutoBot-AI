# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request body for starting a resumable knowledge upload (#19713)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    total_size: int = Field(gt=0)
    target: Literal["document", "transcript"]
    title: str = Field(default="", max_length=500)
    category: str = Field(default="uploads", max_length=100)
    tags: list[Annotated[str, Field(max_length=50)]] = Field(default_factory=list, max_length=20)
    whisper_model: str = Field(default="base", pattern=r"^[a-z0-9._-]{1,20}$")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
