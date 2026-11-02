# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request body for starting a resumable knowledge upload (#19713)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    total_size: int = Field(gt=0)
    target: Literal["document", "transcript"]
    title: str = Field(default="", max_length=500)
    category: str = Field(default="uploads", max_length=100)
    tags: list[str] = Field(default_factory=list, max_length=20)
    whisper_model: str = Field(default="base", max_length=20)
    language: str | None = Field(default=None, max_length=10)
