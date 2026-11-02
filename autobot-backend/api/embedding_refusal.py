# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Turn an embedding refusal into a visible HTTP failure (#18185)."""

from fastapi import HTTPException

from autobot_shared.embedding_model import EmbeddingUnavailableError


def reraise_http_or_refusal(exc: Exception) -> None:
    """First call in a route's broad ``except``: an HTTPException passes through, a refusal is a 503.

    A refused query space is a failed search with a reason, never "no results" and never a bare 500.
    """
    if isinstance(exc, HTTPException):
        raise exc
    if isinstance(exc, EmbeddingUnavailableError):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
