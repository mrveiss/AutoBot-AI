# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Per-query context tracker preventing redundant chunk reads (#1994, #2005)."""

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class ContextTracker:
    """Tracks which chunks have been seen in a query session."""

    def __init__(self, query_session_id: str, token_budget: int = 4096):
        self.query_session_id = query_session_id
        self.token_budget = token_budget
        self._seen_chunk_ids: set[str] = set()
        self._tokens_used: int = 0

    @property
    def tokens_remaining(self) -> int:
        return max(0, self.token_budget - self._tokens_used)

    def filter_unseen(self, chunks: list[dict]) -> list[dict]:
        """Return only chunks not yet seen in this session."""
        return [c for c in chunks if c.get("chunk_id") not in self._seen_chunk_ids]

    def record(self, chunk_ids: list[str], tokens: int) -> None:
        """Mark chunks as seen and update token budget."""
        self._seen_chunk_ids.update(chunk_ids)
        self._tokens_used += tokens

    def summary(self) -> dict:
        """Return session summary for logging/debugging."""
        return {
            "session_id": self.query_session_id,
            "chunks_seen": len(self._seen_chunk_ids),
            "tokens_used": self._tokens_used,
            "tokens_remaining": self.tokens_remaining,
        }
