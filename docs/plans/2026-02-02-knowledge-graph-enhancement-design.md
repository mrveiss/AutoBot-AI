# Knowledge Graph Enhancement Design

> **Date**: 2026-02-02
> **Author**: mrveiss
> **Status**: Draft - Pending Implementation

## Executive Summary

This design document outlines four major enhancements to AutoBot's knowledge management system:

1. **ECL Pipeline Architecture** - Modular Extract-Cognify-Load document processing
2. **LLM-Powered Knowledge Graph Generation** - Automatic entity and relationship extraction
3. **Temporal Knowledge & Event Extraction** - Time-aware knowledge with event tracking
4. **Hierarchical Summarization** - Multi-level document summaries

These features transform raw documents into structured, queryable knowledge graphs with temporal awareness and multi-level abstractions.

---

## 1. ECL Pipeline Architecture

### Overview

A plugin-based pipeline system where documents flow through three stages:
- **Extract**: Document classification, chunking, metadata extraction
- **Cognify**: LLM-powered entity, relationship, event, and summary generation
- **Load**: Storage to ChromaDB (vectors), Redis (graph), SQLite (facts)

### Architecture

```
Document Input
      ↓
┌─────────────────────────────────────────┐
│           EXTRACT STAGE                  │
│  • Document Classifier                   │
│  • Semantic Chunker (GPU-accelerated)    │
│  • Metadata Extractor                    │
└─────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────┐
│           COGNIFY STAGE                  │
│  • Entity Extractor (LLM)                │
│  • Relationship Extractor (LLM)          │
│  • Event/Temporal Extractor (LLM)        │
│  • Hierarchical Summarizer (LLM)         │
└─────────────────────────────────────────┘
      ↓
┌─────────────────────────────────────────┐
│            LOAD STAGE                    │
│  • ChromaDB (embeddings)                 │
│  • Redis Memory Graph (relationships)    │
│  • SQLite (facts, metadata)              │
└─────────────────────────────────────────┘
```

### File Structure

```
autobot-user-backend/knowledge/pipeline/
├── __init__.py
├── base.py              # Base classes: BaseExtractor, BaseCognifier, BaseLoader
├── registry.py          # TaskRegistry with plugin decorators
├── runner.py            # PipelineRunner - orchestrates stages
├── config.py            # Pipeline configuration loading
├── extractors/
│   ├── __init__.py
│   ├── document_classifier.py
│   ├── semantic_chunker.py
│   └── metadata_extractor.py
├── cognifiers/
│   ├── __init__.py
│   ├── entity_extractor.py
│   ├── relationship_extractor.py
│   ├── event_extractor.py
│   └── summarizer.py
├── loaders/
│   ├── __init__.py
│   ├── chromadb_loader.py
│   ├── redis_graph_loader.py
│   └── sqlite_loader.py
└── models/
    ├── __init__.py
    ├── chunk.py
    ├── entity.py
    ├── relationship.py
    ├── event.py
    └── summary.py
```

### Configuration Schema

```yaml
# config/pipelines/knowledge_enrichment.yaml
pipeline_name: knowledge_enrichment
stages:
  extract:
    tasks:
      - name: classify_document
        enabled: true
      - name: chunk_text
        config:
          max_tokens: 512
          overlap: 50
          chunker: semantic  # semantic | fixed | sentence
      - name: extract_metadata
        enabled: true

  cognify:
    tasks:
      - name: extract_entities
        model: llama3.2:3b
        batch_size: 50
        confidence_threshold: 0.7
      - name: extract_relationships
        model: llama3.2:3b
        batch_size: 50
      - name: extract_events
        enabled: true
        model: llama3.2:3b
      - name: generate_summaries
        enabled: true
        levels: [chunk, section, document]
        max_words:
          chunk: 50
          section: 150
          document: 300

  load:
    targets:
      - name: chromadb
        collection: knowledge_vectors
        embed_summaries: true
      - name: redis_graph
        database: 0
      - name: sqlite
        table: knowledge_facts
```

### Task Registry Pattern

```python
# autobot-user-backend/knowledge/pipeline/registry.py
from typing import Type, Callable
from functools import wraps

class TaskRegistry:
    """Plugin registry for pipeline tasks."""

    _extractors: dict[str, Type['BaseExtractor']] = {}
    _cognifiers: dict[str, Type['BaseCognifier']] = {}
    _loaders: dict[str, Type['BaseLoader']] = {}

    @classmethod
    def register_extractor(cls, name: str) -> Callable:
        """Decorator to register extractor tasks."""
        def wrapper(task_class: Type['BaseExtractor']) -> Type['BaseExtractor']:
            cls._extractors[name] = task_class
            return task_class
        return wrapper

    @classmethod
    def register_cognifier(cls, name: str) -> Callable:
        """Decorator to register cognifier tasks."""
        def wrapper(task_class: Type['BaseCognifier']) -> Type['BaseCognifier']:
            cls._cognifiers[name] = task_class
            return task_class
        return wrapper

    @classmethod
    def register_loader(cls, name: str) -> Callable:
        """Decorator to register loader tasks."""
        def wrapper(task_class: Type['BaseLoader']) -> Type['BaseLoader']:
            cls._loaders[name] = task_class
            return task_class
        return wrapper

    @classmethod
    def get_task(cls, stage: str, name: str) -> Type:
        """Retrieve a registered task by stage and name."""
        registry = {
            'extract': cls._extractors,
            'cognify': cls._cognifiers,
            'load': cls._loaders
        }
        return registry[stage].get(name)
```

### Base Classes

```python
# autobot-user-backend/knowledge/pipeline/base.py
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator
from pydantic import BaseModel

class PipelineContext(BaseModel):
    """Shared context passed through pipeline stages."""
    document_id: str
    user_id: str
    pipeline_name: str
    config: dict
    metadata: dict = {}

class BaseExtractor(ABC):
    """Base class for extraction tasks."""

    @abstractmethod
    async def process(
        self,
        input_data: Any,
        context: PipelineContext
    ) -> AsyncIterator[Any]:
        """Process input and yield extracted data."""
        pass

class BaseCognifier(ABC):
    """Base class for cognification tasks."""

    @abstractmethod
    async def process(
        self,
        chunks: list[Any],
        context: PipelineContext
    ) -> list[Any]:
        """Process chunks and return enriched data."""
        pass

class BaseLoader(ABC):
    """Base class for loading tasks."""

    @abstractmethod
    async def load(
        self,
        data: list[Any],
        context: PipelineContext
    ) -> None:
        """Load processed data to storage."""
        pass
```

### Pipeline Runner

```python
# autobot-user-backend/knowledge/pipeline/runner.py
import asyncio
from typing import AsyncIterator
import logging

logger = logging.getLogger(__name__)

class PipelineRunner:
    """Orchestrates pipeline execution."""

    def __init__(self, config: dict):
        self.config = config
        self.registry = TaskRegistry()

    async def run(
        self,
        document_path: str,
        context: PipelineContext
    ) -> PipelineResult:
        """Execute the full pipeline."""

        # Extract stage
        extracted_data = []
        for task_config in self.config['stages']['extract']['tasks']:
            if not task_config.get('enabled', True):
                continue
            task = self.registry.get_task('extract', task_config['name'])
            instance = task(task_config.get('config', {}))
            async for item in instance.process(document_path, context):
                extracted_data.append(item)

        # Cognify stage (batch processing)
        cognified_data = {
            'entities': [],
            'relationships': [],
            'events': [],
            'summaries': []
        }

        for task_config in self.config['stages']['cognify']['tasks']:
            if not task_config.get('enabled', True):
                continue
            task = self.registry.get_task('cognify', task_config['name'])
            instance = task(task_config.get('config', {}))
            batch_size = task_config.get('batch_size', 50)

            # Process in batches
            for i in range(0, len(extracted_data), batch_size):
                batch = extracted_data[i:i + batch_size]
                results = await instance.process(batch, context)
                # Route results to appropriate collection
                self._route_cognify_results(results, cognified_data)

        # Load stage
        for target_config in self.config['stages']['load']['targets']:
            loader = self.registry.get_task('load', target_config['name'])
            instance = loader(target_config)
            await instance.load(cognified_data, context)

        return PipelineResult(
            document_id=context.document_id,
            chunks_processed=len(extracted_data),
            entities_extracted=len(cognified_data['entities']),
            relationships_extracted=len(cognified_data['relationships']),
            events_extracted=len(cognified_data['events']),
            summaries_generated=len(cognified_data['summaries'])
        )
```

---

## 2. LLM-Powered Knowledge Graph Generation

### Entity Model

```python
# autobot-user-backend/knowledge/pipeline/models/entity.py
from pydantic import BaseModel, Field
from typing import Literal, Any
from uuid import UUID, uuid4
from datetime import datetime

class Entity(BaseModel):
    """Named entity extracted from documents."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    canonical_name: str  # Normalized form for deduplication
    entity_type: Literal[
        "PERSON",
        "ORGANIZATION",
        "CONCEPT",
        "TECHNOLOGY",
        "LOCATION",
        "EVENT",
        "DOCUMENT"
    ]
    description: str
    properties: dict[str, Any] = {}

    # Source tracking
    source_chunk_ids: list[UUID] = []
    source_document_id: UUID | None = None

    # Quality metrics
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_count: int = 1  # Times extracted (for dedup confidence)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
```

### Relationship Model

```python
# autobot-user-backend/knowledge/pipeline/models/relationship.py
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID, uuid4
from datetime import datetime

class Relationship(BaseModel):
    """Relationship between two entities."""

    id: UUID = Field(default_factory=uuid4)
    source_entity_id: UUID
    target_entity_id: UUID

    relationship_type: Literal[
        # Causal
        "CAUSES", "ENABLES", "PREVENTS", "TRIGGERS",
        # Compositional
        "CONTAINS", "PART_OF", "COMPOSED_OF",
        # Associative
        "RELATES_TO", "SIMILAR_TO", "CONTRASTS_WITH",
        # Temporal
        "PRECEDES", "FOLLOWS", "DURING",
        # Hierarchical
        "IS_A", "INSTANCE_OF", "SUBTYPE_OF",
        # Attribution
        "CREATED_BY", "AUTHORED_BY", "OWNED_BY",
        # Technical
        "IMPLEMENTS", "EXTENDS", "DEPENDS_ON", "USES"
    ]

    description: str  # Natural language description
    bidirectional: bool = False

    # Quality metrics
    confidence: float = Field(ge=0.0, le=1.0)

    # Source tracking
    source_chunk_ids: list[UUID] = []

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Entity Extractor Implementation

```python
# autobot-user-backend/knowledge/pipeline/cognifiers/entity_extractor.py
from typing import Type
import json
from pydantic import BaseModel

from ..base import BaseCognifier, PipelineContext
from ..registry import TaskRegistry
from ..models.entity import Entity
from src.services.llm_service import LLMService

ENTITY_EXTRACTION_PROMPT = """
Analyze the following text and extract all significant named entities.

For each entity, provide:
- name: The exact name as it appears
- entity_type: One of [PERSON, ORGANIZATION, CONCEPT, TECHNOLOGY, LOCATION, EVENT, DOCUMENT]
- description: Brief description of the entity in this context (1-2 sentences)
- properties: Key attributes mentioned as key-value pairs

Focus on:
- People, teams, companies mentioned
- Technical concepts, methodologies, patterns
- Tools, frameworks, programming languages
- Specific locations or systems
- Named events or milestones

Text:
{chunk_text}

Return a JSON array of entities following this schema:
{{
  "entities": [
    {{
      "name": "string",
      "entity_type": "string",
      "description": "string",
      "properties": {{}}
    }}
  ]
}}
"""

@TaskRegistry.register_cognifier("extract_entities")
class EntityExtractor(BaseCognifier):
    """LLM-powered entity extraction from text chunks."""

    def __init__(self, config: dict):
        self.model = config.get('model', 'llama3.2:3b')
        self.confidence_threshold = config.get('confidence_threshold', 0.7)
        self.llm = LLMService(model=self.model)

    async def process(
        self,
        chunks: list[dict],
        context: PipelineContext
    ) -> list[Entity]:
        """Extract entities from a batch of chunks."""

        entities = []

        for chunk in chunks:
            prompt = ENTITY_EXTRACTION_PROMPT.format(
                chunk_text=chunk['content']
            )

            response = await self.llm.generate(
                prompt=prompt,
                response_format="json"
            )

            try:
                extracted = json.loads(response)
                for entity_data in extracted.get('entities', []):
                    entity = Entity(
                        name=entity_data['name'],
                        canonical_name=self._normalize_name(entity_data['name']),
                        entity_type=entity_data['entity_type'],
                        description=entity_data['description'],
                        properties=entity_data.get('properties', {}),
                        source_chunk_ids=[chunk['id']],
                        source_document_id=context.document_id,
                        confidence=0.8  # Base confidence, adjusted by dedup
                    )
                    entities.append(entity)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse entity extraction response")
                continue

        # Deduplicate and merge entities
        merged_entities = self._merge_entities(entities)

        return merged_entities

    def _normalize_name(self, name: str) -> str:
        """Normalize entity name for deduplication."""
        return name.lower().strip()

    def _merge_entities(self, entities: list[Entity]) -> list[Entity]:
        """Merge duplicate entities, boosting confidence."""
        seen: dict[str, Entity] = {}

        for entity in entities:
            key = f"{entity.canonical_name}:{entity.entity_type}"

            if key in seen:
                # Merge: combine sources, boost confidence
                existing = seen[key]
                existing.source_chunk_ids.extend(entity.source_chunk_ids)
                existing.extraction_count += 1
                existing.confidence = min(0.99, existing.confidence + 0.05)

                # Merge properties
                for k, v in entity.properties.items():
                    if k not in existing.properties:
                        existing.properties[k] = v
            else:
                seen[key] = entity

        return list(seen.values())
```

### Relationship Extractor Implementation

```python
# autobot-user-backend/knowledge/pipeline/cognifiers/relationship_extractor.py

RELATIONSHIP_EXTRACTION_PROMPT = """
Given the following text and list of entities, identify relationships between them.

Entities:
{entities_json}

Text:
{chunk_text}

For each relationship found, provide:
- source_entity: Name of the source entity
- target_entity: Name of the target entity
- relationship_type: One of [CAUSES, ENABLES, PREVENTS, TRIGGERS, CONTAINS, PART_OF, COMPOSED_OF, RELATES_TO, SIMILAR_TO, CONTRASTS_WITH, PRECEDES, FOLLOWS, DURING, IS_A, INSTANCE_OF, SUBTYPE_OF, CREATED_BY, AUTHORED_BY, OWNED_BY, IMPLEMENTS, EXTENDS, DEPENDS_ON, USES]
- description: Brief description of the relationship
- bidirectional: true if the relationship works both ways

Return JSON:
{{
  "relationships": [
    {{
      "source_entity": "string",
      "target_entity": "string",
      "relationship_type": "string",
      "description": "string",
      "bidirectional": boolean
    }}
  ]
}}
"""

@TaskRegistry.register_cognifier("extract_relationships")
class RelationshipExtractor(BaseCognifier):
    """LLM-powered relationship extraction."""

    def __init__(self, config: dict):
        self.model = config.get('model', 'llama3.2:3b')
        self.llm = LLMService(model=self.model)

    async def process(
        self,
        chunks: list[dict],
        context: PipelineContext,
        entities: list[Entity] = None
    ) -> list[Relationship]:
        """Extract relationships from chunks given known entities."""

        if not entities:
            return []

        # Build entity lookup
        entity_map = {e.name: e for e in entities}
        entities_json = json.dumps([
            {"name": e.name, "type": e.entity_type}
            for e in entities
        ])

        relationships = []

        for chunk in chunks:
            prompt = RELATIONSHIP_EXTRACTION_PROMPT.format(
                entities_json=entities_json,
                chunk_text=chunk['content']
            )

            response = await self.llm.generate(
                prompt=prompt,
                response_format="json"
            )

            try:
                extracted = json.loads(response)
                for rel_data in extracted.get('relationships', []):
                    source = entity_map.get(rel_data['source_entity'])
                    target = entity_map.get(rel_data['target_entity'])

                    if source and target:
                        relationship = Relationship(
                            source_entity_id=source.id,
                            target_entity_id=target.id,
                            relationship_type=rel_data['relationship_type'],
                            description=rel_data['description'],
                            bidirectional=rel_data.get('bidirectional', False),
                            source_chunk_ids=[chunk['id']],
                            confidence=0.75
                        )
                        relationships.append(relationship)
            except json.JSONDecodeError:
                continue

        return relationships
```

### Redis Graph Integration

```python
# autobot-user-backend/knowledge/pipeline/loaders/redis_graph_loader.py

@TaskRegistry.register_loader("redis_graph")
class RedisGraphLoader(BaseLoader):
    """Load entities and relationships to Redis Memory Graph."""

    def __init__(self, config: dict):
        self.database = config.get('database', 0)
        self.graph = AutoBotMemoryGraph(database=self.database)

    async def load(
        self,
        data: dict,
        context: PipelineContext
    ) -> None:
        """Load entities and relationships to graph."""

        # Load entities
        for entity in data.get('entities', []):
            await self.graph.add_entity(
                entity_id=str(entity.id),
                entity_type=entity.entity_type.lower(),
                name=entity.name,
                content=entity.description,
                metadata={
                    'canonical_name': entity.canonical_name,
                    'properties': entity.properties,
                    'confidence': entity.confidence,
                    'source_document_id': str(entity.source_document_id),
                    'source_chunk_ids': [str(c) for c in entity.source_chunk_ids]
                }
            )

        # Load relationships
        for rel in data.get('relationships', []):
            await self.graph.add_relationship(
                from_entity_id=str(rel.source_entity_id),
                to_entity_id=str(rel.target_entity_id),
                relationship_type=rel.relationship_type.lower(),
                metadata={
                    'description': rel.description,
                    'bidirectional': rel.bidirectional,
                    'confidence': rel.confidence
                }
            )

            # If bidirectional, add reverse relationship
            if rel.bidirectional:
                await self.graph.add_relationship(
                    from_entity_id=str(rel.target_entity_id),
                    to_entity_id=str(rel.source_entity_id),
                    relationship_type=rel.relationship_type.lower(),
                    metadata={
                        'description': rel.description,
                        'bidirectional': True,
                        'confidence': rel.confidence
                    }
                )
```

---

## 3. Temporal Knowledge & Event Extraction

### Event Model

```python
# autobot-user-backend/knowledge/pipeline/models/event.py
from pydantic import BaseModel, Field
from typing import Literal, Optional
from uuid import UUID, uuid4
from datetime import datetime

class TemporalEvent(BaseModel):
    """An event with temporal context."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    description: str

    # Temporal attributes
    timestamp: datetime | None = None  # Exact time if known
    date_range_start: datetime | None = None
    date_range_end: datetime | None = None
    temporal_expression: str  # Original text: "in Q3 2024", "after the merger"
    temporal_type: Literal["point", "range", "relative", "recurring"]

    # Participants and context
    participants: list[str] = []  # Entity names involved
    location: str | None = None

    # Classification
    event_type: Literal[
        "action",      # Something was done
        "decision",    # A choice was made
        "change",      # State transition
        "milestone",   # Significant marker
        "occurrence"   # Something happened
    ]

    # Source tracking
    source_chunk_ids: list[UUID] = []
    source_document_id: UUID | None = None

    # Quality
    confidence: float = Field(ge=0.0, le=1.0, default=0.7)

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Event Extractor

```python
# autobot-user-backend/knowledge/pipeline/cognifiers/event_extractor.py

EVENT_EXTRACTION_PROMPT = """
Extract all events and temporal information from this text.

For each event, identify:
1. name: Short name for the event
2. description: What happened
3. temporal_expression: The time expression as written (e.g., "in January 2024", "after phase 1")
4. temporal_type: One of [point, range, relative, recurring]
5. participants: Names of entities involved
6. location: Where it happened (if mentioned)
7. event_type: One of [action, decision, change, milestone, occurrence]

Important temporal expressions to look for:
- Specific dates: "January 15, 2024", "Q3 2023"
- Relative times: "after the launch", "before version 2.0"
- Durations: "over 3 months", "during the migration"
- Recurring: "every sprint", "monthly reviews"

Text:
{chunk_text}

Known entities in this text:
{entities_json}

Return JSON:
{{
  "events": [
    {{
      "name": "string",
      "description": "string",
      "temporal_expression": "string",
      "temporal_type": "string",
      "participants": ["string"],
      "location": "string or null",
      "event_type": "string"
    }}
  ]
}}
"""

@TaskRegistry.register_cognifier("extract_events")
class EventExtractor(BaseCognifier):
    """LLM-powered event and temporal extraction."""

    def __init__(self, config: dict):
        self.model = config.get('model', 'llama3.2:3b')
        self.llm = LLMService(model=self.model)

    async def process(
        self,
        chunks: list[dict],
        context: PipelineContext,
        entities: list[Entity] = None
    ) -> list[TemporalEvent]:
        """Extract events from chunks."""

        events = []
        entities_json = json.dumps([
            {"name": e.name, "type": e.entity_type}
            for e in (entities or [])
        ])

        for chunk in chunks:
            prompt = EVENT_EXTRACTION_PROMPT.format(
                chunk_text=chunk['content'],
                entities_json=entities_json
            )

            response = await self.llm.generate(
                prompt=prompt,
                response_format="json"
            )

            try:
                extracted = json.loads(response)
                for event_data in extracted.get('events', []):
                    # Parse temporal expression to datetime if possible
                    timestamp, range_start, range_end = self._parse_temporal(
                        event_data['temporal_expression']
                    )

                    event = TemporalEvent(
                        name=event_data['name'],
                        description=event_data['description'],
                        timestamp=timestamp,
                        date_range_start=range_start,
                        date_range_end=range_end,
                        temporal_expression=event_data['temporal_expression'],
                        temporal_type=event_data['temporal_type'],
                        participants=event_data.get('participants', []),
                        location=event_data.get('location'),
                        event_type=event_data['event_type'],
                        source_chunk_ids=[chunk['id']],
                        source_document_id=context.document_id
                    )
                    events.append(event)
            except json.JSONDecodeError:
                continue

        return events

    def _parse_temporal(
        self,
        expression: str
    ) -> tuple[datetime | None, datetime | None, datetime | None]:
        """Attempt to parse temporal expression to datetime."""
        # Implementation uses dateutil.parser and custom patterns
        # Returns (exact_timestamp, range_start, range_end)
        # Falls back to None if unparseable
        pass
```

### Temporal Query Methods

```python
# autobot-user-backend/knowledge/temporal_search.py

class TemporalSearchService:
    """Search service for temporal queries."""

    def __init__(self, graph: AutoBotMemoryGraph, redis_client):
        self.graph = graph
        self.redis = redis_client

    async def search_events_in_range(
        self,
        start_date: datetime,
        end_date: datetime,
        event_types: list[str] = None,
        participants: list[str] = None
    ) -> list[TemporalEvent]:
        """Find all events within a date range."""

        # Query Redis sorted set for events in timestamp range
        start_score = start_date.timestamp()
        end_score = end_date.timestamp()

        event_ids = await self.redis.zrangebyscore(
            'timeline:global',
            start_score,
            end_score
        )

        events = []
        for event_id in event_ids:
            event_data = await self.redis.json().get(f'event:{event_id}:data')
            event = TemporalEvent(**event_data)

            # Apply filters
            if event_types and event.event_type not in event_types:
                continue
            if participants:
                if not any(p in event.participants for p in participants):
                    continue

            events.append(event)

        return sorted(events, key=lambda e: e.timestamp or datetime.min)

    async def get_event_timeline(
        self,
        entity_name: str,
        limit: int = 50
    ) -> list[TemporalEvent]:
        """Get chronological timeline of events involving an entity."""

        # Get event IDs for this entity
        event_ids = await self.redis.smembers(f'entity:{entity_name}:events')

        events = []
        for event_id in event_ids:
            event_data = await self.redis.json().get(f'event:{event_id}:data')
            if event_data:
                events.append(TemporalEvent(**event_data))

        # Sort by timestamp
        events.sort(key=lambda e: e.timestamp or datetime.min)

        return events[:limit]

    async def find_causal_chain(
        self,
        event_id: str,
        direction: Literal["causes", "caused_by"] = "causes",
        max_depth: int = 5
    ) -> list[TemporalEvent]:
        """Trace causal relationships between events."""

        chain = []
        visited = set()
        current_id = event_id

        for _ in range(max_depth):
            if current_id in visited:
                break
            visited.add(current_id)

            # Get event
            event_data = await self.redis.json().get(f'event:{current_id}:data')
            if not event_data:
                break

            event = TemporalEvent(**event_data)
            chain.append(event)

            # Get next in chain based on direction
            rel_type = "causes" if direction == "causes" else "caused_by"
            next_events = await self.graph.get_related_entities(
                current_id,
                relationship_types=[rel_type],
                max_hops=1
            )

            if not next_events:
                break

            current_id = next_events[0]['id']

        return chain
```

---

## 4. Hierarchical Summarization

### Summary Model

```python
# autobot-user-backend/knowledge/pipeline/models/summary.py
from pydantic import BaseModel, Field
from typing import Literal
from uuid import UUID, uuid4
from datetime import datetime

class Summary(BaseModel):
    """Hierarchical summary with source linkage."""

    id: UUID = Field(default_factory=uuid4)
    content: str  # The summary text

    # Hierarchy
    level: Literal["chunk", "section", "document", "collection"]
    parent_summary_id: UUID | None = None  # Link to higher-level summary
    child_summary_ids: list[UUID] = []  # Links to lower-level summaries

    # Source linkage
    source_chunk_ids: list[UUID] = []  # Chunks this summarizes
    source_document_id: UUID | None = None

    # Metadata
    word_count: int
    key_topics: list[str] = []  # Extracted topics
    key_entities: list[str] = []  # Entities mentioned

    # For vector search
    embedding: list[float] | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### Summarizer Implementation

```python
# autobot-user-backend/knowledge/pipeline/cognifiers/summarizer.py

SUMMARIZATION_PROMPT = """
Create a concise summary of the following content.

Guidelines:
- Capture the main points and key information
- Preserve important technical details
- Mention key entities and relationships
- Keep it under {max_words} words

Content:
{text}

Also extract:
- key_topics: 3-5 main themes as a list
- key_entities: Important names, technologies, concepts mentioned

Return JSON:
{{
  "summary": "string",
  "key_topics": ["string"],
  "key_entities": ["string"]
}}
"""

@TaskRegistry.register_cognifier("generate_summaries")
class HierarchicalSummarizer(BaseCognifier):
    """Generate multi-level summaries of documents."""

    def __init__(self, config: dict):
        self.model = config.get('model', 'llama3.2:3b')
        self.levels = config.get('levels', ['chunk', 'section', 'document'])
        self.max_words = config.get('max_words', {
            'chunk': 50,
            'section': 150,
            'document': 300
        })
        self.llm = LLMService(model=self.model)

    async def process(
        self,
        chunks: list[dict],
        context: PipelineContext
    ) -> list[Summary]:
        """Generate hierarchical summaries."""

        all_summaries = []

        # Level 1: Chunk summaries (optional)
        chunk_summaries = []
        if 'chunk' in self.levels:
            for chunk in chunks:
                summary = await self._summarize(
                    chunk['content'],
                    level='chunk',
                    max_words=self.max_words['chunk']
                )
                summary.source_chunk_ids = [chunk['id']]
                summary.source_document_id = context.document_id
                chunk_summaries.append(summary)
            all_summaries.extend(chunk_summaries)

        # Level 2: Section summaries
        if 'section' in self.levels:
            # Group chunks into sections (by heading or fixed size)
            sections = self._group_into_sections(chunks)
            section_summaries = []

            for section_chunks in sections:
                combined_text = '\n\n'.join(c['content'] for c in section_chunks)
                summary = await self._summarize(
                    combined_text,
                    level='section',
                    max_words=self.max_words['section']
                )
                summary.source_chunk_ids = [c['id'] for c in section_chunks]
                summary.source_document_id = context.document_id

                # Link to child chunk summaries
                summary.child_summary_ids = [
                    cs.id for cs in chunk_summaries
                    if any(cid in cs.source_chunk_ids for cid in summary.source_chunk_ids)
                ]
                section_summaries.append(summary)

            all_summaries.extend(section_summaries)

        # Level 3: Document summary
        if 'document' in self.levels:
            full_text = '\n\n'.join(c['content'] for c in chunks)
            doc_summary = await self._summarize(
                full_text,
                level='document',
                max_words=self.max_words['document']
            )
            doc_summary.source_chunk_ids = [c['id'] for c in chunks]
            doc_summary.source_document_id = context.document_id

            # Link to section summaries
            if section_summaries:
                doc_summary.child_summary_ids = [s.id for s in section_summaries]
                for ss in section_summaries:
                    ss.parent_summary_id = doc_summary.id

            all_summaries.append(doc_summary)

        return all_summaries

    async def _summarize(
        self,
        text: str,
        level: str,
        max_words: int
    ) -> Summary:
        """Generate a single summary."""

        prompt = SUMMARIZATION_PROMPT.format(
            text=text,
            max_words=max_words
        )

        response = await self.llm.generate(
            prompt=prompt,
            response_format="json"
        )

        data = json.loads(response)

        return Summary(
            content=data['summary'],
            level=level,
            word_count=len(data['summary'].split()),
            key_topics=data.get('key_topics', []),
            key_entities=data.get('key_entities', [])
        )

    def _group_into_sections(
        self,
        chunks: list[dict],
        section_size: int = 5
    ) -> list[list[dict]]:
        """Group chunks into sections."""
        sections = []
        for i in range(0, len(chunks), section_size):
            sections.append(chunks[i:i + section_size])
        return sections
```

### Summary Search

```python
# autobot-user-backend/knowledge/summary_search.py

class SummarySearchService:
    """Search service for summaries."""

    def __init__(self, chromadb_client, embedding_service):
        self.chroma = chromadb_client
        self.embedder = embedding_service
        self.collection = self.chroma.get_collection('knowledge_summaries')

    async def search_summaries(
        self,
        query: str,
        level: str = None,
        top_k: int = 10
    ) -> list[dict]:
        """Search summaries for quick overview retrieval."""

        query_embedding = await self.embedder.embed(query)

        where_filter = {}
        if level:
            where_filter['level'] = level

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_filter if where_filter else None
        )

        return [
            {
                'summary_id': results['ids'][0][i],
                'content': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'score': 1 - results['distances'][0][i]
            }
            for i in range(len(results['ids'][0]))
        ]

    async def get_document_overview(
        self,
        document_id: str
    ) -> dict:
        """Get hierarchical overview of a document."""

        # Get document-level summary
        doc_summaries = self.collection.get(
            where={
                'source_document_id': document_id,
                'level': 'document'
            }
        )

        if not doc_summaries['ids']:
            return None

        doc_summary = {
            'id': doc_summaries['ids'][0],
            'content': doc_summaries['documents'][0],
            'metadata': doc_summaries['metadatas'][0]
        }

        # Get section summaries
        section_summaries = self.collection.get(
            where={
                'source_document_id': document_id,
                'level': 'section'
            }
        )

        return {
            'document_summary': doc_summary,
            'section_summaries': [
                {
                    'id': section_summaries['ids'][i],
                    'content': section_summaries['documents'][i],
                    'metadata': section_summaries['metadatas'][i]
                }
                for i in range(len(section_summaries['ids']))
            ]
        }

    async def drill_down(
        self,
        summary_id: str
    ) -> dict:
        """From a summary, get underlying detail."""

        # Get the summary
        summary = self.collection.get(ids=[summary_id])
        if not summary['ids']:
            return None

        metadata = summary['metadatas'][0]

        # Get child summaries
        child_ids = metadata.get('child_summary_ids', [])
        children = []
        if child_ids:
            child_results = self.collection.get(ids=child_ids)
            children = [
                {
                    'id': child_results['ids'][i],
                    'content': child_results['documents'][i],
                    'level': child_results['metadatas'][i]['level']
                }
                for i in range(len(child_results['ids']))
            ]

        return {
            'summary': {
                'id': summary_id,
                'content': summary['documents'][0],
                'level': metadata['level']
            },
            'children': children,
            'source_chunk_ids': metadata.get('source_chunk_ids', [])
        }
```

---

## 5. API Endpoints

### New REST Endpoints

```python
# src/api/knowledge_graph_routes.py

@router.post("/api/knowledge/pipeline/run")
async def run_pipeline(
    document_id: str,
    pipeline_name: str = "knowledge_enrichment",
    user: User = Depends(get_current_user)
):
    """Run knowledge enrichment pipeline on a document."""
    pass

@router.get("/api/knowledge/entities")
async def search_entities(
    query: str,
    entity_types: list[str] = Query(default=[]),
    limit: int = 20,
    user: User = Depends(get_current_user)
):
    """Search entities in knowledge graph."""
    pass

@router.get("/api/knowledge/relationships")
async def get_relationships(
    entity_id: str,
    relationship_types: list[str] = Query(default=[]),
    max_hops: int = 2,
    user: User = Depends(get_current_user)
):
    """Get relationships for an entity."""
    pass

@router.get("/api/knowledge/events")
async def search_events(
    query: str = None,
    start_date: datetime = None,
    end_date: datetime = None,
    event_types: list[str] = Query(default=[]),
    user: User = Depends(get_current_user)
):
    """Search temporal events."""
    pass

@router.get("/api/knowledge/events/{entity_name}/timeline")
async def get_entity_timeline(
    entity_name: str,
    limit: int = 50,
    user: User = Depends(get_current_user)
):
    """Get event timeline for an entity."""
    pass

@router.get("/api/knowledge/summaries/search")
async def search_summaries(
    query: str,
    level: str = None,
    top_k: int = 10,
    user: User = Depends(get_current_user)
):
    """Search summaries."""
    pass

@router.get("/api/knowledge/documents/{document_id}/overview")
async def get_document_overview(
    document_id: str,
    user: User = Depends(get_current_user)
):
    """Get hierarchical overview of a document."""
    pass

@router.get("/api/knowledge/summaries/{summary_id}/drill-down")
async def drill_down_summary(
    summary_id: str,
    user: User = Depends(get_current_user)
):
    """Drill down from summary to source detail."""
    pass
```

---

## 6. Frontend Components

### New Vue Components

```
autobot-user-frontend/src/components/knowledge/
├── pipeline/
│   ├── PipelineRunner.vue       # Run and monitor pipelines
│   └── PipelineConfig.vue       # Configure pipeline settings
├── graph/
│   ├── KnowledgeGraphExplorer.vue  # Interactive graph visualization
│   ├── EntityDetail.vue            # Entity details and relationships
│   └── RelationshipViewer.vue      # Relationship explorer
├── temporal/
│   ├── EventTimeline.vue        # Interactive timeline visualization
│   ├── TemporalFilter.vue       # Date range picker
│   └── CausalChainViewer.vue    # Event cause-effect chains
└── summaries/
    ├── DocumentOverview.vue     # Hierarchical document summary
    ├── SummarySearch.vue        # Summary-focused search
    └── DrillDownViewer.vue      # Navigate summary → source
```

---

## 7. Implementation Phases

### Phase 1: ECL Pipeline Foundation (Week 1-2)
- [ ] Implement base classes and registry
- [ ] Create pipeline runner
- [ ] Implement basic extractors (document classifier, chunker)
- [ ] Add configuration loading
- [ ] Create API endpoints for pipeline execution
- [ ] Write unit tests

### Phase 2: Entity & Relationship Extraction (Week 3-4)
- [ ] Implement entity extractor with LLM
- [ ] Implement relationship extractor
- [ ] Add entity deduplication logic
- [ ] Integrate with Redis Memory Graph
- [ ] Update ChromaDB loader for entities
- [ ] Create entity search API endpoints
- [ ] Write integration tests

### Phase 3: Temporal Knowledge (Week 5-6)
- [ ] Implement event model
- [ ] Create event extractor
- [ ] Add temporal parsing utilities
- [ ] Implement temporal search service
- [ ] Create timeline API endpoints
- [ ] Build EventTimeline.vue component
- [ ] Write tests

### Phase 4: Hierarchical Summarization (Week 7-8)
- [ ] Implement summary model
- [ ] Create hierarchical summarizer
- [ ] Add summary embeddings to ChromaDB
- [ ] Implement summary search service
- [ ] Create summary API endpoints
- [ ] Build DocumentOverview.vue component
- [ ] Write tests

### Phase 5: Integration & Polish (Week 9-10)
- [ ] End-to-end pipeline testing
- [ ] Performance optimization
- [ ] UI refinements
- [ ] Documentation
- [ ] User acceptance testing

---

## 8. Dependencies

### Python Packages (add to requirements.txt)
```
# Already present - no new dependencies required
# Uses existing: pydantic, redis, chromadb, ollama/llama
```

### Configuration
```yaml
# Add to config/ssot_config.py
knowledge_graph:
  pipeline:
    default_model: "llama3.2:3b"
    batch_size: 50
    confidence_threshold: 0.7
  temporal:
    parse_relative_dates: true
  summaries:
    embed_summaries: true
    max_words:
      chunk: 50
      section: 150
      document: 300
```

---

## 9. Testing Strategy

### Unit Tests
- Pipeline task registry
- Entity/relationship/event models
- Temporal parsing utilities
- Summary generation logic

### Integration Tests
- Full pipeline execution
- ChromaDB loading
- Redis graph operations
- API endpoint responses

### E2E Tests
- Document upload → Pipeline → Search
- Timeline visualization
- Summary drill-down navigation

---

## 10. Success Metrics

- **Pipeline Performance**: <30s for 100-page document
- **Entity Extraction Accuracy**: >85% precision on test corpus
- **Relationship Accuracy**: >75% precision
- **Summary Quality**: Human evaluation score >4/5
- **Search Relevance**: MRR >0.7 for knowledge graph queries

---

## Appendix A: Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                        DOCUMENT INPUT                            │
│  (PDF, MD, TXT, Code, etc.)                                     │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      EXTRACT STAGE                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Classify   │→ │   Chunk     │→ │  Metadata   │             │
│  │  Document   │  │   Text      │  │  Extract    │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │     Chunks      │
                    │   + Metadata    │
                    └─────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      COGNIFY STAGE                               │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Extract    │  │  Extract    │  │  Extract    │             │
│  │  Entities   │  │  Relations  │  │  Events     │             │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘             │
│         │                │                │                     │
│         └────────────────┼────────────────┘                     │
│                          │                                       │
│  ┌─────────────┐         │                                       │
│  │  Generate   │◄────────┘                                       │
│  │  Summaries  │                                                 │
│  └─────────────┘                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       LOAD STAGE                                 │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  ChromaDB   │  │   Redis     │  │   SQLite    │             │
│  │  Vectors    │  │   Graph     │  │   Facts     │             │
│  │             │  │             │  │             │             │
│  │ • Chunks    │  │ • Entities  │  │ • Metadata  │             │
│  │ • Summaries │  │ • Relations │  │ • Stats     │             │
│  │ • Entities  │  │ • Events    │  │ • Versions  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     SEARCH & RETRIEVAL                           │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                    Query Processing                      │    │
│  │  • Intent Detection                                      │    │
│  │  • Query Expansion                                       │    │
│  │  • Temporal Filter Parsing                               │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│         ┌────────────────────┼────────────────────┐             │
│         ▼                    ▼                    ▼             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │  Semantic   │  │   Graph     │  │  Temporal   │             │
│  │  Search     │  │  Traversal  │  │  Search     │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│         │                    │                    │             │
│         └────────────────────┼────────────────────┘             │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                   Result Fusion                          │    │
│  │  • Reciprocal Rank Fusion                                │    │
│  │  • Cross-encoder Reranking                               │    │
│  │  • Diversity Filtering                                   │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Appendix B: Redis Key Schema

```
# Entities
entity:{entity_id}:data          # Entity JSON
entity:{canonical_name}:id       # Canonical name → ID lookup
entity:type:{type}:ids           # Set of entity IDs by type

# Relationships
rel:{relationship_id}:data       # Relationship JSON
entity:{entity_id}:outgoing      # Set of outgoing relationship IDs
entity:{entity_id}:incoming      # Set of incoming relationship IDs

# Events
event:{event_id}:data            # Event JSON
event:{event_id}:timestamp       # Timestamp for sorted set score
entity:{name}:events             # Set of event IDs for entity
timeline:global                  # Sorted set: event_id → timestamp

# Summaries (also in ChromaDB)
summary:{summary_id}:data        # Summary JSON
document:{document_id}:summaries # Set of summary IDs for document
```
