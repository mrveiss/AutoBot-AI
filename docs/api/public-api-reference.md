# AutoBot Public REST API Reference

> **Version:** v1 (planned)
> **Base URL:** `https://<autobot-host>:8443/api/v1`
> **Current internal base:** `https://<autobot-host>:8443/api`

This document defines the public REST API surface for external developers.
All endpoints listed here are candidates for the stable `/api/v1/` namespace.
Internal, admin-only, and MCP bridge endpoints are excluded.

---

## Table of Contents

- [Authentication](#authentication)
- [Rate Limiting](#rate-limiting)
- [Error Format](#error-format)
- [Chat](#chat)
- [Knowledge Base](#knowledge-base)
- [Agents](#agents)
- [Workflows](#workflows)
- [Models and LLM](#models-and-llm)
- [Voice](#voice)
- [Multimodal](#multimodal)
- [System](#system)

---

## Authentication

All API requests require a valid API key or JWT token.

### API Key Authentication

Pass the API key in the `Authorization` header:

```
Authorization: Bearer <api-key>
```

### JWT Token Authentication

Obtain a JWT token via the login endpoint, then pass it in subsequent requests:

```
Authorization: Bearer <jwt-token>
```

### POST /auth/login

Authenticate and receive a JWT token.

**Request:**

```json
{
  "username": "string",
  "password": "string"
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "Login successful",
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "session_id": "sess_abc123",
  "user": {
    "username": "string",
    "user_id": "string",
    "role": "string",
    "email": "string",
    "last_login": "2026-03-15T12:00:00Z"
  }
}
```

### POST /auth/logout

Invalidate the current session.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

### GET /auth/me

Get current user information.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "username": "string",
  "role": "string",
  "permissions": ["string"]
}
```

### POST /auth/refresh

Refresh an expiring JWT token.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "token": "eyJhbGciOiJIUzI1NiIs...",
  "expiresIn": 3600
}
```

---

## Rate Limiting

All API endpoints enforce rate limiting. Limits are communicated via response headers:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests per window |
| `X-RateLimit-Remaining` | Requests remaining in current window |
| `X-RateLimit-Reset` | Unix timestamp when the window resets |
| `Retry-After` | Seconds to wait (only on 429 responses) |

**Default limits (planned for v1):**

| Tier | Requests/minute | Burst |
|------|-----------------|-------|
| Free | 60 | 10 |
| Standard | 300 | 50 |
| Enterprise | 1000 | 200 |

When rate-limited, the API returns HTTP 429:

```json
{
  "error": "rate_limit_exceeded",
  "message": "Too many requests. Retry after 12 seconds.",
  "retry_after": 12
}
```

---

## Error Format

All error responses follow a consistent format:

```json
{
  "success": false,
  "error": "error_code",
  "message": "Human-readable description",
  "details": {}
}
```

**Standard HTTP Status Codes:**

| Code | Meaning |
|------|---------|
| 200 | Success |
| 201 | Created |
| 400 | Bad Request -- malformed input |
| 401 | Unauthorized -- missing or invalid credentials |
| 403 | Forbidden -- insufficient permissions |
| 404 | Not Found |
| 409 | Conflict -- resource already exists |
| 422 | Validation Error -- input failed validation |
| 429 | Rate Limited |
| 500 | Internal Server Error |

---

## Chat

Chat endpoints manage conversational sessions and message exchange with AI models.

**Internal prefix:** `/api` (chat router registered with empty prefix)

### POST /chat

Send a message and receive a response.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "content": "How do I configure network scanning?",
  "role": "user",
  "session_id": "optional-session-id",
  "model": "optional-model-name",
  "use_knowledge_base": true,
  "context_window": 10
}
```

**Response (200):**

```json
{
  "success": true,
  "response": "To configure network scanning, you can...",
  "session_id": "chat_abc123",
  "message_id": "msg_xyz789",
  "metadata": {
    "model": "gpt-4-turbo",
    "tokens_used": 245,
    "knowledge_base_used": true
  }
}
```

### POST /chat/stream

Send a message and receive a streaming response (Server-Sent Events).

**Headers:** `Authorization: Bearer <token>`, `Accept: text/event-stream`

**Request:** Same as `POST /chat`.

**Response:** SSE stream with events:

```
data: {"type": "token", "content": "To "}
data: {"type": "token", "content": "configure "}
data: {"type": "token", "content": "network..."}
data: {"type": "done", "message_id": "msg_xyz789", "metadata": {...}}
```

### GET /chats

List chat sessions for the authenticated user.

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Maximum sessions to return |
| `offset` | int | 0 | Pagination offset |

**Response (200):**

```json
{
  "success": true,
  "sessions": [
    {
      "session_id": "chat_abc123",
      "title": "Network scanning discussion",
      "created_at": "2026-03-15T10:30:00Z",
      "updated_at": "2026-03-15T11:00:00Z",
      "message_count": 12
    }
  ],
  "total": 42
}
```

### POST /chat/sessions

Create a new chat session.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "title": "New conversation",
  "model": "gpt-4-turbo"
}
```

**Response (201):**

```json
{
  "success": true,
  "session_id": "chat_abc123",
  "title": "New conversation",
  "created_at": "2026-03-15T10:30:00Z"
}
```

### GET /chat/sessions/{session_id}

Get a specific chat session with its message history.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "session": {
    "session_id": "chat_abc123",
    "title": "Network scanning discussion",
    "messages": [
      {
        "message_id": "msg_001",
        "role": "user",
        "content": "How do I scan a network?",
        "timestamp": "2026-03-15T10:30:00Z"
      },
      {
        "message_id": "msg_002",
        "role": "assistant",
        "content": "You can use nmap to scan...",
        "timestamp": "2026-03-15T10:30:05Z"
      }
    ]
  }
}
```

### POST /chats/{chat_id}/message

Send a message to an existing chat session.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "content": "Tell me more about nmap flags",
  "role": "user"
}
```

**Response (200):** Same format as `POST /chat`.

### DELETE /chats/{chat_id}

Delete a chat session.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "message": "Chat session deleted"
}
```

### GET /chat/sessions/{session_id}/export

Export a chat session.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "export": {
    "session_id": "chat_abc123",
    "format": "json",
    "messages": [...],
    "exported_at": "2026-03-15T12:00:00Z"
  }
}
```

---

## Knowledge Base

Endpoints for managing documents, facts, and collections in the knowledge base.

**Internal prefix:** `/api/knowledge_base`

### POST /knowledge_base/facts

Add text content to the knowledge base.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "content": "AutoBot supports NPU acceleration for inference workloads.",
  "title": "NPU Acceleration",
  "source": "Technical Documentation",
  "category": "general",
  "tags": ["npu", "acceleration", "hardware"]
}
```

**Response (201):**

```json
{
  "success": true,
  "fact_id": "fact_abc123",
  "message": "Content added to knowledge base"
}
```

### POST /knowledge_base/upload

Upload a document file to the knowledge base.

**Headers:** `Authorization: Bearer <token>`, `Content-Type: multipart/form-data`

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | yes | Document file (PDF, TXT, MD, DOCX) |
| `category` | string | no | Category for the document |
| `tags` | string | no | Comma-separated tags |

**Response (200):**

```json
{
  "success": true,
  "document_id": "doc_abc123",
  "filename": "architecture.pdf",
  "chunks_created": 15,
  "message": "Document uploaded and indexed"
}
```

### POST /knowledge_base/url

Add content from a URL.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "url": "https://example.com/article",
  "title": "External Article",
  "method": "fetch",
  "category": "web",
  "tags": ["external", "reference"]
}
```

**Response (200):**

```json
{
  "success": true,
  "message": "URL content added to knowledge base"
}
```

### POST /knowledge_base/query

Query the knowledge base using natural language.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "query": "How does NPU acceleration work?",
  "top_k": 5,
  "category": "general",
  "min_confidence": 0.7
}
```

**Response (200):**

```json
{
  "success": true,
  "results": [
    {
      "content": "AutoBot supports NPU acceleration...",
      "score": 0.95,
      "source": "Technical Documentation",
      "category": "general",
      "metadata": {}
    }
  ],
  "query_time_ms": 45
}
```

### POST /knowledge_base/search

Search the knowledge base with advanced options.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "query": "network security tools",
  "search_type": "hybrid",
  "top_k": 10,
  "filters": {
    "categories": ["security", "tools"],
    "tags": ["network"]
  }
}
```

**Response (200):**

```json
{
  "success": true,
  "results": [...],
  "total": 42,
  "search_type": "hybrid",
  "query_time_ms": 78
}
```

### GET /knowledge_base/entries

List knowledge base entries.

**Headers:** `Authorization: Bearer <token>`

**Query Parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Maximum entries to return |
| `offset` | int | 0 | Pagination offset |
| `category` | string | - | Filter by category |

**Response (200):**

```json
{
  "success": true,
  "entries": [...],
  "total": 150
}
```

### GET /knowledge_base/stats

Get knowledge base statistics.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "stats": {
    "total_facts": 1500,
    "total_documents": 85,
    "categories": {"general": 500, "security": 300, "tools": 200},
    "storage_size_mb": 42.5
  }
}
```

### GET /knowledge_base/categories

List available categories.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "categories": [
    {"name": "general", "count": 500},
    {"name": "security", "count": 300}
  ]
}
```

### Collections

Collections group related facts for organized access.

#### POST /knowledge_base/collections

Create a new collection.

**Request:**

```json
{
  "name": "Security Playbooks",
  "description": "Collection of security automation playbooks"
}
```

#### GET /knowledge_base/collections

List all collections.

#### GET /knowledge_base/collections/{collection_id}

Get a specific collection with its facts.

#### PUT /knowledge_base/collections/{collection_id}

Update a collection.

#### DELETE /knowledge_base/collections/{collection_id}

Delete a collection.

#### POST /knowledge_base/collections/{collection_id}/facts

Add facts to a collection.

#### GET /knowledge_base/collections/{collection_id}/facts

List facts in a collection.

---

## Agents

Endpoints for managing and invoking AI agents.

**Internal prefix:** `/api/agent`

### GET /agent/agents/available

List all available agents and their capabilities.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "agents": [
    {
      "name": "rag",
      "description": "Retrieval-Augmented Generation for document synthesis",
      "capabilities": ["document_query", "reformulate_query", "analyze_documents"]
    },
    {
      "name": "chat",
      "description": "Conversational interactions with context awareness",
      "capabilities": ["natural_conversation", "context_retention"]
    },
    {
      "name": "research",
      "description": "Comprehensive research and analysis",
      "capabilities": ["research_queries", "source_analysis", "report_generation"]
    },
    {
      "name": "web_research_assistant",
      "description": "Web-based research and content analysis",
      "capabilities": ["web_search", "content_extraction", "source_validation"]
    },
    {
      "name": "knowledge_extraction",
      "description": "Structured knowledge extraction from content",
      "capabilities": ["entity_extraction", "relationship_mapping"]
    }
  ]
}
```

### GET /agent/agents/status

Get the status of all active agents.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "agents": {
    "rag": {"status": "idle", "last_active": "2026-03-15T10:30:00Z"},
    "research": {"status": "busy", "current_task": "task_abc123"}
  }
}
```

### POST /agent/goal

Execute an agent goal.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "goal": "Research the latest network security vulnerabilities",
  "agent": "research",
  "parameters": {
    "depth": "comprehensive",
    "sources": ["web", "knowledge_base"]
  }
}
```

**Response (200):**

```json
{
  "success": true,
  "task_id": "task_abc123",
  "status": "running",
  "agent": "research",
  "message": "Goal execution started"
}
```

### POST /agent/goal/enhanced

Execute an enhanced agent goal with AI Stack integration.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "goal": "Analyze codebase for security vulnerabilities",
  "agent": "research",
  "use_ai_stack": true,
  "parameters": {}
}
```

### POST /agent/multi-agent/coordinate

Coordinate multiple agents on a complex task.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "task": "Research and document network scanning tools",
  "agents": ["research", "rag", "knowledge_extraction"],
  "coordination_mode": "sequential"
}
```

**Response (200):**

```json
{
  "success": true,
  "coordination_id": "coord_abc123",
  "status": "running",
  "agents_involved": ["research", "rag", "knowledge_extraction"]
}
```

### POST /agent/research/comprehensive

Run a comprehensive research task.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "query": "Latest developments in NPU-accelerated AI inference",
  "depth": "comprehensive"
}
```

### POST /agent/pause

Pause a running agent task.

**Request:**

```json
{
  "task_id": "task_abc123"
}
```

### POST /agent/resume

Resume a paused agent task.

**Request:**

```json
{
  "task_id": "task_abc123"
}
```

---

## Workflows

Endpoints for multi-agent workflow orchestration.

**Internal prefix:** `/api/workflow`

### POST /workflow/execute

Trigger a new workflow execution.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "workflow_type": "research_and_document",
  "parameters": {
    "topic": "Network security scanning",
    "output_format": "report"
  }
}
```

**Response (200):**

```json
{
  "success": true,
  "workflow_id": "wf_abc123",
  "status": "running",
  "steps": [
    {"step": 1, "agent": "research", "action": "Research tools", "status": "pending"},
    {"step": 2, "agent": "librarian", "action": "Search Knowledge Base", "status": "pending"},
    {"step": 3, "agent": "orchestrator", "action": "Compile report", "status": "pending"}
  ]
}
```

### GET /workflow/workflows

List all workflows.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "workflows": [
    {
      "workflow_id": "wf_abc123",
      "type": "research_and_document",
      "status": "completed",
      "created_at": "2026-03-15T10:00:00Z",
      "completed_at": "2026-03-15T10:05:00Z"
    }
  ]
}
```

### GET /workflow/workflow/{workflow_id}

Get details of a specific workflow.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "workflow": {
    "workflow_id": "wf_abc123",
    "type": "research_and_document",
    "status": "running",
    "progress": 0.66,
    "steps": [
      {"step": 1, "agent": "research", "status": "completed", "result": "..."},
      {"step": 2, "agent": "librarian", "status": "running"},
      {"step": 3, "agent": "orchestrator", "status": "pending"}
    ]
  }
}
```

### GET /workflow/workflow/{workflow_id}/status

Get the current status of a workflow.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "workflow_id": "wf_abc123",
  "status": "running",
  "progress": 0.66,
  "current_step": 2,
  "total_steps": 3
}
```

### POST /workflow/workflow/{workflow_id}/approve

Approve a pending workflow step (for workflows requiring human approval).

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "step_id": 2,
  "approved": true,
  "comment": "Approved for execution"
}
```

### GET /workflow/workflow/{workflow_id}/pending_approvals

List pending approval requests for a workflow.

### DELETE /workflow/workflow/{workflow_id}

Cancel and delete a workflow.

---

## Models and LLM

Endpoints for managing LLM providers and model configuration.

**Internal prefix:** `/api/llm`

### GET /llm/models

List available language models.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "models": [
    {
      "name": "gpt-4-turbo",
      "provider": "openai",
      "type": "chat",
      "context_window": 128000,
      "available": true
    },
    {
      "name": "claude-3-opus",
      "provider": "anthropic",
      "type": "chat",
      "context_window": 200000,
      "available": true
    }
  ]
}
```

### GET /llm/current

Get the currently active model configuration.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "model": "gpt-4-turbo",
  "provider": "openai",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

### GET /llm/config

Get LLM configuration.

**Headers:** `Authorization: Bearer <token>`

### POST /llm/config

Update LLM configuration.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "model": "claude-3-opus",
  "provider": "anthropic",
  "temperature": 0.7,
  "max_tokens": 4096
}
```

### GET /llm/status

Get LLM provider connection status.

**Headers:** `Authorization: Bearer <token>`

**Response (200):**

```json
{
  "success": true,
  "providers": {
    "openai": {"status": "connected", "latency_ms": 120},
    "anthropic": {"status": "connected", "latency_ms": 95}
  }
}
```

### GET /llm/health/providers

Get health status of all configured LLM providers.

### GET /llm/embedding/models

List available embedding models.

---

## Voice

Endpoints for voice processing (text-to-speech and speech-to-text).

**Internal prefix:** `/api/voice`

### POST /voice/transcribe

Transcribe audio to text.

**Headers:** `Authorization: Bearer <token>`, `Content-Type: multipart/form-data`

**Form Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `audio` | file | yes | Audio file (WAV, MP3, OGG) |
| `language` | string | no | Language code (e.g., "en") |

### POST /voice/synthesize

Convert text to speech audio.

**Headers:** `Authorization: Bearer <token>`

**Request:**

```json
{
  "text": "Hello, this is AutoBot speaking.",
  "voice": "default",
  "format": "wav"
}
```

---

## Multimodal

Endpoints for multi-modal AI processing (text, image, audio).

**Internal prefix:** `/api/multimodal`

### POST /multimodal/process/image

Process an image with AI analysis.

**Headers:** `Authorization: Bearer <token>`

**Request:** `multipart/form-data` with image file, or JSON with base64-encoded image.

### POST /multimodal/process/audio

Process audio with AI analysis.

### POST /multimodal/process/text

Process text with multi-modal context.

### POST /multimodal/search/cross-modal

Search across modalities (text, image, audio).

### GET /multimodal/stats

Get multi-modal processing statistics.

### GET /multimodal/health

Health check for multi-modal subsystem.

---

## System

System-level endpoints for health checking and diagnostics.

**Internal prefix:** `/api/system`

### GET /system/health

Health check endpoint.

**Response (200):**

```json
{
  "status": "healthy",
  "version": "2.x.x",
  "uptime_seconds": 86400,
  "components": {
    "database": "healthy",
    "redis": "healthy",
    "llm": "healthy",
    "knowledge_base": "healthy"
  }
}
```

### GET /system/info

Get system information.

**Headers:** `Authorization: Bearer <token>`

---

## Pagination

Endpoints returning lists support pagination via query parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `limit` | int | 50 | Items per page (max 100) |
| `offset` | int | 0 | Number of items to skip |

Response includes total count for client-side pagination:

```json
{
  "success": true,
  "data": [...],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

---

## WebSocket Endpoints

AutoBot also provides WebSocket endpoints for real-time communication:

- **`/api/ws/chat`** -- Real-time chat with streaming responses
- **`/api/ws/voice`** -- Real-time voice streaming
- **`/api/ws/terminal`** -- Terminal session streaming

WebSocket connections require the JWT token as a query parameter:

```
wss://<autobot-host>:8443/api/ws/chat?token=<jwt-token>
```

---

## Notes for SDK Implementers

1. **Content-Type:** Always send `Content-Type: application/json` for JSON payloads
2. **File uploads:** Use `Content-Type: multipart/form-data` for file upload endpoints
3. **Streaming:** Use SSE (Server-Sent Events) for streaming endpoints -- the `Accept: text/event-stream` header is recommended
4. **Idempotency:** POST requests that create resources should include a client-generated `request_id` for idempotency
5. **Timeouts:** Recommended client timeout of 30 seconds for standard requests, 120 seconds for streaming and workflow endpoints
