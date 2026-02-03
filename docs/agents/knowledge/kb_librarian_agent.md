# KB Librarian Agent

## Overview

The KB Librarian Agent provides intelligent knowledge base search and retrieval capabilities. It automatically detects questions in user requests, searches the knowledge base for relevant information, and provides structured summaries with source attribution.

## System Integration & Interactions

### Architecture Position
```
User Question → Agent Orchestrator → KB Librarian Agent
                                           ↓
┌─────────────────────────────────────────────────────────────┐
│                KB Librarian Agent                           │
├─────────────────────────────────────────────────────────────┤
│ • Question detection and analysis                          │
│ • Knowledge base search and retrieval                      │
│ • Context-aware result ranking                             │
│ • Intelligent summarization                                │
└─────────────────┬───────────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    ▼             ▼             ▼
┌─────────┐ ┌─────────────┐ ┌─────────────┐
│Knowledge│ │   Redis     │ │ Semantic    │
│Base     │ │   Cache     │ │ Chunker     │
│(SQLite) │ │             │ │             │
└─────────┘ └─────────────┘ └─────────────┘
```

### Core System Interactions

#### 1. **Knowledge Base Integration**
```python
class KBLibrarianAgent:
    def __init__(self):
        # Direct integration with AutoBot's knowledge base
        self.knowledge_base = KnowledgeBase()
        self.semantic_chunker = SemanticChunker()
        
        # Configuration
        self.similarity_threshold = 0.7
        self.max_results = 10
        self.auto_summarize = True
        
    async def search_knowledge_base(self, query: str, context: dict = None) -> List[dict]:
        """Search knowledge base with semantic understanding"""
        
        # Use semantic chunking for better query understanding
        processed_query = await self.semantic_chunker.process_query(query)
        
        # Search knowledge base
        search_results = await self.knowledge_base.search_chunks(
            query=processed_query,
            limit=self.max_results,
            similarity_threshold=self.similarity_threshold
        )
        
        return search_results
```

**System Interactions:**
- **Knowledge Base**: Direct connection to SQLite-based knowledge storage
- **Semantic Chunker**: Uses embedding-based query processing for better results
- **Vector Search**: Leverages semantic similarity for relevant document retrieval
- **Metadata Integration**: Accesses document metadata for context and attribution

#### 2. **Redis Caching Integration**
```python
class KBLibrarianCache:
    """Caching layer for KB Librarian operations"""
    
    def __init__(self):
        self.redis_client = get_redis_client()
        self.cache_prefix = "autobot:kb_librarian:"
        self.cache_ttl = 3600  # 1 hour
        
    async def get_cached_search(self, query: str) -> Optional[dict]:
        """Retrieve cached search results"""
        cache_key = f"{self.cache_prefix}search:{hashlib.md5(query.encode()).hexdigest()}"
        
        cached_result = await self.redis_client.get(cache_key)
        if cached_result:
            return json.loads(cached_result)
        return None
        
    async def cache_search_results(self, query: str, results: dict):
        """Cache search results for faster retrieval"""
        cache_key = f"{self.cache_prefix}search:{hashlib.md5(query.encode()).hexdigest()}"
        
        await self.redis_client.setex(
            cache_key,
            self.cache_ttl,
            json.dumps(results, default=str)
        )
```

**System Interactions:**
- **Redis Client**: Uses centralized Redis connection for caching
- **Query Caching**: Caches search results to improve response times
- **Session State**: Maintains user context and search history
- **Cache Invalidation**: Automatically expires stale search results

#### 3. **Question Detection System**
```python
class QuestionDetector:
    """Detects and analyzes questions in user input"""
    
    def __init__(self):
        self.question_patterns = [
            r'\b(what|who|when|where|why|how|which|can|could|would|should|is|are|will|do|does|did)\b',
            r'\?$',  # Ends with question mark
            r'\b(explain|describe|tell me|show me|help me understand)\b',
            r'\b(definition of|meaning of|purpose of)\b'
        ]
        
    def is_question(self, text: str) -> bool:
        """Determine if input text contains a question"""
        text_lower = text.lower().strip()
        
        # Check for question patterns
        for pattern in self.question_patterns:
            if re.search(pattern, text_lower):
                return True
                
        return False
        
    def extract_question_type(self, text: str) -> str:
        """Classify the type of question"""
        text_lower = text.lower()
        
        if any(word in text_lower for word in ['what', 'definition', 'meaning']):
            return 'definition'
        elif any(word in text_lower for word in ['how', 'explain', 'describe']):
            return 'explanation'
        elif any(word in text_lower for word in ['when', 'where']):
            return 'factual'
        elif any(word in text_lower for word in ['why', 'purpose']):
            return 'reasoning'
        else:
            return 'general'
```

**System Interactions:**
- **NLP Processing**: Uses pattern matching and semantic analysis
- **Classification Integration**: Works with classification agents for intent detection
- **Context Analysis**: Analyzes conversation context for better question understanding

#### 4. **API Endpoint Integration**
```python
# FastAPI endpoint integration
@router.post("/kb/search")
async def kb_search_endpoint(request: KBSearchRequest):
    """API endpoint for knowledge base search"""
    
    kb_librarian = get_kb_librarian_agent()
    
    # Process search request
    results = await kb_librarian.process_query(
        query=request.query,
        context=request.context,
        user_id=request.user_id
    )
    
    return KBSearchResponse(
        results=results['results'],
        summary=results.get('summary'),
        sources=results.get('sources', []),
        confidence=results.get('confidence', 0.0),
        processing_time=results.get('processing_time', 0)
    )

@router.get("/kb/recent-searches")
async def get_recent_searches(user_id: str, limit: int = 10):
    """Get user's recent knowledge base searches"""
    
    kb_librarian = get_kb_librarian_agent()
    recent_searches = await kb_librarian.get_user_search_history(user_id, limit)
    
    return {
        "searches": recent_searches,
        "total_count": len(recent_searches)
    }
```

**System Interactions:**
- **FastAPI Integration**: Provides REST API endpoints for KB operations
- **User Context**: Integrates with user management and session handling
- **Request Validation**: Uses Pydantic models for request/response validation
- **Authentication**: Integrates with security layer for user authentication

## Core Functionality

### 1. **Intelligent Query Processing**
```python
async def process_query(self, query: str, context: dict = None, 
                       user_id: str = None) -> dict:
    """
    Process a knowledge base query with intelligent analysis
    
    Args:
        query: User's search query or question
        context: Conversation context and metadata
        user_id: User identifier for personalization
        
    Returns:
        Dict containing search results, summary, and metadata
    """
    
    # Step 1: Query analysis and enhancement
    analyzed_query = await self._analyze_query(query, context)
    
    # Step 2: Check cache for recent similar queries
    cached_result = await self.cache.get_cached_search(analyzed_query['processed_query'])
    if cached_result:
        cached_result['from_cache'] = True
        return cached_result
    
    # Step 3: Execute knowledge base search
    search_results = await self._execute_search(analyzed_query)
    
    # Step 4: Rank and filter results
    ranked_results = await self._rank_results(search_results, analyzed_query)
    
    # Step 5: Generate summary if requested
    summary = None
    if self.auto_summarize and len(ranked_results) > 0:
        summary = await self._generate_summary(ranked_results, query)
    
    # Step 6: Prepare response
    response = {
        'results': ranked_results,
        'summary': summary,
        'query_analysis': analyzed_query,
        'sources': self._extract_sources(ranked_results),
        'confidence': self._calculate_confidence(ranked_results),
        'processing_time': time.time() - start_time,
        'from_cache': False
    }
    
    # Step 7: Cache results for future use
    await self.cache.cache_search_results(analyzed_query['processed_query'], response)
    
    # Step 8: Log search for analytics
    await self._log_search_activity(user_id, query, response)
    
    return response
```

### 2. **Context-Aware Search Enhancement**
```python
async def _analyze_query(self, query: str, context: dict = None) -> dict:
    """Enhance query with context and semantic analysis"""
    
    analysis = {
        'original_query': query,
        'processed_query': query,
        'question_type': self.question_detector.extract_question_type(query),
        'is_question': self.question_detector.is_question(query),
        'keywords': [],
        'entities': [],
        'context_enhanced': False
    }
    
    # Extract key terms and entities
    analysis['keywords'] = self._extract_keywords(query)
    analysis['entities'] = self._extract_entities(query)
    
    # Context enhancement
    if context:
        # Use conversation history for context
        if 'conversation_history' in context:
            enhanced_query = await self._enhance_with_conversation_context(
                query, context['conversation_history']
            )
            if enhanced_query != query:
                analysis['processed_query'] = enhanced_query
                analysis['context_enhanced'] = True
        
        # Use document context if available
        if 'document_context' in context:
            analysis['document_filter'] = context['document_context']
    
    return analysis

async def _enhance_with_conversation_context(self, query: str, 
                                           conversation_history: List[dict]) -> str:
    """Enhance query using conversation context"""
    
    # Look for relevant context in recent messages
    recent_context = []
    for msg in conversation_history[-5:]:  # Last 5 messages
        if msg.get('type') in ['user', 'assistant'] and 'content' in msg:
            recent_context.append(msg['content'])
    
    if not recent_context:
        return query
    
    # Use LLM to enhance query with context
    enhancement_prompt = f"""
    Given this conversation context and the current query, enhance the query to be more specific and searchable:
    
    Recent conversation:
    {' '.join(recent_context[-3:])}
    
    Current query: {query}
    
    Enhanced query (keep it concise and focused):
    """
    
    try:
        enhanced = await self.llm_interface.quick_completion(enhancement_prompt)
        return enhanced.strip() if enhanced else query
    except:
        return query
```

### 3. **Result Ranking and Filtering**
```python
async def _rank_results(self, search_results: List[dict], 
                       query_analysis: dict) -> List[dict]:
    """Rank search results based on relevance and context"""
    
    scored_results = []
    
    for result in search_results:
        score = await self._calculate_result_score(result, query_analysis)
        
        scored_result = {
            **result,
            'relevance_score': score,
            'ranking_factors': {
                'semantic_similarity': result.get('similarity_score', 0),
                'keyword_matches': self._count_keyword_matches(result, query_analysis),
                'entity_matches': self._count_entity_matches(result, query_analysis),
                'document_freshness': self._calculate_freshness_score(result),
                'source_authority': self._calculate_authority_score(result)
            }
        }
        
        scored_results.append(scored_result)
    
    # Sort by combined relevance score
    ranked_results = sorted(scored_results, key=lambda x: x['relevance_score'], reverse=True)
    
    # Apply similarity threshold filtering
    filtered_results = [
        result for result in ranked_results 
        if result['relevance_score'] >= self.similarity_threshold
    ]
    
    return filtered_results[:self.max_results]

async def _calculate_result_score(self, result: dict, query_analysis: dict) -> float:
    """Calculate comprehensive relevance score for a search result"""
    
    # Base semantic similarity score
    base_score = result.get('similarity_score', 0.0)
    
    # Keyword matching bonus
    keyword_bonus = self._count_keyword_matches(result, query_analysis) * 0.1
    
    # Entity matching bonus
    entity_bonus = self._count_entity_matches(result, query_analysis) * 0.15
    
    # Question type matching bonus
    question_type_bonus = 0.0
    if query_analysis['question_type'] == 'definition':
        if any(word in result.get('content', '').lower() 
               for word in ['definition', 'meaning', 'refers to', 'is defined as']):
            question_type_bonus = 0.2
    
    # Document freshness factor
    freshness_factor = self._calculate_freshness_score(result)
    
    # Combine all factors
    final_score = (
        base_score * 0.6 +  # Semantic similarity (primary factor)
        keyword_bonus +     # Keyword matches
        entity_bonus +      # Entity matches
        question_type_bonus + # Question type relevance
        freshness_factor * 0.1  # Document freshness
    )
    
    return min(final_score, 1.0)  # Cap at 1.0
```

### 4. **Intelligent Summarization**
```python
async def _generate_summary(self, results: List[dict], original_query: str) -> dict:
    """Generate intelligent summary of search results"""
    
    if not results:
        return None
    
    # Prepare content for summarization
    content_snippets = []
    sources = []
    
    for result in results[:5]:  # Use top 5 results for summary
        snippet = {
            'content': result.get('content', '')[:500],  # Limit snippet length
            'source': result.get('source', ''),
            'relevance': result.get('relevance_score', 0)
        }
        content_snippets.append(snippet)
        sources.append(result.get('source', ''))
    
    # Generate summary using LLM
    summary_prompt = f"""
    Based on the following search results, provide a comprehensive answer to the question: "{original_query}"
    
    Search results:
    {self._format_results_for_summary(content_snippets)}
    
    Please provide:
    1. A clear, concise answer to the question
    2. Key points from the search results
    3. Any important caveats or limitations
    
    Answer:
    """
    
    try:
        summary_text = await self.llm_interface.chat_completion([
            {"role": "system", "content": "You are a knowledgeable research assistant. Provide accurate, well-structured answers based on the provided search results."},
            {"role": "user", "content": summary_prompt}
        ])
        
        return {
            'text': summary_text,
            'based_on_results': len(content_snippets),
            'sources': list(set(sources)),
            'confidence': self._calculate_summary_confidence(results),
            'generated_at': time.time()
        }
        
    except Exception as e:
        logger.error(f"Failed to generate summary: {e}")
        return {
            'text': f"Found {len(results)} relevant results for your query.",
            'error': 'summarization_failed',
            'sources': list(set(sources))
        }
```

## Performance Optimization

### 1. **Caching Strategy**
```python
class MultiLevelCache:
    """Implements multi-level caching for KB operations"""
    
    def __init__(self):
        # L1: In-memory cache for recent queries
        self.memory_cache = {}
        self.memory_cache_size = 100
        
        # L2: Redis cache for persistent results
        self.redis_client = get_redis_client()
        self.redis_ttl = 3600
        
        # L3: Pre-computed popular queries
        self.popular_queries_cache = {}
        
    async def get_cached_result(self, query: str) -> Optional[dict]:
        """Get cached result with multi-level lookup"""
        
        # Check L1 cache (memory)
        if query in self.memory_cache:
            return self.memory_cache[query]
        
        # Check L2 cache (Redis)
        redis_result = await self.redis_client.get(f"kb:search:{query}")
        if redis_result:
            result = json.loads(redis_result)
            # Promote to L1 cache
            self._add_to_memory_cache(query, result)
            return result
        
        # Check L3 cache (popular queries)
        if query in self.popular_queries_cache:
            result = self.popular_queries_cache[query]
            await self._cache_result(query, result)
            return result
        
        return None
```

### 2. **Search Optimization**
```python
class SearchOptimizer:
    """Optimizes knowledge base search performance"""
    
    async def optimize_query(self, query: str) -> str:
        """Optimize query for better search performance"""
        
        # Remove stop words for better matching
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words = query.lower().split()
        filtered_words = [w for w in words if w not in stop_words]
        
        # Add important terms for context
        if len(filtered_words) < len(words):
            optimized_query = ' '.join(filtered_words)
        else:
            optimized_query = query
        
        return optimized_query
    
    async def batch_search(self, queries: List[str]) -> List[dict]:
        """Perform batch search for multiple queries efficiently"""
        
        # Group similar queries for optimization
        query_groups = self._group_similar_queries(queries)
        
        results = []
        for group in query_groups:
            # Search once for the group representative
            group_result = await self.knowledge_base.search_chunks(group['representative'])
            
            # Adapt results for each query in the group
            for query in group['queries']:
                adapted_result = self._adapt_result_for_query(group_result, query)
                results.append(adapted_result)
        
        return results
```

## Error Handling & Reliability

### Error Boundary Integration
```python
from src.utils.error_boundaries import error_boundary

class KBLibrarianAgent:
    @error_boundary(component="kb_librarian", function="process_query")
    async def process_query(self, query: str, **kwargs):
        """Process query with error boundary protection"""
        # Implementation with automatic error handling
        pass
    
    @error_boundary(component="kb_librarian", function="search_knowledge_base")
    async def search_knowledge_base(self, query: str, **kwargs):
        """Search KB with error recovery"""
        try:
            return await self._perform_search(query, **kwargs)
        except Exception as e:
            # Fallback to simple text search if semantic search fails
            logger.warning(f"Semantic search failed, falling back to text search: {e}")
            return await self._perform_text_search(query, **kwargs)
```

### Graceful Degradation
```python
async def _perform_search_with_fallbacks(self, query: str) -> List[dict]:
    """Perform search with multiple fallback strategies"""
    
    strategies = [
        ('semantic_search', self._semantic_search),
        ('keyword_search', self._keyword_search),
        ('fuzzy_search', self._fuzzy_search),
        ('basic_text_search', self._basic_text_search)
    ]
    
    for strategy_name, strategy_func in strategies:
        try:
            results = await strategy_func(query)
            if results:
                logger.info(f"Search successful with {strategy_name}")
                return results
        except Exception as e:
            logger.warning(f"Search strategy {strategy_name} failed: {e}")
            continue
    
    # If all strategies fail, return empty results
    logger.error("All search strategies failed")
    return []
```

## Usage Examples

### 1. **Direct Agent Usage**
```python
from src.agents.kb_librarian_agent import get_kb_librarian_agent

# Initialize agent
kb_librarian = get_kb_librarian_agent()

# Process a question
result = await kb_librarian.process_query(
    query="What is machine learning?",
    context={
        "conversation_history": [...],
        "user_preferences": {"detail_level": "intermediate"}
    },
    user_id="user123"
)

print(f"Summary: {result['summary']['text']}")
print(f"Sources: {', '.join(result['sources'])}")
for item in result['results']:
    print(f"- {item['content'][:100]}... (Score: {item['relevance_score']:.2f})")
```

### 2. **API Usage**
```bash
# Search knowledge base
curl -X POST "http://localhost:8001/api/kb/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does AutoBot handle security?",
    "context": {"detail_level": "detailed"},
    "user_id": "user123"
  }'

# Get recent searches
curl "http://localhost:8001/api/kb/recent-searches?user_id=user123&limit=5"
```

### 3. **Integration with Other Agents**
```python
# From within another agent
async def enhanced_response_with_kb(self, user_query: str):
    """Enhance response using KB Librarian"""
    
    # Check if query contains questions that KB can answer
    kb_librarian = get_kb_librarian_agent()
    
    if kb_librarian.question_detector.is_question(user_query):
        kb_results = await kb_librarian.process_query(user_query)
        
        if kb_results['results']:
            # Incorporate KB knowledge into response
            knowledge_context = kb_results['summary']['text']
            enhanced_response = await self._generate_response_with_context(
                user_query, knowledge_context
            )
            return enhanced_response
    
    # Fall back to standard response
    return await self._generate_standard_response(user_query)
```

---

*The KB Librarian Agent demonstrates sophisticated integration with AutoBot's knowledge infrastructure, providing intelligent search and summarization capabilities that enhance the overall system's knowledge management effectiveness.*