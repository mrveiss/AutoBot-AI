# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Request schema of the multi-source knowledge graph (#20945; split out of schemas_knowledge.py)."""

from pydantic import BaseModel, Field

from constants.rag_graph_constants import RAG_GRAPH_TRAVERSAL_DEPTH


class GraphRequest(BaseModel):
    """Request model for multi-source knowledge graph."""

    max_facts: int = Field(50, ge=1, le=200, description="Facts per page (page through with offset)")
    offset: int = Field(0, ge=0, description="Facts to skip, so a client can page to every fact (#20945)")
    include_buckets: bool = Field(True, description="Include one section per non-fact knowledge bucket (#20945)")
    max_depth: int = Field(RAG_GRAPH_TRAVERSAL_DEPTH, ge=1, le=3, description="Maximum relation depth")
    include_categories: bool = Field(True, description="Include category nodes")
    include_relations: bool = Field(True, description="Include fact relations")
    category_filter: str | None = Field(None, description="Filter by category path")
