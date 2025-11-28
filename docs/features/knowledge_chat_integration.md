# Knowledge-Enhanced Chat Integration

**GitHub Issue:** [#249](https://github.com/mrveiss/AutoBot-AI/issues/249)
**Date:** 2025-09-29
**Status:** Planning
**Priority:** High - Core AutoBot functionality

---

## Overview

Integrate the Knowledge Manager's 14,000+ vector-indexed facts into the chat system to enable:
- **Contextual responses** using stored knowledge
- **RAG (Retrieval-Augmented Generation)** for accurate answers
- **Automatic knowledge retrieval** based on conversation context
- **Source citations** from knowledge base

---

## Current Architecture

### Knowledge Manager (✅ Operational)
- **Location**: `src/knowledge_base_v2.py`
- **Vectors**: 14,047 indexed with 768-dimensional embeddings
- **Search**: Semantic search via LlamaIndex + Redis
- **API**: `/api/knowledge_base/search` endpoint available

### Chat System
- **Location**: `backend/api/chat.py`
- **LLM**: Ollama integration (llama3.2:3b)
- **WebSocket**: Real-time streaming responses
- **State**: Manages conversation history

---

## Recommended Integration Approach

### **Option 1: RAG Pipeline Integration (RECOMMENDED)**

**Architecture:**
```
User Query → Query Analysis → Knowledge Retrieval → Context Augmentation → LLM Response
```

**Implementation:**

1. **Query Analysis Layer**
   - Detect if query benefits from knowledge base
   - Extract key terms for semantic search
   - Determine search scope (category, recency, etc.)

2. **Knowledge Retrieval**
   ```python
   # In chat endpoint before LLM call
   relevant_facts = await knowledge_base.search(
       query=user_message,
       top_k=5  # Retrieve top 5 most relevant facts
   )
   ```

3. **Context Augmentation**
   ```python
   # Build enhanced prompt with retrieved knowledge
   context = "\n\n".join([f"- {fact['content']}" for fact in relevant_facts])

   augmented_prompt = f"""You are AutoBot assistant. Answer using the following knowledge context:

   KNOWLEDGE CONTEXT:
   {context}

   USER QUESTION: {user_message}

   Provide an accurate answer based on the knowledge context. If the context doesn't contain relevant information, say so."""
   ```

4. **LLM Generation**
   - Send augmented prompt to Ollama
   - Stream response back to user
   - Include source citations

**File Changes:**
- **`backend/api/chat.py`**: Add RAG pipeline before LLM call
- **`src/agents/chat_agent.py`**: Integrate knowledge retrieval
- **`src/agents/rag_agent.py`**: Enhanced RAG orchestration

**Advantages:**
- ✅ Most accurate - uses actual stored knowledge
- ✅ Cites sources from knowledge base
- ✅ Reduces hallucinations
- ✅ Handles 14,000+ facts efficiently
- ✅ Automatic relevance ranking via vector search

**Considerations:**
- Latency: +100-300ms for knowledge retrieval
- Context window: Must fit retrieved facts + query + response
- Relevance threshold: Only use highly relevant facts (score > 0.7)

---

### **Option 2: Agent-Based Knowledge Integration**

**Architecture:**
```
User Query → Agent Router → Knowledge Agent (if needed) → Response Agent → User
```

**Implementation:**

1. **Create Knowledge-Aware Agent**
   ```python
   # src/agents/knowledge_chat_agent.py
   class KnowledgeChatAgent:
       async def should_use_knowledge(self, query: str) -> bool:
           """Determine if query needs knowledge base"""
           keywords = ["what is", "how to", "explain", "tell me about"]
           return any(kw in query.lower() for kw in keywords)

       async def get_response(self, query: str) -> str:
           if await self.should_use_knowledge(query):
               facts = await self.kb.search(query, top_k=3)
               return await self.generate_with_knowledge(query, facts)
           else:
               return await self.generate_direct(query)
   ```

2. **Agent Orchestration**
   - Route queries through agent system
   - Knowledge agent decides when to retrieve
   - Other agents handle non-knowledge queries

**File Changes:**
- **`src/agents/knowledge_chat_agent.py`**: New agent
- **`src/agents/agent_orchestrator.py`**: Route to knowledge agent
- **`backend/api/chat.py`**: Use orchestrator

**Advantages:**
- ✅ Flexible - can combine multiple agents
- ✅ Extensible - easy to add more agents
- ✅ Selective - only uses KB when beneficial

**Considerations:**
- More complex architecture
- Requires agent routing logic
- Potential for routing errors

---

###  **Option 3: Hybrid Approach (BEST FOR AUTOBOT)**

**Combine RAG + Agents for optimal flexibility:**

```python
# backend/api/chat.py - Enhanced chat endpoint

async def chat_with_knowledge(message: str, session_id: str):
    # 1. Check if knowledge might be helpful
    query_analysis = await analyze_query_intent(message)

    # 2. Retrieve knowledge if beneficial
    knowledge_context = []
    if query_analysis.needs_knowledge:
        knowledge_context = await knowledge_base.search(
            query=message,
            top_k=5
        )

    # 3. Route through agent orchestrator with knowledge
    response = await agent_orchestrator.process(
        message=message,
        knowledge_context=knowledge_context,
        session_id=session_id
    )

    # 4. Stream response with citations
    async for chunk in response:
        yield chunk
```

**Advantages:**
- ✅ Best of both worlds
- ✅ Efficient knowledge retrieval
- ✅ Agent flexibility
- ✅ Automatic relevance detection

---

## Implementation Plan

### **Phase 1: Basic RAG Integration (2-4 hours)**

1. **Add RAG to Chat Endpoint**
   ```python
   # File: backend/api/chat.py

   @router.post("/message")
   async def chat_message(request: ChatRequest):
       # Get knowledge base instance
       kb = request.app.state.knowledge_base

       # Search for relevant knowledge
       relevant_facts = await kb.search(request.message, top_k=5)

       # Build context
       if relevant_facts:
           context = "\n".join([f"- {f['content']}" for f in relevant_facts])
           augmented_message = f"Context: {context}\n\nQuestion: {request.message}"
       else:
           augmented_message = request.message

       # Get LLM response with context
       response = await llm_interface.chat(augmented_message)
       return response
   ```

2. **Add Knowledge Toggle**
   - Frontend checkbox: "Use knowledge base"
   - API parameter: `use_knowledge: bool = True`
   - Allow users to disable for pure LLM chat

3. **Add Citation Display**
   - Return source fact IDs with response
   - Display "Sources: [1] [2] [3]" in UI
   - Allow clicking sources to view full fact

### **Phase 2: Smart Knowledge Retrieval (4-6 hours)**

1. **Query Intent Detection**
   ```python
   async def analyze_query_intent(query: str) -> QueryAnalysis:
       """Determine if query needs knowledge"""
       # Patterns that benefit from knowledge
       knowledge_patterns = [
           r"what is",
           r"how (do|to)",
           r"explain",
           r"tell me about",
           r"define",
           r"describe"
       ]

       needs_knowledge = any(
           re.search(pattern, query.lower())
           for pattern in knowledge_patterns
       )

       return QueryAnalysis(
           needs_knowledge=needs_knowledge,
           confidence=0.8 if needs_knowledge else 0.2
       )
   ```

2. **Relevance Filtering**
   - Only use facts with score > 0.7
   - Limit to top 3-5 most relevant
   - Avoid irrelevant context pollution

3. **Category-Aware Search**
   - Extract category hints from query
   - Filter knowledge by category
   - Improve search precision

### **Phase 3: Advanced Features (6-8 hours)**

1. **Conversation-Aware RAG**
   - Track conversation topics
   - Maintain relevant knowledge cache
   - Update search based on conversation flow

2. **Multi-turn Knowledge**
   - Remember what knowledge was used
   - Avoid re-retrieving same facts
   - Build conversation knowledge graph

3. **Knowledge Updates from Chat**
   - "Remember this: <fact>" command
   - Store new facts during conversation
   - Automatic fact extraction

---

## API Endpoints

### Enhanced Chat Endpoint

```http
POST /api/chat/message
Content-Type: application/json

{
  "message": "What is the ls command?",
  "session_id": "abc123",
  "use_knowledge": true,
  "knowledge_options": {
    "top_k": 5,
    "score_threshold": 0.7,
    "categories": ["commands"]
  }
}

Response (streaming):
{
  "content": "The ls command lists directory contents...",
  "sources": [
    {
      "fact_id": "uuid-123",
      "content": "ls - list directory contents",
      "score": 0.95,
      "category": "commands"
    }
  ],
  "used_knowledge": true
}
```

### Knowledge Search Endpoint (Existing)

```http
POST /api/knowledge_base/search
Content-Type: application/json

{
  "query": "ls command",
  "top_k": 5
}

Response:
[
  {
    "content": "ls - list directory contents",
    "score": 0.95,
    "metadata": {"category": "commands"},
    "node_id": "uuid-123"
  }
]
```

---

## Frontend Integration

### **Chat Interface Updates**

1. **Knowledge Toggle**
   ```vue
   <template>
     <div class="chat-controls">
       <label>
         <input type="checkbox" v-model="useKnowledge" />
         Use Knowledge Base
       </label>
     </div>
   </template>
   ```

2. **Source Citations**
   ```vue
   <template>
     <div class="message-sources" v-if="message.sources">
       <span>Sources:</span>
       <a
         v-for="source in message.sources"
         :key="source.fact_id"
         @click="viewSource(source)"
         class="source-link"
       >
         [{{ source.score.toFixed(2) }}]
       </a>
     </div>
   </template>
   ```

3. **Knowledge Indicator**
   - Show 🧠 icon when knowledge is used
   - Display "Using knowledge base..." during retrieval
   - Show number of facts retrieved

### **Knowledge Panel**

1. **Retrieved Facts Display**
   - Show facts used in current response
   - Highlight relevant portions
   - Allow expanding to full fact

2. **Knowledge Search**
   - Standalone search interface
   - Browse knowledge by category
   - View all indexed facts

---

## Performance Considerations

### **Latency Targets**
- Knowledge retrieval: < 200ms
- Context augmentation: < 50ms
- Total overhead: < 250ms
- Streaming start: < 500ms (total)

### **Optimization Strategies**

1. **Caching**
   ```python
   @lru_cache(maxsize=100)
   async def get_cached_knowledge(query_hash: str):
       return await knowledge_base.search(query)
   ```

2. **Parallel Processing**
   ```python
   # Retrieve knowledge and start LLM simultaneously
   knowledge_task = asyncio.create_task(kb.search(query))
   llm_task = asyncio.create_task(llm.prepare(query))

   knowledge = await knowledge_task
   # Augment and continue with LLM
   ```

3. **Relevance Pre-filtering**
   - Quick keyword check before vector search
   - Skip retrieval for obviously irrelevant queries
   - Reduce unnecessary vector operations

---

## Testing Strategy

### **Unit Tests**

1. **Knowledge Retrieval**
   ```python
   async def test_knowledge_retrieval():
       facts = await kb.search("ls command", top_k=5)
       assert len(facts) > 0
       assert facts[0]['score'] > 0.7
   ```

2. **Context Augmentation**
   ```python
   async def test_context_building():
       facts = [{"content": "ls lists files"}]
       context = build_context(facts)
       assert "ls lists files" in context
   ```

3. **RAG Pipeline**
   ```python
   async def test_rag_pipeline():
       response = await chat_with_knowledge("what is ls?")
       assert "lists" in response.lower()
       assert len(response.sources) > 0
   ```

### **Integration Tests**

1. **End-to-End Chat**
   - Send query through API
   - Verify knowledge retrieval
   - Check response quality
   - Validate source citations

2. **Performance Tests**
   - Measure retrieval latency
   - Test with 1000+ concurrent queries
   - Verify caching effectiveness

---

## Monitoring & Metrics

### **Key Metrics to Track**

1. **Usage Metrics**
   - % of queries using knowledge
   - Average facts retrieved per query
   - Knowledge vs non-knowledge queries

2. **Performance Metrics**
   - Knowledge retrieval time (p50, p95, p99)
   - Total RAG overhead
   - Cache hit rate

3. **Quality Metrics**
   - Average relevance score
   - User satisfaction (thumbs up/down)
   - Knowledge usefulness rate

### **Logging**

```python
logger.info(
    "Knowledge retrieval",
    extra={
        "query": query,
        "facts_retrieved": len(facts),
        "top_score": facts[0]['score'] if facts else 0,
        "retrieval_ms": retrieval_time,
        "used_in_response": True
    }
)
```

---

## Security & Privacy

1. **Knowledge Access Control**
   - Filter knowledge by user permissions
   - Respect category access levels
   - Audit knowledge access

2. **Sensitive Information**
   - Mark facts as sensitive/private
   - Exclude from general retrieval
   - Require explicit access

3. **Rate Limiting**
   - Limit knowledge queries per minute
   - Prevent knowledge base DoS
   - Cache to reduce load

---

## Next Steps

### **Immediate (Week 1)**
1. ✅ Fix stats display (COMPLETED)
2. Implement basic RAG integration
3. Add knowledge toggle to UI
4. Test with sample queries

### **Short-term (Week 2-3)**
5. Add smart query intent detection
6. Implement relevance filtering
7. Add source citations display
8. Performance optimization

### **Long-term (Month 2)**
9. Conversation-aware RAG
10. Multi-turn knowledge tracking
11. Knowledge updates from chat
12. Advanced analytics

---

## Related Documentation

- **Knowledge Manager Fix**: [`docs/fixes/knowledge_manager_vector_indexing_fix.md`](../fixes/knowledge_manager_vector_indexing_fix.md)
- **Chat API**: [`backend/api/chat.py`](../../backend/api/chat.py)
- **Knowledge Base V2**: [`src/knowledge_base_v2.py`](../../src/knowledge_base_v2.py)
- **RAG Agent**: [`src/agents/rag_agent.py`](../../src/agents/rag_agent.py)

---

**Status**: Ready for implementation
**Recommended Approach**: Hybrid (RAG + Agents)
**Estimated Effort**: 12-18 hours total
**Expected Impact**: High - Core differentiator for AutoBot