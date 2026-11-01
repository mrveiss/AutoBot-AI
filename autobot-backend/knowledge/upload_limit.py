# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one limit on a knowledge file upload (#19712); the frontend reads it from the backend."""

from __future__ import annotations

from pydantic import BaseModel

from autobot_shared.env_utils import env_int

MAX_FILE_SIZE_MB: int = env_int("AUTOBOT_KB_UPLOAD_MAX_MB", 10)
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024


class KnowledgeUploadLimitResponse(BaseModel):
    max_mb: int
