# ChatKnowledgeService Integration Guide

## Overview

The `ChatKnowledgeService` provides RAG (Retrieval-Augmented Generation) capabilities for the AutoBot chat system. It retrieves relevant knowledge from the knowledge base and formats it for inclusion in LLM prompts.

## Architecture

```
User Query → ChatWorkflowManager → ChatKnowledgeService → RAGService → KnowledgeBase
                                           ↓
                                    Format Context + Citations
                                           ↓
                                    LLM Prompt + Frontend Response
```

## Key Features

1. **Semantic Search**: Uses RAGService's advanced search with reranking
2. **Score Filtering**: Only includes high-quality, relevant facts (configurable threshold)
3. **Graceful Degradation**: Returns empty context on errors (doesn't break chat)
4. **Performance Logging**: Tracks retrieval time and result counts
5. **Citation Support**: Returns structured metadata for source attribution

## Installation

```python
# In chat_workflow_manager.py

from src.services.chat_knowledge_service import ChatKnowledgeService
from backend.services.rag_service import RAGService

# Initialize in __init__ method
self.rag_service = RAGService(knowledge_base=self.kb)
await self.rag_service.initialize()
self.knowledge_service = ChatKnowledgeService(self.rag_service)
```

## Integration into ChatWorkflowManager

### Step 1: Initialize Service

```python
class ChatWorkflowManager:
    def __init__(self, ...):
        # Existing initialization
        self.kb = kb

        # Add RAG integration
        self.rag_service = None
        self.knowledge_service = None

    async def initialize(self):
        """Initialize RAG services."""
        try:
            # Initialize RAGService
            self.rag_service = RAGService(knowledge_base=self.kb)
            await self.rag_service.initialize()

            # Initialize ChatKnowledgeService
            self.knowledge_service = ChatKnowledgeService(self.rag_service)
            logger.info("Knowledge service initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize knowledge service: {e}")
            # Continue without RAG - graceful degradation
```

### Step 2: Modify `_prepare_llm_request_params()`

```python
async def _prepare_llm_request_params(
    self, session: WorkflowSession, message: str
) -> Dict[str, Any]:
    """
    Prepare LLM request parameters including endpoint, model, and prompt.

    Now includes knowledge context from RAG system.
    """

    # [Existing code for endpoint, system_prompt, conversation_context...]

    # ============================================
    # NEW: Retrieve relevant knowledge
    # ============================================
    knowledge_context = ""
    citations = []

    if self.knowledge_service:
        try:
            knowledge_context, citations = await self.knowledge_service.retrieve_relevant_knowledge(
                query=message,
                top_k=5,  # Maximum 5 knowledge facts
                score_threshold=0.7  # Only high-quality facts (score > 0.7)
            )

            if knowledge_context:
                logger.info(f"Added {len(citations)} knowledge facts to context")
            else:
                logger.debug("No relevant knowledge found for query")

        except Exception as e:
            logger.error(f"Knowledge retrieval failed: {e}")
            # Continue without knowledge - graceful degradation

    # ============================================
    # Build complete prompt with knowledge
    # ============================================
    full_prompt = (
        system_prompt
        + ("\n\n" + knowledge_context if knowledge_context else "")  # Add knowledge if available
        + conversation_context
        + f"\n**Current user message:** {message}\n\nAssistant:"
    )

    # Store citations in session for frontend
    session.last_citations = citations

    return {
        "endpoint": ollama_endpoint,
        "model": selected_model,
        "prompt": full_prompt,
        "citations": citations,  # Include for response metadata
    }
```

### Step 3: Include Citations in Response

```python
async def process_message(self, session_id: str, message: str) -> Dict[str, Any]:
    """
    Process chat message and return response with citations.
    """
    # [Existing message processing code...]

    # Get LLM parameters (now includes citations)
    llm_params = await self._prepare_llm_request_params(session, message)

    # [Make LLM request, get response...]

    # Return response with citations
    return {
        "response": llm_response_text,
        "citations": llm_params.get("citations", []),  # Knowledge sources
        "session_id": session_id,
        # ... other metadata ...
    }
```

## Configuration Options

### Default Configuration

```python
# Default values in ChatKnowledgeService.retrieve_relevant_knowledge()
top_k=5              # Maximum number of facts to retrieve
score_threshold=0.7  # Minimum relevance score (0.0-1.0)
```

### Recommended Settings by Use Case

```python
# High precision (only very relevant facts)
top_k=3
score_threshold=0.85

# Balanced (default)
top_k=5
score_threshold=0.7

# High recall (more facts, lower quality threshold)
top_k=10
score_threshold=0.5

# No knowledge augmentation
knowledge_service=None  # Simply don't initialize the service
```

## Output Format

### Knowledge Context String

```
KNOWLEDGE CONTEXT:
1. [score: 0.92] Redis is configured in config/redis.yaml
2. [score: 0.82] Use redis-cli to connect to Redis
3. [score: 0.75] Redis default port is 6379
```

This string is prepended to the LLM prompt to provide relevant context.

### Citation List

```python
[
    {
        "id": "fact1",
        "content": "Redis is configured in config/redis.yaml",
        "score": 0.92,
        "source": "docs/redis.md",
        "rank": 1,
        "metadata": {
            "semantic_score": 0.95,
            "keyword_score": 0.8,
            "hybrid_score": 0.9,
            "rerank_score": 0.92,
            "chunk_index": 0
        }
    },
    # ... more citations ...
]
```

This list can be sent to the frontend for displaying knowledge sources.

## Error Handling

The service is designed for **graceful degradation**:

```python
# If RAG service fails
→ Returns empty context ("") and empty citations ([])
→ Chat continues without knowledge augmentation
→ Error logged but not propagated

# If knowledge base is empty
→ Returns empty context and empty citations
→ Normal chat flow continues

# If filtering removes all results
→ Returns empty context and empty citations
→ Normal chat flow continues
```

**The chat system NEVER breaks due to knowledge retrieval failures.**

## Performance Considerations

### Retrieval Time

- **Typical**: 100-300ms for semantic search + reranking
- **Cached**: <10ms for repeated queries (RAGService cache)
- **Timeout**: Configurable in RAGConfig (default 5s)

### Optimization Tips

1. **Adjust top_k**: Smaller values = faster retrieval
2. **Score threshold**: Higher threshold = fewer results to format
3. **Enable caching**: RAGService caches results for 5 minutes by default
4. **Monitor logs**: Check retrieval times in chat_knowledge_service logs

```python
# Example log output
INFO: Retrieved 3/5 facts (threshold: 0.7) in 0.245s
```

## Testing

### Unit Tests

```bash
# Run ChatKnowledgeService tests
pytest tests/unit/test_chat_knowledge_service.py -v

# Run with coverage
pytest tests/unit/test_chat_knowledge_service.py --cov=src.services.chat_knowledge_service
```

### Integration Testing

```python
# Manual integration test
from src.services.chat_knowledge_service import ChatKnowledgeService
from backend.services.rag_service import RAGService

# Initialize with real knowledge base
rag_service = RAGService(knowledge_base)
await rag_service.initialize()

knowledge_service = ChatKnowledgeService(rag_service)

# Test retrieval
context, citations = await knowledge_service.retrieve_relevant_knowledge(
    query="How do I configure Redis?",
    top_k=5,
    score_threshold=0.7
)

print(f"Context:\n{context}")
print(f"\nCitations: {len(citations)} sources")
```

## Monitoring

### Key Metrics to Track

```python
# Get service statistics
stats = await knowledge_service.get_knowledge_stats()

{
    "service": "ChatKnowledgeService",
    "rag_service_initialized": true,
    "rag_cache_entries": 15,
    "kb_implementation": "KnowledgeBaseV2"
}
```

### Logging

All operations are logged to the `chat_knowledge_service` logger:

```python
# Successful retrieval
INFO: Retrieved 3/5 facts (threshold: 0.7) in 0.245s

# Filtering
DEBUG: Filtered out result (score 0.62 < 0.7): Redis default port is...

# Error handling
ERROR: Knowledge retrieval failed for query 'test...': Connection timeout
DEBUG: Returning empty knowledge context due to error
```

## Troubleshooting

### No Knowledge Context Being Added

**Symptoms**: `context == ""` and `citations == []`

**Possible Causes**:
1. No relevant documents in knowledge base
2. Score threshold too high (all results filtered out)
3. RAG service not initialized
4. Knowledge base empty

**Solutions**:
```python
# Check service status
stats = await knowledge_service.get_knowledge_stats()
logger.info(f"Service stats: {stats}")

# Lower threshold temporarily
context, citations = await knowledge_service.retrieve_relevant_knowledge(
    query=message,
    score_threshold=0.5  # Lower from 0.7
)

# Check RAG service directly
results, metrics = await rag_service.advanced_search(query=message, max_results=10)
logger.info(f"RAG returned {len(results)} results")
```

### Knowledge Context Too Large

**Symptoms**: LLM prompts exceeding token limits

**Solutions**:
```python
# Reduce top_k
context, citations = await knowledge_service.retrieve_relevant_knowledge(
    query=message,
    top_k=3,  # Reduce from 5
    score_threshold=0.8  # Increase threshold
)

# Or truncate context manually
if len(knowledge_context) > 1000:
    knowledge_context = knowledge_context[:1000] + "..."
```

### Slow Retrieval Performance

**Symptoms**: Retrieval time > 500ms

**Solutions**:
```python
# Check if caching is working
rag_stats = rag_service.get_stats()
logger.info(f"Cache entries: {rag_stats['cache_entries']}")

# Reduce reranking overhead
results, metrics = await rag_service.advanced_search(
    query=message,
    max_results=3,
    enable_reranking=False  # Disable if too slow
)

# Monitor metrics
logger.info(f"Retrieval time: {metrics.retrieval_time:.3f}s")
logger.info(f"Reranking time: {metrics.reranking_time:.3f}s")
```

## Advanced Usage

### Custom Score Thresholds Per Query Type

```python
# Adjust threshold based on query complexity
def get_score_threshold(query: str) -> float:
    if any(word in query.lower() for word in ["how", "what", "configure"]):
        return 0.6  # Lower threshold for questions
    else:
        return 0.8  # Higher threshold for statements

threshold = get_score_threshold(message)
context, citations = await knowledge_service.retrieve_relevant_knowledge(
    query=message,
    score_threshold=threshold
)
```

### Combining with Conversation History

```python
# Expand query with conversation context for better retrieval
expanded_query = message
if session.conversation_history:
    last_exchange = session.conversation_history[-1]
    expanded_query = f"{last_exchange['user']} {message}"

context, citations = await knowledge_service.retrieve_relevant_knowledge(
    query=expanded_query,
    top_k=5
)
```

## Future Enhancements

Planned improvements for Phase 2+:

- **Query expansion**: Automatically expand queries for better recall
- **Citation tracking**: Track which citations were actually used in response
- **Feedback loop**: Learn from user interactions to improve retrieval
- **Context caching**: Cache knowledge context per session
- **Multi-turn awareness**: Use conversation history for retrieval

## References

- **RAGService**: `/home/kali/Desktop/AutoBot/backend/services/rag_service.py`
- **ChatWorkflowManager**: `/home/kali/Desktop/AutoBot/src/chat_workflow_manager.py`
- **AdvancedRAGOptimizer**: `/home/kali/Desktop/AutoBot/src/advanced_rag_optimizer.py`
- **Tests**: `/home/kali/Desktop/AutoBot/tests/unit/test_chat_knowledge_service.py`
