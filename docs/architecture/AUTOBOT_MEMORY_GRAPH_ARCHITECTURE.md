# AutoBot Memory Graph - Enhanced Memory System Architecture

**Version:** 1.0
**Date:** 2025-10-03
**Status:** Design Specification
**Author:** Systems Architect AI

---

## Executive Summary

The AutoBot Memory Graph is an enhanced memory system that provides graph-based relationship tracking, semantic search, and cross-conversation context for the AutoBot platform. It augments the existing chat history system with entity-relationship modeling capabilities similar to Memory MCP, enabling project continuity, decision tracking, and intelligent context retrieval.

**Key Capabilities:**
- Entity extraction and management (conversations, bugs, features, decisions, tasks)
- Graph-based relationship tracking with bidirectional links
- Semantic search across all entities and observations
- Cross-conversation context and project continuity
- Backward compatible with existing chat history system
- High-performance Redis Stack-based implementation

---

## 1. Architecture Overview

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     AutoBot Application Layer                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐         ┌──────────────────────────────┐  │
│  │ Chat History     │         │  Memory Graph Interface      │  │
│  │ Manager          │◄────────┤  (AutoBotMemoryGraph)        │  │
│  │ (Existing)       │  Events │                              │  │
│  └────────┬─────────┘         └───────────┬──────────────────┘  │
│           │                               │                      │
│           │ Session Data                  │ Entities/Relations   │
│           │                               │                      │
├───────────┼───────────────────────────────┼──────────────────────┤
│           │                               │                      │
│  ┌────────▼─────────┐         ┌──────────▼──────────────────┐  │
│  │ Redis DB 8       │         │  Redis DB 9                 │  │
│  │ Chat History     │         │  Memory Graph               │  │
│  │ - Sessions       │         │  - Entities (RedisJSON)     │  │
│  │ - Messages       │         │  - Relations (RedisGraph)   │  │
│  │ - Transcripts    │         │  - Search Index (Search)    │  │
│  └──────────────────┘         └─────────────────────────────┘  │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
                                │
                                │ Redis Stack (172.16.168.23:6379)
                                ▼
                ┌────────────────────────────────┐
                │  Redis Stack Modules           │
                │  - RedisGraph (Relationships)  │
                │  - RedisJSON (Entities)        │
                │  - RediSearch (Semantic)       │
                │  - RedisTimeSeries (Tracking)  │
                └────────────────────────────────┘
```

### 1.2 Technology Stack

- **Storage Backend**: Redis Stack 7.4 on VM3 (172.16.168.23:6379)
- **Database**: DB 9 (dedicated for Memory Graph)
- **Redis Modules**:
  - **RedisGraph**: Native graph operations for entity relationships
  - **RedisJSON**: Fast entity storage with native JSON support
  - **RediSearch**: Full-text and semantic search across entities
  - **RedisTimeSeries**: Entity timeline tracking
- **Python Client**: `redis-py` with graph, search, and JSON support
- **Performance**: Multi-threaded I/O (10 threads), 6GB memory allocation

---

## 2. Data Model Specification

### 2.1 Entity Model

Entities are stored as RedisJSON documents with the following structure:

```python
Entity = {
    # Core identification
    "entity_id": "uuid-v4",                    # Unique entity identifier
    "entity_type": str,                        # Entity type (see 2.1.1)
    "name": str,                               # Human-readable name

    # Content
    "observations": [str],                     # List of observations/notes

    # Metadata
    "metadata": {
        "created_at": "ISO-8601 timestamp",
        "updated_at": "ISO-8601 timestamp",
        "created_by": str,                     # User or system identifier
        "session_id": Optional[str],           # Link to chat session
        "tags": [str],                         # Classification tags
        "priority": str,                       # low|medium|high|critical
        "status": str,                         # active|completed|archived|cancelled
        "version": int,                        # Entity version number
        "parent_entity": Optional[str]         # Parent entity ID (hierarchies)
    },

    # Search optimization
    "search_text": str,                        # Concatenated searchable text
    "embedding_vector": Optional[List[float]]  # Future: semantic embeddings
}
```

#### 2.1.1 Entity Types

| Entity Type       | Description                           | Use Case                                    |
|-------------------|---------------------------------------|---------------------------------------------|
| `conversation`    | Chat session metadata                 | Link conversations, track topics            |
| `bug_fix`         | Bug tracking and resolution           | Bug → Fix → Test → Deploy chains            |
| `feature`         | Feature implementation tracking       | Feature planning and progress               |
| `decision`        | Architecture/design decisions         | Decision history and rationale              |
| `task`            | Task entities with dependencies       | Task management and tracking                |
| `user_preference` | User settings and preferences         | Personalization and context                 |
| `context`         | Important context snippets            | Reusable context across conversations       |
| `learning`        | Lessons learned and insights          | Knowledge accumulation                      |

### 2.2 Relationship Model

Relationships are stored in RedisGraph with the following structure:

```python
Relation = {
    # Core relationship
    "relation_id": "uuid-v4",                  # Unique relation identifier
    "from_entity": "entity_id",                # Source entity
    "to_entity": "entity_id",                  # Target entity
    "relation_type": str,                      # Relationship type (see 2.2.1)

    # Metadata
    "metadata": {
        "created_at": "ISO-8601 timestamp",
        "created_by": str,                     # User or system identifier
        "strength": float,                     # 0.0-1.0 relationship strength
        "bidirectional": bool,                 # Can traverse both ways
        "context": Optional[str],              # Additional context
        "auto_generated": bool                 # System vs manual creation
    }
}
```

#### 2.2.1 Relationship Types

| Relation Type   | Description                          | Example                                      |
|-----------------|--------------------------------------|----------------------------------------------|
| `relates_to`    | General association                  | Conversation → Conversation                  |
| `depends_on`    | Dependency relationship              | Task → Task (blocking)                       |
| `implements`    | Implementation link                  | Feature → Code Changes                       |
| `fixes`         | Fix relationship                     | Bug Fix → Bug                                |
| `informs`       | Information flow                     | Research → Decision                          |
| `guides`        | Planning relationship                | Plan → Implementation                        |
| `follows`       | Sequential relationship              | Task → Next Task                             |
| `contains`      | Hierarchical relationship            | Parent → Child Entity                        |

### 2.3 Search Index Schema

RediSearch index for semantic search:

```python
SearchIndex = {
    "index_name": "memory_graph_idx",
    "prefix": "entity:",
    "fields": [
        # Text fields (full-text search)
        {"name": "name", "type": "TEXT", "weight": 5.0},
        {"name": "entity_type", "type": "TAG"},
        {"name": "observations", "type": "TEXT", "weight": 3.0},
        {"name": "search_text", "type": "TEXT", "weight": 2.0},

        # Tag fields (exact match)
        {"name": "status", "type": "TAG"},
        {"name": "priority", "type": "TAG"},
        {"name": "tags", "type": "TAG", "separator": ","},

        # Numeric fields (range queries)
        {"name": "created_at", "type": "NUMERIC", "sortable": True},
        {"name": "updated_at", "type": "NUMERIC", "sortable": True},
        {"name": "version", "type": "NUMERIC"},

        # Vector field (future: semantic search)
        # {"name": "embedding_vector", "type": "VECTOR", "algorithm": "HNSW"}
    ]
}
```

---

## 3. API Interface Specification

### 3.1 Core API Class

```python
class AutoBotMemoryGraph:
    """
    Enhanced memory system with graph-based relationship tracking
    and semantic search capabilities.

    Integrates with existing ChatHistoryManager to provide:
    - Entity extraction from conversations
    - Relationship tracking
    - Semantic search
    - Cross-conversation context
    """

    def __init__(
        self,
        redis_host: str = "172.16.168.23",
        redis_port: int = 6379,
        database: int = 9,
        chat_history_manager: Optional[ChatHistoryManager] = None
    ):
        """
        Initialize Memory Graph interface.

        Args:
            redis_host: Redis server hostname
            redis_port: Redis server port
            database: Redis database number (default: 9)
            chat_history_manager: Optional link to chat history manager
        """
```

### 3.2 Entity Operations

#### 3.2.1 Create Entity

```python
async def create_entity(
    self,
    entity_type: str,
    name: str,
    observations: List[str],
    metadata: Optional[Dict[str, Any]] = None,
    tags: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Create a new entity in the memory graph.

    Args:
        entity_type: Type of entity (conversation, bug_fix, feature, etc.)
        name: Human-readable entity name
        observations: List of observation strings
        metadata: Optional additional metadata
        tags: Optional classification tags

    Returns:
        Created entity with entity_id and metadata

    Raises:
        ValidationError: Invalid entity_type or empty name
        InternalError: Redis operation failed

    Example:
        entity = await memory_graph.create_entity(
            entity_type="decision",
            name="Use Redis Stack for Memory Graph",
            observations=[
                "RedisGraph provides native graph operations",
                "RedisJSON enables fast entity storage",
                "RediSearch allows semantic search"
            ],
            tags=["architecture", "database"],
            metadata={"priority": "high"}
        )
    """
```

#### 3.2.2 Add Observations

```python
async def add_observations(
    self,
    entity_name: str,
    observations: List[str]
) -> Dict[str, Any]:
    """
    Add new observations to an existing entity.

    Args:
        entity_name: Name of entity to update
        observations: List of new observations to add

    Returns:
        Updated entity data

    Raises:
        ResourceNotFoundError: Entity not found
        InternalError: Redis operation failed

    Example:
        await memory_graph.add_observations(
            entity_name="Use Redis Stack for Memory Graph",
            observations=["Multi-threaded I/O provides 10x performance"]
        )
    """
```

#### 3.2.3 Get Entity

```python
async def get_entity(
    self,
    entity_name: str,
    include_relations: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Retrieve entity by name.

    Args:
        entity_name: Name of entity to retrieve
        include_relations: Include related entities in response

    Returns:
        Entity data or None if not found

    Example:
        entity = await memory_graph.get_entity(
            entity_name="Use Redis Stack for Memory Graph",
            include_relations=True
        )
    """
```

#### 3.2.4 Delete Entity

```python
async def delete_entity(
    self,
    entity_name: str,
    cascade_relations: bool = True
) -> bool:
    """
    Delete entity and optionally its relations.

    Args:
        entity_name: Name of entity to delete
        cascade_relations: Delete all relations to/from this entity

    Returns:
        True if deleted, False if not found

    Raises:
        InternalError: Redis operation failed
    """
```

### 3.3 Relationship Operations

#### 3.3.1 Create Relation

```python
async def create_relation(
    self,
    from_entity: str,
    to_entity: str,
    relation_type: str,
    bidirectional: bool = False,
    strength: float = 1.0,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Create relationship between two entities.

    Args:
        from_entity: Source entity name
        to_entity: Target entity name
        relation_type: Type of relationship (relates_to, depends_on, etc.)
        bidirectional: Create reverse relation as well
        strength: Relationship strength (0.0-1.0)
        metadata: Optional additional metadata

    Returns:
        Created relation data

    Raises:
        ResourceNotFoundError: Entity not found
        ValidationError: Invalid relation_type
        InternalError: Redis operation failed

    Example:
        await memory_graph.create_relation(
            from_entity="Authentication Research 2025-10-03",
            to_entity="Authentication Implementation Plan",
            relation_type="informs",
            bidirectional=False,
            strength=0.9
        )
    """
```

#### 3.3.2 Get Related Entities

```python
async def get_related_entities(
    self,
    entity_name: str,
    relation_type: Optional[str] = None,
    direction: str = "both",
    max_depth: int = 1
) -> List[Dict[str, Any]]:
    """
    Get entities related to specified entity.

    Args:
        entity_name: Name of entity
        relation_type: Filter by relation type (None = all types)
        direction: "outgoing", "incoming", or "both"
        max_depth: Relationship traversal depth (1-3)

    Returns:
        List of related entities with relation metadata

    Example:
        related = await memory_graph.get_related_entities(
            entity_name="Authentication Feature",
            relation_type="depends_on",
            direction="outgoing",
            max_depth=2
        )
    """
```

#### 3.3.3 Delete Relation

```python
async def delete_relation(
    self,
    from_entity: str,
    to_entity: str,
    relation_type: str
) -> bool:
    """
    Delete specific relation between entities.

    Args:
        from_entity: Source entity name
        to_entity: Target entity name
        relation_type: Type of relation to delete

    Returns:
        True if deleted, False if not found
    """
```

### 3.4 Search and Query Operations

#### 3.4.1 Search Entities

```python
async def search_entities(
    self,
    query: str,
    entity_type: Optional[str] = None,
    tags: Optional[List[str]] = None,
    status: Optional[str] = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """
    Semantic search across all entities.

    Args:
        query: Search query (full-text search)
        entity_type: Filter by entity type
        tags: Filter by tags (any match)
        status: Filter by status
        limit: Maximum results to return

    Returns:
        List of matching entities sorted by relevance

    Example:
        # Find all architecture decisions about Redis
        results = await memory_graph.search_entities(
            query="Redis architecture database",
            entity_type="decision",
            tags=["architecture"],
            status="active"
        )
    """
```

#### 3.4.2 Query Graph

```python
async def query_graph(
    self,
    cypher_query: str,
    params: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """
    Execute Cypher query against RedisGraph.

    Args:
        cypher_query: Cypher query string
        params: Query parameters

    Returns:
        Query results

    Example:
        # Find all tasks that depend on completed tasks
        results = await memory_graph.query_graph(
            "MATCH (t:task)-[:depends_on]->(d:task) "
            "WHERE d.status = 'completed' "
            "RETURN t.name, d.name"
        )
    """
```

### 3.5 Integration Operations

#### 3.5.1 Create Conversation Entity

```python
async def create_conversation_entity(
    self,
    session_id: str,
    metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Automatically create entity from chat session.

    Args:
        session_id: Chat session identifier
        metadata: Optional additional metadata

    Returns:
        Created conversation entity

    Note:
        Extracts observations from session messages,
        creates tags based on content analysis,
        links to related conversations automatically.
    """
```

#### 3.5.2 Link Conversations

```python
async def link_conversations(
    self,
    session_id_1: str,
    session_id_2: str,
    relation_type: str = "relates_to"
) -> Dict[str, Any]:
    """
    Create relationship between two conversations.

    Args:
        session_id_1: First session ID
        session_id_2: Second session ID
        relation_type: Type of relationship

    Returns:
        Created relation data
    """
```

#### 3.5.3 Get Conversation Context

```python
async def get_conversation_context(
    self,
    session_id: str,
    max_related: int = 10
) -> Dict[str, Any]:
    """
    Get full context for conversation including related entities.

    Args:
        session_id: Chat session ID
        max_related: Maximum related entities to include

    Returns:
        Comprehensive context including:
        - Conversation entity
        - Related conversations
        - Relevant decisions, tasks, bugs
        - User preferences

    Example:
        context = await memory_graph.get_conversation_context(
            session_id="267ab75b-8c44-46bb-b038-e5ee72096de4"
        )
        # Returns all related context for AI response generation
    """
```

---

## 4. Integration Strategy

### 4.1 Integration with ChatHistoryManager

The Memory Graph integrates seamlessly with the existing `ChatHistoryManager`:

```python
# In chat_history_manager.py

class ChatHistoryManager:
    def __init__(self, ...):
        # Existing initialization
        self.memory_graph = None  # Optional memory graph integration

    async def enable_memory_graph(self):
        """Enable memory graph integration"""
        from src.autobot_memory_graph import AutoBotMemoryGraph
        self.memory_graph = AutoBotMemoryGraph(
            chat_history_manager=self
        )

    async def create_session(self, session_id, title, metadata):
        """Enhanced session creation with entity extraction"""
        # Existing session creation
        session = await super().create_session(...)

        # Auto-create conversation entity if memory graph enabled
        if self.memory_graph:
            await self.memory_graph.create_conversation_entity(
                session_id=session_id,
                metadata=metadata
            )

        return session
```

### 4.2 Event-Driven Entity Extraction

Automatic entity creation from chat events:

```python
async def on_message_added(session_id: str, message: Dict[str, Any]):
    """
    Event handler for new messages - extract entities automatically.

    Triggers:
    - Bug mentions → create bug_fix entity
    - Feature requests → create feature entity
    - Decisions made → create decision entity
    - Tasks assigned → create task entity
    """

    # Example: Extract bug mention
    if "bug" in message["content"].lower():
        await memory_graph.create_entity(
            entity_type="bug_fix",
            name=extract_bug_summary(message),
            observations=[message["content"]],
            metadata={"session_id": session_id}
        )
```

### 4.3 Backward Compatibility

The system maintains full backward compatibility:

1. **Existing code unchanged**: ChatHistoryManager works identically
2. **Optional activation**: Memory Graph is opt-in via `enable_memory_graph()`
3. **Graceful degradation**: If Memory Graph unavailable, system continues normally
4. **Data preservation**: All existing chat history remains intact

---

## 5. Migration Strategy

### 5.1 Phase 1: Infrastructure Setup (Week 1)

**Objective**: Deploy Memory Graph infrastructure without affecting existing system

**Tasks**:
1. Create `AutoBotMemoryGraph` class in `src/autobot_memory_graph.py`
2. Initialize Redis DB 9 with RedisGraph, RedisJSON, RediSearch indexes
3. Create RediSearch index for entity search
4. Deploy configuration to Redis VM (172.16.168.23)
5. Unit tests for all API operations

**Validation**:
- Memory Graph operations work in isolation
- No impact on existing chat functionality
- Performance tests show <50ms entity operations

### 5.2 Phase 2: Data Migration (Week 2)

**Objective**: Migrate existing conversations to entities

**Tasks**:
1. Create migration script: `scripts/migrate_chat_to_memory_graph.py`
2. Extract conversation entities from `data/conversation_transcripts/*.json`
3. Auto-generate relationships based on session metadata
4. Validate migrated data integrity
5. Create rollback mechanism

**Migration Script**:
```python
async def migrate_existing_conversations():
    """
    Migrate existing chat sessions to conversation entities.

    Process:
    1. Scan all session files in data/conversation_transcripts/
    2. Extract metadata and key observations
    3. Create conversation entities
    4. Link related conversations (same user, similar topics)
    """

    memory_graph = AutoBotMemoryGraph()
    chat_manager = ChatHistoryManager()

    sessions = await chat_manager.list_sessions()

    for session in sessions:
        # Load full session data
        messages = await chat_manager.load_session(session["chatId"])

        # Extract observations from messages
        observations = extract_key_observations(messages)

        # Create entity
        entity = await memory_graph.create_conversation_entity(
            session_id=session["chatId"],
            metadata={
                "title": session.get("name"),
                "message_count": len(messages),
                "created_at": session.get("createdTime")
            }
        )

        logger.info(f"Migrated session {session['chatId']} → entity {entity['entity_id']}")
```

**Validation**:
- All sessions have corresponding entities
- Observations accurately reflect session content
- Relationships created between related sessions

### 5.3 Phase 3: Integration (Week 3)

**Objective**: Integrate Memory Graph with chat workflow

**Tasks**:
1. Add `enable_memory_graph()` to ChatHistoryManager initialization
2. Implement automatic entity extraction on message events
3. Add context retrieval to chat response generation
4. Update chat API to include memory graph context
5. Frontend integration (optional: show related conversations)

**Integration Points**:
```python
# In autobot-user-backend/api/chat.py

async def process_chat_message(message, ...):
    # Existing message processing

    # Enhanced: Get memory graph context
    if memory_graph:
        context = await memory_graph.get_conversation_context(
            session_id=message.session_id,
            max_related=10
        )

        # Include related entities in AI prompt
        llm_context.extend([
            f"Related conversations: {context['related_conversations']}",
            f"Relevant decisions: {context['decisions']}",
            f"Active tasks: {context['tasks']}"
        ])

    # Generate response with enhanced context
    response = await llm_service.generate_response(llm_context)
```

**Validation**:
- AI responses include relevant cross-conversation context
- Entity extraction accuracy >90%
- No performance degradation in chat operations

### 5.4 Phase 4: Advanced Features (Week 4)

**Objective**: Enable advanced memory graph capabilities

**Tasks**:
1. Semantic search UI integration
2. Entity visualization (graph view)
3. Task dependency tracking
4. Decision history timeline
5. User preference learning

**Advanced Features**:
- **Graph Visualization**: D3.js graph showing entity relationships
- **Timeline View**: RedisTimeSeries-based entity history
- **Smart Context**: AI-powered entity extraction and linking
- **Preference Learning**: Automatic user preference entity creation

---

## 6. Performance Considerations

### 6.1 Performance Targets

| Operation                  | Target Latency | Notes                                    |
|----------------------------|----------------|------------------------------------------|
| Create Entity              | <50ms          | Single RedisJSON write                   |
| Add Observation            | <30ms          | Append to JSON array                     |
| Get Entity                 | <20ms          | Single RedisJSON read                    |
| Create Relation            | <50ms          | RedisGraph edge creation                 |
| Get Related Entities       | <100ms         | Graph traversal (depth 1-2)              |
| Search Entities            | <200ms         | RediSearch query (up to 1000 entities)   |
| Graph Query (Cypher)       | <500ms         | Complex graph traversal                  |
| Get Conversation Context   | <300ms         | Multiple entity/relation retrievals      |

### 6.2 Optimization Strategies

1. **Connection Pooling**:
   ```python
   # Redis connection pool (50 connections, 10 I/O threads)
   pool = redis.ConnectionPool(
       host="172.16.168.23",
       port=6379,
       db=9,
       max_connections=50,
       socket_timeout=5,
       socket_connect_timeout=2
   )
   ```

2. **Batch Operations**:
   ```python
   async def create_entities_batch(entities: List[Dict]) -> List[Dict]:
       """Create multiple entities in single pipeline"""
       pipeline = redis_client.pipeline()
       for entity in entities:
           pipeline.json().set(f"entity:{entity['entity_id']}", "$", entity)
       results = await pipeline.execute()
       return results
   ```

3. **Caching Strategy**:
   - Cache frequently accessed entities in DB 4 (app cache)
   - TTL: 300 seconds (5 minutes)
   - Cache invalidation on entity updates

4. **Search Index Optimization**:
   - Maintain separate search text field (pre-computed)
   - Update index asynchronously after entity creation
   - Use tag fields for exact-match filters

### 6.3 Storage Estimates

**Assumptions**:
- Average entity size: 2KB (JSON)
- Average relation size: 500 bytes
- 10,000 entities with 20,000 relations

**Storage Calculation**:
```
Entities:  10,000 × 2KB     = 20 MB
Relations: 20,000 × 500B    = 10 MB
Index:     ~10% overhead    =  3 MB
Total:                      = 33 MB
```

**Scaling**:
- 100,000 entities + 200,000 relations = ~330 MB
- 1,000,000 entities + 2,000,000 relations = ~3.3 GB
- Well within 6GB Redis memory allocation

---

## 7. Security Considerations

### 7.1 Access Control

1. **Network Security**:
   - Redis VM on internal network only (172.16.168.0/24)
   - No external access to Redis port
   - Protected mode disabled (internal network trust)

2. **Entity-Level Security** (Future):
   ```python
   Entity.metadata = {
       "visibility": "public|private|team",
       "owner": "user_id",
       "allowed_users": ["user1", "user2"]
   }
   ```

3. **Audit Trail**:
   - Track entity creation/modification user
   - Log all entity/relation changes
   - Maintain entity version history

### 7.2 Data Privacy

1. **Sensitive Data Handling**:
   - No PII in entity names (use references)
   - Encrypt sensitive observations (optional)
   - User preference entities marked as private

2. **Data Retention**:
   - Archive old entities to DB 10 (backup)
   - Soft delete (status = "archived") before hard delete
   - Maintain deletion audit trail

---

## 8. API Endpoints (Backend Integration)

### 8.1 REST API Endpoints

Add to `autobot-user-backend/api/memory.py`:

```python
@router.post("/api/memory/entities")
async def create_entity_endpoint(entity_data: EntityCreate):
    """Create new entity"""

@router.get("/api/memory/entities/{entity_name}")
async def get_entity_endpoint(entity_name: str):
    """Get entity by name"""

@router.put("/api/memory/entities/{entity_name}/observations")
async def add_observations_endpoint(entity_name: str, observations: List[str]):
    """Add observations to entity"""

@router.delete("/api/memory/entities/{entity_name}")
async def delete_entity_endpoint(entity_name: str):
    """Delete entity"""

@router.post("/api/memory/relations")
async def create_relation_endpoint(relation_data: RelationCreate):
    """Create relationship between entities"""

@router.get("/api/memory/entities/{entity_name}/related")
async def get_related_entities_endpoint(entity_name: str):
    """Get related entities"""

@router.get("/api/memory/search")
async def search_entities_endpoint(
    query: str,
    entity_type: Optional[str] = None,
    tags: Optional[str] = None
):
    """Search entities"""

@router.get("/api/memory/context/{session_id}")
async def get_conversation_context_endpoint(session_id: str):
    """Get conversation context with related entities"""
```

---

## 9. Testing Strategy

### 9.1 Unit Tests

```python
# tests/test_autobot_memory_graph.py

async def test_create_entity():
    """Test entity creation"""
    entity = await memory_graph.create_entity(
        entity_type="decision",
        name="Test Decision",
        observations=["Observation 1", "Observation 2"]
    )
    assert entity["entity_id"] is not None
    assert entity["name"] == "Test Decision"
    assert len(entity["observations"]) == 2

async def test_create_relation():
    """Test relation creation"""
    entity1 = await memory_graph.create_entity(...)
    entity2 = await memory_graph.create_entity(...)

    relation = await memory_graph.create_relation(
        from_entity=entity1["name"],
        to_entity=entity2["name"],
        relation_type="relates_to"
    )
    assert relation["from_entity"] == entity1["entity_id"]
    assert relation["to_entity"] == entity2["entity_id"]

async def test_search_entities():
    """Test semantic search"""
    await memory_graph.create_entity(
        entity_type="decision",
        name="Use Redis for Memory",
        observations=["Redis provides graph capabilities"]
    )

    results = await memory_graph.search_entities("Redis graph")
    assert len(results) > 0
    assert "Use Redis for Memory" in [r["name"] for r in results]
```

### 9.2 Integration Tests

```python
# tests/integration/test_chat_memory_integration.py

async def test_conversation_entity_creation():
    """Test automatic conversation entity creation"""
    session_id = await chat_manager.create_session(title="Test Session")

    # Verify conversation entity created
    entity = await memory_graph.get_entity(f"conversation:{session_id}")
    assert entity is not None
    assert entity["metadata"]["session_id"] == session_id

async def test_context_enrichment():
    """Test chat context enrichment with memory graph"""
    # Create related entities
    decision = await memory_graph.create_entity(
        entity_type="decision",
        name="Use FastAPI",
        observations=["FastAPI chosen for API framework"]
    )

    # Send chat message
    response = await chat_api.send_message(
        message="Tell me about our API framework decision",
        session_id=session_id
    )

    # Verify response includes decision context
    assert "FastAPI" in response["content"]
```

### 9.3 Performance Tests

```python
# tests/performance/test_memory_graph_performance.py

async def test_entity_creation_performance():
    """Test entity creation latency"""
    import time

    latencies = []
    for i in range(100):
        start = time.time()
        await memory_graph.create_entity(
            entity_type="test",
            name=f"Test Entity {i}",
            observations=[f"Observation {i}"]
        )
        latencies.append((time.time() - start) * 1000)

    avg_latency = sum(latencies) / len(latencies)
    p95_latency = sorted(latencies)[94]

    assert avg_latency < 50, f"Average latency {avg_latency}ms exceeds 50ms"
    assert p95_latency < 100, f"P95 latency {p95_latency}ms exceeds 100ms"
```

---

## 10. Monitoring and Observability

### 10.1 Metrics to Monitor

1. **Entity Metrics**:
   - Total entities by type
   - Entity creation rate
   - Entity update rate
   - Entity deletion rate

2. **Relation Metrics**:
   - Total relations by type
   - Relation creation rate
   - Average relations per entity

3. **Search Metrics**:
   - Search query rate
   - Search latency (p50, p95, p99)
   - Search result count distribution

4. **Integration Metrics**:
   - Conversation entity creation rate
   - Context retrieval latency
   - Entity extraction accuracy

### 10.2 Health Checks

```python
@router.get("/api/memory/health")
async def memory_graph_health():
    """Memory Graph health check"""
    try:
        # Test Redis connectivity
        await redis_client.ping()

        # Test entity operations
        test_entity = await memory_graph.create_entity(
            entity_type="test",
            name="health_check",
            observations=["test"]
        )
        await memory_graph.delete_entity("health_check")

        # Test search
        results = await memory_graph.search_entities("health")

        return {
            "status": "healthy",
            "redis_connected": True,
            "entity_operations": "ok",
            "search_operations": "ok"
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }
```

---

## 11. Future Enhancements

### 11.1 Semantic Embeddings (Phase 5)

**Objective**: Add vector-based semantic similarity search

**Implementation**:
1. Generate embeddings for entity observations using sentence transformers
2. Store embeddings in RedisJSON entity field
3. Use RediSearch VECTOR field type for similarity search
4. Enable "find similar entities" functionality

**Use Cases**:
- Find conversations about similar topics
- Suggest related decisions based on content similarity
- Detect duplicate bug reports

### 11.2 Automated Entity Extraction (Phase 6)

**Objective**: Use LLM to automatically extract entities from conversations

**Implementation**:
1. Analyze conversation messages with LLM
2. Extract mentions of bugs, features, decisions, tasks
3. Automatically create entities with appropriate metadata
4. Link entities to conversations

**Use Cases**:
- Zero-configuration entity tracking
- Automatic project knowledge accumulation
- Intelligent context suggestions

### 11.3 Entity Visualization (Phase 7)

**Objective**: Visual graph interface for entities and relationships

**Implementation**:
1. Create frontend component with D3.js/vis.js
2. Render entity graph with interactive nodes
3. Click nodes to view entity details
4. Highlight relationship paths

**Use Cases**:
- Visual project timeline
- Dependency visualization
- Knowledge graph exploration

---

## 12. Conclusion

The AutoBot Memory Graph provides a powerful enhancement to the existing chat system, enabling:

- **Project Continuity**: Track decisions, bugs, features across conversations
- **Intelligent Context**: AI responses enriched with relevant historical context
- **Semantic Search**: Find information across all conversations and entities
- **Relationship Tracking**: Understand dependencies and connections
- **Knowledge Accumulation**: Build comprehensive project knowledge base

**Key Benefits**:
1. Backward compatible with existing chat system
2. High-performance Redis Stack implementation
3. Scalable to millions of entities
4. Extensible for future AI-powered features
5. Minimal infrastructure changes required

**Next Steps**:
1. Implement `AutoBotMemoryGraph` class (Phase 1)
2. Deploy to Redis VM and create indexes
3. Migrate existing conversations (Phase 2)
4. Integrate with chat workflow (Phase 3)
5. Enable advanced features (Phase 4+)

---

## Appendix A: Redis Commands Reference

### Entity Operations

```bash
# Create entity (RedisJSON)
JSON.SET entity:uuid123 $ '{"entity_id":"uuid123","entity_type":"decision",...}'

# Get entity
JSON.GET entity:uuid123

# Update observations
JSON.ARRAPPEND entity:uuid123 $.observations '"New observation"'

# Delete entity
JSON.DEL entity:uuid123
```

### Relation Operations (RedisGraph)

```bash
# Create relation
GRAPH.QUERY memory_graph "CREATE (:Entity {id:'uuid1'})-[:relates_to]->(:Entity {id:'uuid2'})"

# Get related entities
GRAPH.QUERY memory_graph "MATCH (e:Entity {id:'uuid1'})-[:relates_to]->(related) RETURN related"

# Delete relation
GRAPH.QUERY memory_graph "MATCH (:Entity {id:'uuid1'})-[r:relates_to]->(:Entity {id:'uuid2'}) DELETE r"
```

### Search Operations (RediSearch)

```bash
# Create search index
FT.CREATE memory_graph_idx ON JSON PREFIX 1 entity: SCHEMA $.name AS name TEXT WEIGHT 5.0 $.entity_type AS entity_type TAG

# Search entities
FT.SEARCH memory_graph_idx "Redis architecture @entity_type:{decision}"

# Aggregate by type
FT.AGGREGATE memory_graph_idx "*" GROUPBY 1 @entity_type REDUCE COUNT 0 AS count
```

---

## Appendix B: Example Use Cases

### Use Case 1: Bug Tracking Chain

```python
# Create bug entity
bug = await memory_graph.create_entity(
    entity_type="bug_fix",
    name="Login timeout issue",
    observations=[
        "Users experiencing timeout on login",
        "Occurs after 30 seconds",
        "Redis connection timeout suspected"
    ],
    tags=["bug", "authentication", "high-priority"]
)

# Create fix entity
fix = await memory_graph.create_entity(
    entity_type="decision",
    name="Increase Redis timeout to 60s",
    observations=[
        "Changed socket_timeout from 30s to 60s",
        "Applied to connection pool config"
    ],
    tags=["fix", "configuration"]
)

# Link bug → fix
await memory_graph.create_relation(
    from_entity="Increase Redis timeout to 60s",
    to_entity="Login timeout issue",
    relation_type="fixes"
)

# Create test entity
test = await memory_graph.create_entity(
    entity_type="task",
    name="Verify login timeout fix",
    observations=["Test with 100 concurrent users"],
    tags=["testing", "verification"]
)

# Link fix → test
await memory_graph.create_relation(
    from_entity="Verify login timeout fix",
    to_entity="Increase Redis timeout to 60s",
    relation_type="depends_on"
)
```

**Result**: Complete bug tracking chain: Bug → Fix → Test

### Use Case 2: Feature Implementation Timeline

```python
# Research phase
research = await memory_graph.create_entity(
    entity_type="context",
    name="Memory Graph Research 2025-10-03",
    observations=[
        "Evaluated Memory MCP capabilities",
        "Redis Stack provides graph operations",
        "RediSearch enables semantic search"
    ]
)

# Planning phase
plan = await memory_graph.create_entity(
    entity_type="decision",
    name="Memory Graph Architecture Plan",
    observations=[
        "Use DB 9 for memory graph",
        "Integrate with ChatHistoryManager",
        "4-phase rollout strategy"
    ]
)

await memory_graph.create_relation(
    from_entity="Memory Graph Research 2025-10-03",
    to_entity="Memory Graph Architecture Plan",
    relation_type="informs"
)

# Implementation phase
implementation = await memory_graph.create_entity(
    entity_type="feature",
    name="Memory Graph Implementation",
    observations=["Phase 1: Infrastructure complete"],
    metadata={"status": "in_progress"}
)

await memory_graph.create_relation(
    from_entity="Memory Graph Architecture Plan",
    to_entity="Memory Graph Implementation",
    relation_type="guides"
)
```

**Result**: Complete feature timeline with relationship tracking

### Use Case 3: Cross-Conversation Context

```python
# User asks about previous work in new conversation
session_id = "new-conversation-uuid"

# Get conversation context
context = await memory_graph.get_conversation_context(session_id)

# Context includes:
# - Related conversations (similar topics)
# - Relevant decisions (architectural choices)
# - Active tasks (ongoing work)
# - User preferences (customizations)

# AI uses context to provide informed response
response = await llm_service.generate_response(
    messages=[
        {"role": "system", "content": f"Context: {context['summary']}"},
        {"role": "user", "content": "What did we decide about the database?"}
    ]
)

# Response: "Based on our previous discussion, we decided to use
# Redis Stack for the Memory Graph (decision from 2025-10-03),
# specifically using DB 9 for entity storage..."
```

**Result**: AI responses include relevant context from previous conversations

---

**Document Version**: 1.0
**Last Updated**: 2025-10-03
**Status**: Ready for Implementation
