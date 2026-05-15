# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Pipeline Package - Extract, Cognify, Load (ECL) Framework.

Issue #759: Knowledge Pipeline Foundation.

This package provides a modular pipeline framework for processing documents
through three stages:

1. **Extract**: Parse and chunk documents, extract metadata
2. **Cognify**: LLM-based semantic enrichment (entities, relationships, events)
3. **Load**: Persist to storage backends (Redis, ChromaDB, Memory Graph)

Package Structure:
- models/: Pydantic data models (Chunk, Entity, Relationship, Event, Summary)
- base.py: Abstract base classes (BaseExtractor, BaseCognifier, BaseLoader)
- registry.py: Task registration and lookup
- runner.py: Pipeline orchestration
- config.py: Configuration loading and defaults
- extractors/: Extract stage implementations
- cognifiers/: Cognify stage implementations (future)
- loaders/: Load stage implementations (future)

Usage:
    from knowledge.pipeline import (
        PipelineRunner,
        PipelineContext,
        get_default_config
    )

    config = get_default_config()
    runner = PipelineRunner(config)

    context = PipelineContext(
        document_id=doc_id,
        user_id=user_id,
        pipeline_name="knowledge_enrichment"
    )

    result = await runner.run(document_text, context)
"""

from .base import (
    BaseCognifier,
    BaseExtractor,
    BaseLoader,
    PipelineContext,
    PipelineResult,
)
from .config import get_default_config, load_pipeline_config
from .models import (
    Entity,
    EntityType,
    EventType,
    ProcessedChunk,
    Relationship,
    RelationType,
    Summary,
    SummaryLevel,
    TemporalEvent,
    TemporalType,
)
from .registry import TaskRegistry
from .runner import PipelineRunner

__all__ = [
    # Base classes
    "PipelineContext",
    "PipelineResult",
    "BaseExtractor",
    "BaseCognifier",
    "BaseLoader",
    # Registry
    "TaskRegistry",
    # Runner
    "PipelineRunner",
    # Config
    "load_pipeline_config",
    "get_default_config",
    # Models
    "ProcessedChunk",
    "Entity",
    "EntityType",
    "Relationship",
    "RelationType",
    "TemporalEvent",
    "TemporalType",
    "EventType",
    "Summary",
    "SummaryLevel",
]
