# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Decode an agent's stored history records (#21381, #21270)."""

import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


def parse_history_records(agent_id: str, raw: List[Any]) -> List[Dict[str, Any]]:
    """JSON-decode *raw*; unparsable records are skipped and counted in ONE warning (agent id, no content)."""
    records: List[Dict[str, Any]] = []
    skipped = 0
    for item in raw:
        try:
            records.append(json.loads(item))
        except (TypeError, ValueError):
            skipped += 1
    if skipped:
        logger.warning("Skipped %d unparsable history record(s) for agent %r", skipped, agent_id)
    return records
