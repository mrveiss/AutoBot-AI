# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request schema of the multi-source knowledge graph (#20945; split out of schemas_knowledge.py)."""

from typing import List

from pydantic import BaseModel, Field

from constants.rag_graph_constants import RAG_GRAPH_TRAVERSAL_DEPTH
from knowledge.graph_limits import GRAPH_MAX_OFFSET

#: A facts-scan cursor: ``<raw position>:<readable facts already returned from that batch>``.
CURSOR_PATTERN = r"^\d{1,9}:\d{1,6}$"


class GraphRequest(BaseModel):
    """Request model for multi-source knowledge graph."""

    max_facts: int = Field(50, ge=1, le=200, description="Facts per page (page through with offset)")
    offset: int = Field(
        0,
        ge=0,
        le=GRAPH_MAX_OFFSET,
        description="Facts and bucket records to skip, so a client can page to every one the caller may read (#20945)",
    )
    cursor: str | None = Field(
        None,
        pattern=CURSOR_PATTERN,
        description=(
            "Facts only: the `cursor` of the previous response's facts section. The scan resumes there, so every "
            "readable fact is reachable however deep the listing is; `offset` then pages bucket records only (#20945)"
        ),
    )
    include_buckets: bool = Field(True, description="Include one section per non-fact knowledge bucket (#20945)")
    max_depth: int = Field(RAG_GRAPH_TRAVERSAL_DEPTH, ge=1, le=3, description="Maximum relation depth")
    include_categories: bool = Field(True, description="Include category nodes")
    include_relations: bool = Field(True, description="Include fact relations")
    category_filter: str | None = Field(None, description="Filter by category path")


class GraphSection(BaseModel):
    """Visible total vs this page of one graph section (the facts, or one knowledge bucket)."""

    key: str
    label: str
    total: int | None = Field(None, description="Records the caller may read (a lower bound when truncated)")
    returned: int = Field(description="Records on this page")
    limited: bool = Field(description="True while readable records remain past this page")
    truncated: bool = Field(False, description="True when the scan cap cut the listing short")
    budget_exhausted: bool = Field(
        False, description="True when the per-request scan budget ended before a readable record or the end of data"
    )
    failed: bool = Field(False, description="True when the section's source could not be read; total is unknown")
    cursor: str | None = Field(None, description="Facts section only: pass as `cursor` to continue the scan")


class GraphStats(BaseModel):
    """Counts of one multi-source graph response."""

    sections: List[GraphSection] = Field(default_factory=list)
    total_entities: int = 0
    total_relations: int = 0
    categories: int = 0
    facts: int = 0
