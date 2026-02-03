# ChatKnowledgeService - Quick Reference

## 1-Minute Overview

**What**: Service layer for adding RAG knowledge to chat prompts
**Where**: `src/services/chat_knowledge_service.py`
**Purpose**: Retrieve relevant facts from knowledge base and format for LLM

## Basic Usage

```python
# Initialize
from src.services.chat_knowledge_service import ChatKnowledgeService
from backend.services.rag_service import RAGService

rag_service = RAGService(knowledge_base)
await rag_service.initialize()
knowledge_service = ChatKnowledgeService(rag_service)

# Retrieve knowledge
context, citations = await knowledge_service.retrieve_relevant_knowledge(
    query="How to configure Redis?",
    top_k=5,              # Max 5 facts
    score_threshold=0.7   # Min score 0.7
)

# Use in prompt
prompt = system_prompt + "\n\n" + context + "\n\n" + user_message
```

## Key Methods

### `retrieve_relevant_knowledge(query, top_k=5, score_threshold=0.7)`
Returns: `(context_string, citations_list)`
- `context_string`: Formatted text for LLM prompt
- `citations_list`: List of dicts with metadata

### `format_knowledge_context(facts)`
Returns: `str` - Formatted context string

### `format_citations(facts)`
Returns: `List[Dict]` - Citation objects for frontend

### `get_knowledge_stats()`
Returns: `Dict` - Service statistics

## Output Examples

**Context String**:
```
KNOWLEDGE CONTEXT:
1. [score: 0.92] Redis is configured in config/redis.yaml
2. [score: 0.82] Use redis-cli to connect to Redis
```

**Citation**:
```python
{
    "id": "fact1",
    "content": "Redis is configured in config/redis.yaml",
    "score": 0.92,
    "source": "docs/redis.md",
    "rank": 1,
    "metadata": {...}
}
```

## Error Handling

**Graceful degradation** - Always returns empty results on error:
```python
try:
    context, citations = await service.retrieve_relevant_knowledge(...)
except Exception:
    # Never happens - errors caught internally
    pass

# On error: context="" and citations=[]
# Chat continues normally without knowledge
```

## Configuration Tips

**High Precision** (strict):
```python
top_k=3, score_threshold=0.85
```

**Balanced** (default):
```python
top_k=5, score_threshold=0.7
```

**High Recall** (more facts):
```python
top_k=10, score_threshold=0.5
```

## Performance

- **Typical**: 100-300ms
- **Cached**: <10ms
- **Logged**: All retrieval times logged automatically

## Testing

```bash
# Run tests
pytest tests/unit/test_chat_knowledge_service.py -v

# Import test
python3 -c "from src.services.chat_knowledge_service import ChatKnowledgeService"
```

## Integration Checklist

- [ ] Initialize RAGService with knowledge base
- [ ] Initialize ChatKnowledgeService with RAGService
- [ ] Call `retrieve_relevant_knowledge()` in prompt preparation
- [ ] Add context to LLM prompt
- [ ] Include citations in response metadata
- [ ] Display citations in frontend (optional)

## Common Issues

**No context returned**: Check score_threshold (try 0.5)
**Too slow**: Reduce top_k or disable reranking
**Empty knowledge base**: Verify knowledge base has documents

## Files

- Implementation: `src/services/chat_knowledge_service.py`
- Tests: `tests/unit/test_chat_knowledge_service.py`
- Full Guide: `docs/developer/CHAT_KNOWLEDGE_SERVICE_INTEGRATION.md`
- Deliverables: `docs/phase1-rag-integration-deliverables.md`
