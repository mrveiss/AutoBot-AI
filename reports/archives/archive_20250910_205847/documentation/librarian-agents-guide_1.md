# AutoBot Librarian Agents Guide

## Overview

AutoBot includes several specialized librarian agents that act as intelligent assistants for information management, research, and knowledge base operations. These agents automatically help users by searching, organizing, and providing relevant information.

## Available Librarian Agents

### 1. KB Librarian Agent (`KBLibrarianAgent`)

**Location**: `src/agents/kb_librarian_agent.py`  
**API Endpoint**: `/api/kb-librarian/`

The Knowledge Base Librarian Agent automatically searches the local knowledge base whenever users ask questions, acting like a helpful librarian that finds relevant documentation before providing answers.

#### Features:
- **Automatic Question Detection**: Identifies when user input contains questions
- **Knowledge Base Search**: Searches through indexed project documentation
- **Smart Summarization**: Uses LLM to summarize found information
- **Configurable Behavior**: Adjustable similarity thresholds and result limits

#### Configuration:
```yaml
kb_librarian:
  enabled: true
  similarity_threshold: 0.7
  max_results: 5
  auto_summarize: true
```

#### API Usage:
```bash
# Query the knowledge base
curl -X POST "http://localhost:8001/api/kb-librarian/query" \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I install AutoBot?", "auto_summarize": true}'

# Get librarian status
curl "http://localhost:8001/api/kb-librarian/status"

# Configure librarian settings
curl -X PUT "http://localhost:8001/api/kb-librarian/configure" \
  -H "Content-Type: application/json" \
  -d '{"max_results": 3, "auto_summarize": false}'
```

#### Response Format:
```json
{
  "enabled": true,
  "is_question": true,
  "query": "How do I install AutoBot?",
  "documents_found": 2,
  "documents": [
    {
      "content": "Installation instructions...",
      "metadata": {"filename": "README.md", "category": "project-overview"},
      "score": 0.85
    }
  ],
  "summary": "To install AutoBot, follow these steps..."
}
```

### 2. Containerized Librarian Assistant (`ContainerizedLibrarianAssistant`)

**Location**: `src/agents/containerized_librarian_assistant.py`

An advanced research agent that performs web research using a containerized Playwright service, finds high-quality information, and can store valuable findings in the knowledge base.

#### Features:
- **Web Research**: Uses Playwright in Docker for reliable web scraping
- **Quality Assessment**: Evaluates information quality and source credibility  
- **Source Attribution**: Properly cites sources with URLs and timestamps
- **Knowledge Storage**: Automatically stores high-quality findings for future use
- **Content Filtering**: Filters out low-quality or irrelevant content

#### Configuration:
```yaml
librarian_assistant:
  enabled: true
  playwright_service_url: "http://localhost:3000"
  max_search_results: 5
  max_content_length: 2000
  quality_threshold: 0.7
  auto_store_quality: true
  trusted_domains:
    - "github.com"
    - "docs.python.org"
    - "stackoverflow.com"
```

#### Usage Example:
```python
from src.agents import get_containerized_librarian_assistant

assistant = get_containerized_librarian_assistant()
result = await assistant.research_query(
    "latest Python web frameworks 2025",
    store_results=True
)
```

#### Key Methods:
- `research_query()`: Perform comprehensive web research
- `search_web()`: Basic web search functionality
- `assess_content_quality()`: Evaluate information quality
- `store_quality_content()`: Save valuable findings to KB

### 3. Enhanced KB Librarian (`enhanced_kb_librarian.py`)

**Location**: `src/agents/enhanced_kb_librarian.py`

An enhanced version of the basic KB Librarian with additional capabilities for knowledge management and organization.

### 4. System Knowledge Manager (`system_knowledge_manager.py`)

**Location**: `src/agents/system_knowledge_manager.py`

Manages system-wide knowledge operations, including monitoring, maintenance, and organization of the knowledge base.

## Integration Points

### Chat Integration

Librarian agents are automatically integrated into the chat system:

```python
# In backend/api/chat.py
from src.agents import get_kb_librarian, get_containerized_librarian_assistant

@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    # KB Librarian automatically searches local knowledge
    kb_librarian = get_kb_librarian()
    kb_result = await kb_librarian.process_query(request.message)
    
    # If no local results, use web research assistant
    if kb_result.get("documents_found", 0) == 0:
        web_assistant = get_containerized_librarian_assistant()
        web_result = await web_assistant.research_query(request.message)
```

### Knowledge Base Workflow

1. **User asks question** → KB Librarian searches local docs first
2. **No local results** → Containerized Librarian searches web
3. **High-quality results found** → Stored in KB for future queries
4. **Response generated** → Includes both local and web sources

## Testing

Comprehensive test coverage exists for librarian functionality:

- `autobot-vue/tests/e2e/kb-librarian-api.spec.ts`: API endpoint tests
- `autobot-vue/tests/e2e/kb-librarian-chat.spec.ts`: Chat integration tests

Run tests:
```bash
npm run test:e2e -- --grep "librarian"
```

## Troubleshooting

### KB Librarian Issues

**Problem**: "No results found" for known documentation
**Solution**: Run knowledge base sync
```bash
python scripts/sync_kb_docs.py
```

**Problem**: Summarization fails with model errors
**Solution**: Check LLM model configuration
```bash
curl "http://localhost:8001/api/system/health" | jq '.current_model'
```

### Web Research Issues

**Problem**: Containerized Librarian can't reach Playwright service
**Solution**: Check Docker service status
```bash
docker ps | grep playwright
# Start service if needed
docker run -d -p 3000:3000 playwright-service
```

**Problem**: Low-quality results stored in KB
**Solution**: Adjust quality threshold
```bash
curl -X PUT "http://localhost:8001/api/kb-librarian/configure" \
  -d '{"quality_threshold": 0.8}'
```

## Configuration Reference

### KB Librarian Settings
```yaml
kb_librarian:
  enabled: true                    # Enable/disable the agent
  similarity_threshold: 0.7        # Minimum similarity score (0.0-1.0)
  max_results: 5                   # Maximum results to return
  auto_summarize: true             # Auto-generate summaries
```

### Web Research Settings
```yaml
librarian_assistant:
  enabled: true
  playwright_service_url: "http://localhost:3000"
  max_search_results: 5            # Max web search results
  max_content_length: 2000         # Max content length per result
  quality_threshold: 0.7           # Min quality score to store
  auto_store_quality: true         # Auto-store high-quality results
  trusted_domains:                 # Domains considered high-quality
    - "github.com"
    - "docs.python.org"
    - "stackoverflow.com"
    - "readthedocs.io"
```

## Best Practices

### Knowledge Base Management
1. **Regular Sync**: Run `python scripts/sync_kb_docs.py` after documentation changes
2. **Quality Control**: Review auto-stored content periodically
3. **Source Verification**: Always verify web research sources before relying on them

### Performance Optimization
1. **Caching**: Librarian agents cache results to avoid duplicate searches
2. **Rate Limiting**: Web research includes built-in rate limiting
3. **Content Filtering**: Pre-filter queries to avoid unnecessary searches

### Security Considerations
1. **Trusted Domains**: Only auto-store content from verified sources
2. **Content Validation**: All web content is sanitized before storage
3. **Query Filtering**: Potentially harmful queries are filtered out

## Future Enhancements

### Planned Features
1. **Multi-language Support**: Support for non-English documentation
2. **Image Analysis**: OCR and image content analysis
3. **PDF Processing**: Direct PDF content extraction and indexing
4. **Real-time Updates**: Live sync with documentation changes
5. **Collaborative Features**: Multi-user knowledge base management

### Integration Opportunities
1. **External APIs**: Integration with specialized knowledge APIs
2. **Enterprise Search**: Connection to corporate search systems
3. **Version Control**: Git-integrated documentation tracking
4. **Analytics**: Usage analytics and search pattern analysis

## Migration Guide

### Upgrading from Basic to Enhanced Librarian

```python
# Old way
from src.agents.kb_librarian_agent import KBLibrarianAgent
librarian = KBLibrarianAgent()

# New way - uses containerized version by default
from src.agents import get_librarian_assistant
librarian = get_librarian_assistant()  # Returns ContainerizedLibrarianAssistant
```

### Configuration Migration

```yaml
# Old configuration
knowledge_base:
  search_enabled: true
  max_results: 5

# New configuration
kb_librarian:
  enabled: true
  max_results: 5
  similarity_threshold: 0.7
  auto_summarize: true
```

---

**Note**: Librarian agents are essential components of AutoBot's intelligent assistance system. They work together to provide comprehensive information support, combining local knowledge with web research capabilities to deliver accurate, well-sourced responses to user queries.