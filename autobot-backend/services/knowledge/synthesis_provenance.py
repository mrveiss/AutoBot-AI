# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Synthesis provenance log — records each KnowledgeSynthesizer run to a Redis stream.

Issue #4567: Add synthesis provenance log so operators can audit which source
documents and LLM models produced which insight IDs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

_STREAM_KEY = "kb:synthesis:log"


class SynthesisProvenanceLog:
    """Append-only provenance log for KnowledgeSynthesizer runs."""

    async def log_run(
        self,
        run_id: str,
        source_docs: List[str],
        synthesis_ids: List[str],
        llm_model: str,
        prompt_template: str,
        duration_ms: int,
    ) -> None:
        """Append a provenance entry to the Redis stream.

        Args:
            run_id: Unique identifier for this synthesis run.
            source_docs: List of source document IDs used as input.
            synthesis_ids: List of insight/synthesis IDs produced.
            llm_model: Name/identifier of the LLM model used.
            prompt_template: Name or key of the prompt template used.
            duration_ms: Total synthesis duration in milliseconds.
        """
        entry: Dict[str, Any] = {
            "run_id": run_id,
            "source_docs": json.dumps(source_docs),
            "synthesis_ids": json.dumps(synthesis_ids),
            "llm_model": llm_model,
            "prompt_template": prompt_template,
            "ran_at": datetime.now(timezone.utc).isoformat(),
            "duration_ms": str(duration_ms),
        }
        try:
            redis = await get_async_redis_client(database="main")
            await redis.xadd(_STREAM_KEY, entry)
            logger.debug("Provenance logged for run %s (%d insights)", run_id, len(synthesis_ids))
        except Exception:
            logger.exception("Failed to write provenance log for run %s", run_id)

    async def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return the most recent provenance entries.

        Args:
            limit: Maximum number of entries to return (newest first).

        Returns:
            List of provenance dicts with deserialized fields.
        """
        try:
            redis = await get_async_redis_client(database="main")
            raw_entries = await redis.xrevrange(_STREAM_KEY, count=limit)
        except Exception:
            logger.exception("Failed to read provenance log")
            return []

        results = []
        for _entry_id, fields in raw_entries:
            entry = {
                k.decode("utf-8") if isinstance(k, bytes) else k: (
                    v.decode("utf-8") if isinstance(v, bytes) else v
                )
                for k, v in fields.items()
            }
            for list_field in ("source_docs", "synthesis_ids"):
                if list_field in entry:
                    try:
                        entry[list_field] = json.loads(entry[list_field])
                    except (json.JSONDecodeError, TypeError):
                        entry[list_field] = []
            if "duration_ms" in entry:
                try:
                    entry["duration_ms"] = int(entry["duration_ms"])
                except (ValueError, TypeError):
                    pass
            results.append(entry)
        return results
