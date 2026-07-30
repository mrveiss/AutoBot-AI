# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Data shapes for the /research endpoint (#12622).

Kept separate from ``orchestrator.py`` so the wire contract (request/response
+ internal claim/fact records) can be imported without pulling in the LLM /
fetch / KB dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    """``POST /research`` request body."""

    question: str = Field(..., min_length=3, max_length=2000)
    options: Dict[str, Any] = Field(default_factory=dict)


class Citation(BaseModel):
    """One source citation backing a synthesized statement."""

    fact_id: str
    source_url: str = ""
    source_doc_id: str = ""


class ResearchFactOut(BaseModel):
    """A KB fact produced or reused by this research run."""

    fact_id: str
    content: str
    source_url: str = ""
    confidence: float = 0.0


class ResearchResponse(BaseModel):
    """``POST /research`` response body — the full contract from #12622."""

    answer: str
    citations: List[Citation] = Field(default_factory=list)
    facts: List[ResearchFactOut] = Field(default_factory=list)
    # Phase 0 has no N-source corroborator (#12623 lands it) so this is
    # structurally present but always empty until Phase 1's corroborator can
    # populate it — never a silently-dropped feature.
    contradictions: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = 0.0
    sources_fetched: int = 0
    facts_stored: int = 0


@dataclass
class ExtractedClaim:
    """One atomic claim extracted from a fetched page, pre-KB-storage."""

    content: str
    confidence: float
    source_url: str
    source_doc_id: str


@dataclass
class StoredFact:
    """A claim after landing in the KB (new or deduped to an existing fact)."""

    fact_id: str
    content: str
    confidence: float
    source_url: str
    source_doc_id: str
    is_new: bool


@dataclass
class ResearchBudget:
    """Hard bounds for one orchestrator run (design doc §4.1 / §8 D5)."""

    max_sources: int
    max_content_chars: int
    fetch_timeout_seconds: float
    truncated_sources: List[str] = field(default_factory=list)
