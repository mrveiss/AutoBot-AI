# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

# Knowledge Graph Feature

## Overview

The Knowledge Graph feature provides relationship mapping between knowledge entries and graph-based RAG (Retrieval Augmented Generation) capabilities. It enables sophisticated knowledge organization, entity extraction, and visual exploration of knowledge connections.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Knowledge Graph System                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐       │
│  │   Frontend   │◄──►│   Backend    │◄──►│  Data Layer  │       │
│  │              │    │     APIs     │    │              │       │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘       │
│         │                   │                   │               │
│  KnowledgeGraph.vue   memory.py           AutoBotMemoryGraph    │
│                       graph_rag.py        Redis (relationships)  │
│                       entity_extraction   ChromaDB (vectors)     │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. Memory Graph Core (`src/autobot_memory_graph.py`)

The core memory graph implementation providing:

- **Entity Management**: Create, read, update, delete entities
- **Relationship Tracking**: Link entities with typed relationships
- **Persistence**: Redis-based storage for durability
- **Semantic Search**: Find entities by content similarity

```python
from src.autobot_memory_graph import AutoBotMemoryGraph

# Initialize
memory_graph = AutoBotMemoryGraph(chat_history_manager)
await memory_graph.initialize()

# Create entity
entity = await memory_graph.create_entity(
    entity_type="feature",
    name="Knowledge Graph",
    observations=["Enables relationship mapping", "Supports graph-based RAG"]
)

# Create relationship
relation = await memory_graph.create_relation(
    from_entity="Knowledge Graph",
    to_entity="ChromaDB",
    relation_type="depends_on"
)
```

### 2. Graph-RAG Service (`src/services/graph_rag_service.py`)

Combines vector search with graph traversal for enhanced retrieval:

- **Hybrid Search**: Vector similarity + graph relationships
- **Configurable Weights**: Adjust balance between vector and graph results
- **Entity-Aware**: Uses extracted entities to enhance queries

```python
from src.services.graph_rag_service import GraphRAGService

# Initialize with dependencies
graph_rag = GraphRAGService(
    rag_service=rag_service,
    memory_graph=memory_graph,
    graph_weight=0.3,
    enable_entity_extraction=True
)

# Search with graph enhancement
results = await graph_rag.search(query="knowledge graph features")
```

### 3. Entity Extraction (`src/agents/graph_entity_extractor.py`)

Automatically extracts entities from conversations and documents:

- **Entity Recognition**: Identifies people, concepts, features, etc.
- **Relationship Inference**: Detects relationships between entities
- **Confidence Scoring**: Filters low-confidence extractions

```python
from src.agents.graph_entity_extractor import GraphEntityExtractor

extractor = GraphEntityExtractor(
    extraction_agent=agent,
    memory_graph=memory_graph,
    confidence_threshold=0.6
)

entities = await extractor.extract_entities(text)
```

### 4. REST API (`backend/api/memory.py`)

Full REST API for memory graph operations:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/memory/entities` | POST | Create entity |
| `/api/memory/entities/all` | GET | List all entities |
| `/api/memory/entities/{id}` | GET | Get entity by ID |
| `/api/memory/entities/{id}` | DELETE | Delete entity |
| `/api/memory/entities/{id}/observations` | PATCH | Add observations |
| `/api/memory/entities/{id}/relations` | GET | Get related entities |
| `/api/memory/relations` | POST | Create relationship |
| `/api/memory/relations` | DELETE | Delete relationship |
| `/api/memory/search` | GET | Semantic search |
| `/api/memory/graph` | GET | Get graph structure |
| `/api/memory/health` | GET | Health check |

### 5. Visualization (`autobot-vue/src/components/knowledge/KnowledgeGraph.vue`)

Interactive graph visualization with:

- **SVG-Based Rendering**: Smooth, scalable graphics
- **Layout Options**: Force-directed and grid layouts
- **Interactive Features**: Click, hover, pan, zoom
- **Entity Details**: View observations and metadata
- **Create Entities**: Add new entities directly from UI
- **Search & Filter**: Find entities by name or type
- **Relationship Edges**: Visualize connections with labels

**Access:** Navigate to `/knowledge/graph` in the frontend.

## Entity Types

The system supports the following entity types:

| Type | Description |
|------|-------------|
| `conversation` | Chat conversation records |
| `bug_fix` | Bug fixes and resolutions |
| `feature` | Feature implementations |
| `decision` | Architectural/design decisions |
| `task` | Work tasks and todos |
| `user_preference` | User preferences and settings |
| `context` | Contextual information |
| `learning` | Learned patterns and insights |
| `research` | Research findings |
| `implementation` | Code implementations |

## Relationship Types

Supported relationship types:

| Type | Description |
|------|-------------|
| `relates_to` | General relationship |
| `depends_on` | Dependency relationship |
| `implements` | Implementation of a feature/design |
| `fixes` | Bug fix relationship |
| `informs` | Information flow |
| `guides` | Guidance relationship |
| `follows` | Sequential relationship |
| `contains` | Containment relationship |
| `blocks` | Blocking relationship |

## Configuration

### Environment Variables

No additional environment variables required. Uses existing Redis and ChromaDB configuration.

### Initialization

The Memory Graph is automatically initialized during backend startup in `backend/initialization/lifespan.py`:

```python
# Automatic initialization sequence:
# 1. AutoBotMemoryGraph - Core graph functionality
# 2. GraphRAGService - Graph-enhanced RAG
# 3. GraphEntityExtractor - Entity extraction
```

## Performance

Target performance metrics:

| Operation | Target Latency |
|-----------|---------------|
| Entity CRUD | <50ms |
| Search queries | <200ms |
| Relation traversal | <100ms |
| Graph visualization load | <500ms |

## Usage Examples

### 1. Create Knowledge Entity via API

```bash
curl -X POST http://localhost:8001/api/memory/entities \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Redis Configuration",
    "entity_type": "implementation",
    "observations": [
      "Uses Redis Stack for data persistence",
      "Configured on 172.16.168.23:6379"
    ]
  }'
```

### 2. Search Entities

```bash
curl "http://localhost:8001/api/memory/search?query=redis+configuration"
```

### 3. Get Entity Relations

```bash
curl "http://localhost:8001/api/memory/entities/{entity_id}/relations?direction=both"
```

### 4. Create Relationship

```bash
curl -X POST http://localhost:8001/api/memory/relations \
  -H "Content-Type: application/json" \
  -d '{
    "from_entity": "Redis Configuration",
    "to_entity": "Backend API",
    "relation_type": "depends_on",
    "strength": 0.8
  }'
```

## Integration with Chat

The Knowledge Graph integrates with the chat system to:

1. **Extract Entities**: Automatically extract entities from conversations
2. **Enhance Context**: Use graph relationships to provide better context
3. **Track Decisions**: Store architectural decisions for future reference
4. **Link Conversations**: Connect related conversations via entities

## Future Enhancements

Potential future improvements:

- [ ] Neo4j/ArangoDB integration for larger graphs
- [ ] Graph query language (Cypher/AQL) support
- [ ] Real-time graph updates via WebSocket
- [ ] Export/import functionality
- [ ] Graph analytics and metrics
- [ ] Automated relationship suggestion

## Troubleshooting

### Graph Not Loading

1. Check backend is running: `curl http://localhost:8001/api/memory/health`
2. Verify Redis connection: `redis-cli -h 172.16.168.23 ping`
3. Check browser console for API errors

### Entity Creation Fails

1. Ensure required fields are provided (name, entity_type, observations)
2. Verify entity_type is valid (see Entity Types above)
3. Check for duplicate entity names

### Relations Not Showing

1. Verify entities exist before creating relations
2. Check relation_type is valid (see Relationship Types above)
3. Ensure direction filter is correct (outgoing/incoming/both)

## Related Documentation

- [API Documentation](../api/COMPREHENSIVE_API_DOCUMENTATION.md)
- [Architecture Overview](../architecture/AUTOBOT_MEMORY_GRAPH_ARCHITECTURE.md)
- [Developer Setup](../developer/PHASE_5_DEVELOPER_SETUP.md)
