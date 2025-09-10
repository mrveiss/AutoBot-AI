# NPU Code Search Agent

## Overview

The NPU Code Search Agent provides high-performance semantic code search capabilities using NPU (Neural Processing Unit) acceleration when available, with Redis-based indexing for fast code element lookup and pattern matching.

## System Integration & Interactions

### Architecture Position
```
User Query → Agent Orchestrator → NPU Code Search Agent
                                        ↓
┌─────────────────────────────────────────────────────────────┐
│                NPU Code Search Agent                        │
├─────────────────────────────────────────────────────────────┤
│ • Semantic code similarity search                          │
│ • Pattern matching and code analysis                       │
│ • Multi-language support                                   │
│ • Context extraction and ranking                           │
└─────────────────┬───────────────────────────────────────────┘
                  │
         ┌────────┼────────┐
         ▼        ▼        ▼
    ┌────────┐ ┌─────┐ ┌─────────┐
    │  NPU   │ │Redis│ │File     │
    │Hardware│ │Cache│ │System   │
    └────────┘ └─────┘ └─────────┘
```

### System Component Interactions

#### 1. **NPU Hardware Integration**
```python
# NPU Detection and Initialization
def _init_npu(self):
    """Initialize NPU acceleration if available"""
    try:
        # Check worker capabilities for NPU
        capabilities = self.worker_node.detect_capabilities()
        self.npu_available = capabilities.get("openvino_npu_available", False)
        
        if self.npu_available:
            from openvino.runtime import Core
            self.openvino_core = Core()
            npu_devices = capabilities.get("openvino_npu_devices", [])
```

**System Interactions:**
- **Worker Node**: Queries hardware capabilities for NPU availability
- **OpenVINO Runtime**: Initializes NPU cores for acceleration
- **Hardware Detection**: Automatically detects and configures available NPU devices

#### 2. **Redis Integration**
```python
# Redis-based indexing and caching
class NPUCodeSearchAgent:
    def __init__(self):
        self.redis_client = get_redis_client(async_client=False)
        self.redis_async_client = get_redis_client(async_client=True)
        
        # Index and cache prefixes
        self.index_prefix = "autobot:code:index:"
        self.search_cache_prefix = "autobot:search:cache:"
        self.cache_ttl = 3600  # 1 hour cache
```

**System Interactions:**
- **Redis Client**: Uses centralized Redis connection for caching and indexing
- **Index Storage**: Stores code element indices with semantic embeddings
- **Cache Management**: Implements TTL-based cache expiration for search results
- **Async Operations**: Uses async Redis client for non-blocking operations

#### 3. **File System Integration**
```python
async def index_codebase(self, codebase_path: str, 
                        language_filter: Optional[str] = None) -> Dict[str, Any]:
    """Index an entire codebase for fast searching"""
    # Recursive file discovery
    code_files = []
    for root, dirs, files in os.walk(codebase_path):
        for file in files:
            if any(file.endswith(ext) for ext in self.supported_extensions):
                code_files.append(os.path.join(root, file))
```

**System Interactions:**
- **File System**: Recursively scans directories for code files
- **Security Layer**: Respects file permissions and access controls
- **Path Validation**: Validates file paths for security (prevents directory traversal)
- **File Type Detection**: Uses file extensions and MIME types for language detection

#### 4. **Agent Orchestrator Integration**
```python
# Registration with orchestrator
async def register_with_orchestrator(self):
    """Register capabilities with the agent orchestrator"""
    capabilities = {
        "agent_type": "npu_code_search",
        "supported_operations": [
            "semantic_search", "pattern_matching", "code_analysis", 
            "similarity_search", "context_extraction"
        ],
        "supported_languages": list(self.language_mappings.keys()),
        "performance_tier": "high" if self.npu_available else "medium",
        "hardware_acceleration": self.npu_available
    }
    
    # Register with orchestrator
    from src.agents.agent_orchestrator import get_agent_orchestrator
    orchestrator = get_agent_orchestrator()
    await orchestrator.register_agent("npu_code_search", self, capabilities)
```

**System Interactions:**
- **Agent Registration**: Registers capabilities and supported operations
- **Load Balancing**: Orchestrator routes code search requests based on availability
- **Performance Metrics**: Reports hardware acceleration status for routing decisions

## Core Functionality

### Primary Functions

#### 1. **Semantic Code Search**
```python
async def search_code(self, query: str, search_type: str = "semantic", 
                     language: Optional[str] = None, 
                     limit: int = 10) -> List[CodeSearchResult]:
    """
    Perform semantic code search with NPU acceleration
    
    Args:
        query: Search query (natural language or code patterns)
        search_type: "semantic", "exact", "pattern", "similarity"
        language: Target programming language filter
        limit: Maximum number of results
        
    Returns:
        List of CodeSearchResult objects with confidence scores
    """
```

**System Interactions:**
- **Semantic Processing**: Uses NPU for embedding generation and similarity calculations
- **Language Processing**: Applies language-specific parsers and filters
- **Ranking Algorithm**: Combines semantic similarity with code structure analysis
- **Result Caching**: Stores search results in Redis for repeated queries

#### 2. **Code Indexing**
```python
async def index_codebase(self, codebase_path: str) -> Dict[str, Any]:
    """Index entire codebase for fast searching"""
    indexing_stats = {
        "files_indexed": 0,
        "functions_indexed": 0,
        "classes_indexed": 0,
        "total_size_mb": 0,
        "indexing_time_ms": 0
    }
```

**System Interactions:**
- **File Processing**: Parses code files using language-specific parsers
- **Embedding Generation**: Creates semantic embeddings for code elements
- **Index Storage**: Stores structured indices in Redis with hierarchical keys
- **Progress Tracking**: Reports indexing progress through event system

### API Endpoints Integration

The agent integrates with AutoBot's API system through dedicated endpoints:

#### `/api/code_search/search`
```python
@router.post("/search")
async def search_code_endpoint(request: CodeSearchRequest):
    """API endpoint for code search operations"""
    npu_agent = get_npu_code_search_agent()
    results = await npu_agent.search_code(
        query=request.query,
        search_type=request.search_type,
        language=request.language,
        limit=request.limit
    )
    return CodeSearchResponse(results=results)
```

#### `/api/code_search/index`
```python
@router.post("/index")
async def index_codebase_endpoint(request: IndexRequest):
    """API endpoint for codebase indexing"""
    npu_agent = get_npu_code_search_agent()
    stats = await npu_agent.index_codebase(request.path)
    return IndexResponse(stats=stats)
```

## Performance & Monitoring

### Hardware Acceleration
- **NPU Detection**: Automatically detects Intel NPU devices via OpenVINO
- **Fallback Strategy**: Uses CPU-based processing when NPU unavailable
- **Performance Metrics**: Tracks search times and hardware utilization

### Caching Strategy
- **L1 Cache**: In-memory search result cache (recently used queries)
- **L2 Cache**: Redis-based persistent cache (1-hour TTL)
- **L3 Cache**: Persistent code indices (updated on file changes)

### Monitoring Integration
```python
# Performance tracking
class SearchStats:
    total_files_indexed: int
    search_time_ms: float
    npu_acceleration_used: bool
    redis_cache_hit: bool
    results_count: int
```

**System Interactions:**
- **Metrics Collection**: Integrates with system-wide metrics collection
- **Performance Logging**: Logs search performance for optimization
- **Health Monitoring**: Reports agent health status to monitoring system

## Usage Examples

### 1. **Direct Agent Usage**
```python
from src.agents.npu_code_search_agent import get_npu_code_search_agent

# Initialize agent
npu_agent = get_npu_code_search_agent()

# Index a codebase
await npu_agent.index_codebase("/path/to/project")

# Search for functions
results = await npu_agent.search_code(
    query="calculate total price with tax",
    search_type="semantic",
    language="python"
)

for result in results:
    print(f"File: {result.file_path}")
    print(f"Function: {result.content}")
    print(f"Confidence: {result.confidence}")
```

### 2. **API Integration**
```bash
# Index codebase
curl -X POST http://localhost:8001/api/code_search/index \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/project"}'

# Search code
curl -X POST http://localhost:8001/api/code_search/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "function that validates user input",
    "search_type": "semantic",
    "language": "javascript",
    "limit": 5
  }'
```

### 3. **Orchestrator Integration**
```python
# Via agent orchestrator
from src.agents.agent_orchestrator import get_agent_orchestrator

orchestrator = get_agent_orchestrator()

# Route code search request
response = await orchestrator.process_request({
    "type": "code_search",
    "query": "authentication middleware",
    "context": {"project_path": "/app/src"}
})
```

## Error Handling & Recovery

### Error Boundary Integration
```python
from src.utils.error_boundaries import error_boundary

@error_boundary(component="npu_code_search", function="search_code")
async def search_code(self, query: str, **kwargs):
    # Search implementation with automatic error handling
    pass
```

### Fallback Strategies
1. **NPU Unavailable**: Falls back to CPU-based semantic search
2. **Redis Unavailable**: Uses in-memory caching only
3. **Index Corruption**: Rebuilds index from source files
4. **Search Timeout**: Returns partial results with timeout flag

## Configuration

### Environment Variables
```bash
# NPU Configuration
AUTOBOT_NPU_ENABLED=true
AUTOBOT_NPU_DEVICE_PREFERENCE=AUTO

# Redis Configuration  
AUTOBOT_REDIS_CODE_INDEX_TTL=3600
AUTOBOT_REDIS_SEARCH_CACHE_SIZE=1000

# Performance Tuning
AUTOBOT_CODE_SEARCH_MAX_FILE_SIZE=10485760  # 10MB
AUTOBOT_CODE_SEARCH_INDEX_BATCH_SIZE=100
```

### Agent-Specific Settings
```yaml
# config/agents/npu_code_search.yaml
npu_code_search:
  enabled: true
  hardware_acceleration: auto
  supported_languages:
    - python
    - javascript
    - typescript
    - java
    - cpp
    - go
    - rust
  indexing:
    batch_size: 100
    max_file_size: 10485760
  caching:
    result_ttl: 3600
    max_cache_entries: 1000
```

## Security Considerations

### File Access Control
- **Sandboxed Operations**: Only accesses files within allowed directories
- **Permission Validation**: Checks file permissions before indexing
- **Path Traversal Protection**: Validates all file paths for security

### Data Privacy
- **Code Privacy**: Semantic embeddings don't expose source code directly
- **Cache Isolation**: Search results cached per user/session context
- **Audit Logging**: All code access operations are logged for security

## Dependencies

### Required Components
- **OpenVINO Runtime**: For NPU hardware acceleration
- **Redis**: For caching and index storage  
- **Worker Node**: For hardware capability detection
- **Security Layer**: For access control and audit logging

### Optional Dependencies
- **NPU Drivers**: Intel NPU drivers for hardware acceleration
- **Language Parsers**: Tree-sitter parsers for advanced code analysis
- **Similarity Models**: Pre-trained embeddings for semantic search

---

*This agent demonstrates the deep integration between specialized AI capabilities and AutoBot's system infrastructure, showcasing how agents interact with hardware, caching, security, and orchestration systems.*