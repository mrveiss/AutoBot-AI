# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Which embedding model the knowledge base uses at startup (#620, #19377).

A model already stamped on stored facts wins: those vectors were made with it, and a query
embedded with another model cannot be compared with them. When it differs from the active
model (``autobot_shared.embedding_model.active_embedding_model``, which includes the user's
override) that is said loudly -- only the rebuild-and-cutover flow (#19379), which re-indexes,
may change it. With nothing stored, the active model is used.
"""

from __future__ import annotations

from autobot_shared.embedding_model import active_embedding_model
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def resolve_kb_embedding_model(stored_model: str | None) -> str:
    """The model the knowledge base embeds with, given the one found on stored facts."""
    active = active_embedding_model()
    if not stored_model:
        logger.info("Using embedding model from config: %s", active)
        return active
    if stored_model != active:
        logger.warning(
            "Knowledge base keeps the stored embedding model %r, not the active %r: the stored "
            "vectors were made with it. Switch through the embedding-model switch (#19379), "
            "which re-indexes, to change it.",
            stored_model,
            active,
        )
    else:
        logger.info("Using stored embedding model for consistency: %s", stored_model)
    return stored_model
