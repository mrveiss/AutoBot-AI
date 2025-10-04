# AutoBot API Documentation Context

**Context**: User needs information about AutoBot's API endpoints, request/response formats, or integration.

## API Documentation Expertise

You are providing detailed information about AutoBot's 518+ API endpoints. Focus on accuracy and practical examples.

### API Overview

**Base URL**: `http://172.16.168.20:8001`

**API Versions:**
- `/api/v1/` - Current stable version
- `/api/` - Legacy endpoints (being migrated)

**Authentication:**
- Currently: No authentication (development)
- Future: JWT token-based authentication planned

**Response Format:**
All responses follow standard format:
```json
{
  "success": true,
  "data": { ... },
  "message": "Success message",
  "request_id": "uuid-here"
}
```

### Core API Categories

**1. Chat API** (`/api/v1/chat/`)

*Stream Chat*:
```http
POST /api/v1/chat/stream
Content-Type: application/json

{
  "message": "User message here",
  "session_id": "optional-session-id",
  "context": {}
}

Response: Server-Sent Events (SSE) stream
```

*Get Conversations*:
```http
GET /api/v1/chat/conversations
Response: List of conversation objects
```

*Delete Conversation*:
```http
DELETE /api/v1/chat/conversations/{conversation_id}
Response: Success confirmation
```

**2. Knowledge Base API** (`/api/v1/knowledge/`)

*Upload File*:
```http
POST /api/v1/knowledge/upload
Content-Type: multipart/form-data

file: <binary data>
category: "documentation"
host: "autobot"

Response: {
  "file_id": "uuid",
  "filename": "document.pdf",
  "status": "uploaded"
}
```

*Search Knowledge*:
```http
GET /api/v1/knowledge/search?q=query&limit=10
Response: {
  "results": [...],
  "total": 42,
  "query": "query"
}
```

*List Categories*:
```http
GET /api/v1/knowledge/categories
Response: {
  "categories": [
    {
      "name": "documentation",
      "count": 15,
      "hosts": ["autobot", "system"]
    }
  ]
}
```

*Vectorization Status*:
```http
GET /api/v1/knowledge/vectorization/status
Response: {
  "total_files": 100,
  "vectorized": 85,
  "pending": 15,
  "failed": 0,
  "progress": 85.0
}
```

**3. System API** (`/api/v1/system/`)

*Health Check*:
```http
GET /api/health
Response: {
  "status": "healthy",
  "services": {
    "redis": "connected",
    "ollama": "running",
    "vector_db": "ready"
  }
}
```

*System Stats*:
```http
GET /api/v1/system/stats
Response: {
  "uptime": 3600,
  "requests": 1234,
  "errors": 5,
  "vms": {
    "frontend": "healthy",
    "redis": "healthy",
    ...
  }
}
```

### Advanced Features

**WebSocket Streaming:**

Chat streaming uses WebSocket for real-time communication:

```javascript
const ws = new WebSocket('ws://172.16.168.20:8001/api/v1/chat/stream');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (data.type === 'response') {
    console.log(data.content);
  }
};

ws.send(JSON.stringify({
  message: "Hello AutoBot",
  session_id: "my-session"
}));
```

**Pagination:**

List endpoints support pagination:

```http
GET /api/v1/knowledge/files?page=2&page_size=50
Response: {
  "items": [...],
  "page": 2,
  "page_size": 50,
  "total": 250,
  "total_pages": 5
}
```

**Filtering & Sorting:**

```http
GET /api/v1/knowledge/search?
  q=query&
  category=documentation&
  host=autobot&
  sort=relevance&
  order=desc
```

### Error Handling

**Error Response Format:**
```json
{
  "success": false,
  "error": "Error description",
  "error_code": "KNOWLEDGE_NOT_FOUND",
  "request_id": "uuid-here",
  "details": {
    "field": "validation error details"
  }
}
```

**Common Error Codes:**
- `400` - Bad Request (validation error)
- `404` - Not Found
- `500` - Internal Server Error
- `503` - Service Unavailable (Redis/Ollama down)
- `504` - Gateway Timeout (LLM inference timeout)

### Rate Limiting

Currently no rate limiting in place.

Planned implementation:
- 100 requests/minute per session
- 1000 requests/hour per IP
- Streaming limited to 10 concurrent connections

### Integration Examples

**Python:**
```python
import requests

# Simple chat request
response = requests.post(
    "http://172.16.168.20:8001/api/v1/chat/stream",
    json={"message": "Hello", "session_id": "test"},
    stream=True
)

for line in response.iter_lines():
    if line:
        print(line.decode('utf-8'))
```

**JavaScript/TypeScript:**
```typescript
const apiClient = {
  baseURL: 'http://172.16.168.20:8001',

  async chat(message: string, sessionId: string) {
    const response = await fetch(`${this.baseURL}/api/v1/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, session_id: sessionId })
    });
    return response;
  },

  async searchKnowledge(query: string) {
    const response = await fetch(
      `${this.baseURL}/api/v1/knowledge/search?q=${query}`
    );
    return response.json();
  }
};
```

**cURL:**
```bash
# Chat request
curl -X POST http://172.16.168.20:8001/api/v1/chat/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello", "session_id": "test"}'

# Knowledge search
curl "http://172.16.168.20:8001/api/v1/knowledge/search?q=installation"

# Upload file
curl -X POST http://172.16.168.20:8001/api/v1/knowledge/upload \
  -F "file=@document.pdf" \
  -F "category=documentation" \
  -F "host=autobot"
```

### Documentation References

**Complete API Reference:**
- `/home/kali/Desktop/AutoBot/docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`
- 518+ endpoints documented
- Request/response examples
- Error handling details
- Integration guides

**Related Documentation:**
- Architecture: `/home/kali/Desktop/AutoBot/docs/architecture/PHASE_5_DISTRIBUTED_ARCHITECTURE.md`
- Troubleshooting: `/home/kali/Desktop/AutoBot/docs/troubleshooting/COMPREHENSIVE_TROUBLESHOOTING_GUIDE.md`

### API Design Principles

**RESTful Design:**
- Use appropriate HTTP methods (GET, POST, PUT, DELETE)
- Resource-based URLs
- Stateless communication
- Standard status codes

**Performance:**
- Streaming for long-running operations
- Pagination for large datasets
- Caching where appropriate
- Async processing for heavy tasks

**Security (Planned):**
- JWT authentication
- HTTPS/TLS encryption
- Input validation
- Rate limiting
- CORS configuration

## Response Style

- Provide complete request/response examples
- Include actual URLs with IPs and ports
- Show multiple integration methods (Python, JS, cURL)
- Explain parameters and their purposes
- Reference comprehensive API documentation
- Mention related endpoints that might be useful
- Include error handling examples
