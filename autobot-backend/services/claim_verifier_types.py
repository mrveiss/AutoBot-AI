# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Result types of the claim verifier's RAG and research-agent legs.

Split out of ``services/claim_verifier.py`` (#16665) so that grandfathered module does not grow;
``services.claim_verifier`` re-exports them.
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List

from services.knowledge_grounding_models import KBSource


class ResearchStatus(str, Enum):  # noqa: status-shape  (moved verbatim from claim_verifier.py)
    """Status from research agent investigation."""

    FOUND = "found"
    NOT_FOUND = "not_found"
    CONFLICTING = "conflicting"
    TIMEOUT = "timeout"


@dataclass
class RAGResult:
    """Result from KB RAG search."""

    fact: str
    matches: List[KBSource]
    confidence: float
    search_time_ms: float


@dataclass
class ResearchAgentResult:
    """Result from research agent investigation."""

    claim: str
    fact: str | None
    status: ResearchStatus
    url: str | None = None
    confidence: float = 0.0
    timestamp: float = field(default_factory=time.time)
    research_time_ms: float = 0.0
