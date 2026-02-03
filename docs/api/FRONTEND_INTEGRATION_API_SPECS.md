# AutoBot Frontend Integration API Specifications

## Overview
This document provides complete API specifications for frontend integration with the AutoBot backend system. The backend runs on `http://172.16.168.20:8001/` and provides 285+ documented endpoints across multiple service modules.

## Base Configuration

### Backend API Base URL
```
http://172.16.168.20:8001/
```

### OpenAPI Documentation
- **Swagger UI**: `http://172.16.168.20:8001/docs`  
- **OpenAPI JSON**: `http://172.16.168.20:8001/openapi.json`

## Core API Endpoints

## 1. Chat System APIs

### 1.1 Async Chat API (`/api/async_chat/`)

#### Create New Chat
```http
POST /api/async_chat/chats/new
```

**Response:**
```json
{
  "chat_id": "81a7fd5d-a5e0-4055-bf42-561d33860c59",
  "created": true,
  "timestamp": "2025-09-01T13:45:00.000Z"
}
```

#### Send Chat Message
```http
POST /api/async_chat/chats/{chat_id}/message
Content-Type: application/json

{
  "message": "Your message here (1-10000 characters)",
  "options": {}
}
```

**Response Schema:**
```typescript
interface ChatResponse {
  response: string;
  message_type: string;
  knowledge_status: string;
  processing_time: number;
  conversation_id: string;
  workflow_messages: any[];
  sources: any[];
  metadata: Record<string, any>;
}
```

#### Get Chat Messages
```http
GET /api/async_chat/chats/{chat_id}
```

**Response:**
```json
{
  "chat_id": "string",
  "messages": [],
  "message_count": 0
}
```

#### List All Chats
```http
GET /api/async_chat/chats
```

**Response:**
```json
{
  "chats": [],
  "total_count": 0
}
```

#### Delete Chat
```http
DELETE /api/async_chat/chats/{chat_id}
```

**Response:**
```json
{
  "chat_id": "string",
  "deleted": true
}
```

#### Chat Health Check
```http
GET /api/async_chat/health
```

**Response:**
```json
{
  "status": "healthy|degraded|unhealthy",
  "llm": {
    "status": "healthy",
    "model": "llama3.2:1b-instruct-q4_K_M"
  },
  "async_architecture": true,
  "service": "chat"
}
```

## 2. Knowledge Base APIs

### 2.1 Chat Knowledge API (`/api/chat_knowledge/`)

#### Create Knowledge Context
```http
POST /api/chat_knowledge/context/create
Content-Type: application/json

{
  "chat_id": "string",
  "topic": "Optional topic name",
  "keywords": ["keyword1", "keyword2"]
}
```

#### Upload File to Chat
```http
POST /api/chat_knowledge/files/upload/{chat_id}
Content-Type: multipart/form-data

file: <uploaded_file>
association_type: "upload|reference|generated|modified"
```

#### Associate File with Chat
```http
POST /api/chat_knowledge/files/associate
Content-Type: application/json

{
  "chat_id": "string",
  "file_path": "path/to/file",
  "association_type": "upload|reference|generated|modified",
  "metadata": {}
}
```

#### Add Temporary Knowledge
```http
POST /api/chat_knowledge/knowledge/add_temporary
Content-Type: application/json

{
  "chat_id": "string",
  "content": "Knowledge content",
  "metadata": {}
}
```

#### Search Chat Knowledge
```http
POST /api/chat_knowledge/search
Content-Type: application/json

{
  "query": "search query",
  "chat_id": "optional-specific-chat-id",
  "include_temporary": true
}
```

#### Get Knowledge Decisions
```http
GET /api/chat_knowledge/knowledge/pending/{chat_id}
```

#### Apply Knowledge Decision
```http
POST /api/chat_knowledge/knowledge/decide
Content-Type: application/json

{
  "chat_id": "string",
  "knowledge_id": "string",
  "decision": "add_to_kb|keep_temporary|delete"
}
```

### 2.2 Knowledge Base API (`/api/knowledge_base/`)

#### Basic Statistics
```http
GET /api/knowledge_base/stats/basic
```

**Response:**
```json
{
  "total_documents": 3278,
  "total_chunks": 3278,
  "total_facts": 134
}
```

#### Detailed Statistics
```http
GET /api/knowledge_base/stats
```

#### Search Knowledge Base
```http
POST /api/knowledge_base/search
Content-Type: application/json

{
  "query": "search query",
  "n_results": 5
}
```

#### Add Text to Knowledge Base
```http
POST /api/knowledge_base/add_text
Content-Type: application/json

{
  "text": "content to add",
  "metadata": {}
}
```

#### Add File to Knowledge Base
```http
POST /api/knowledge_base/add_file
Content-Type: multipart/form-data

file: <uploaded_file>
```

#### Get Categories
```http
GET /api/knowledge_base/categories
```

#### Get Category Documents
```http
GET /api/knowledge_base/category/{category_path}/documents
```

#### Get Document Content
```http
POST /api/knowledge_base/document/content
Content-Type: application/json

{
  "document_path": "path/to/document"
}
```

## 3. WebSocket APIs

### 3.1 Real-time Communication (`/ws/`)

#### Main WebSocket Connection
```javascript
const ws = new WebSocket('ws://172.16.168.20:8001/ws');
```

#### Test WebSocket Connection
```javascript
const ws = new WebSocket('ws://172.16.168.20:8001/ws-test');
```

#### WebSocket Message Types

**Connection Established:**
```json
{
  "type": "connection_established",
  "payload": {
    "message": "WebSocket connected successfully"
  }
}
```

**Keep-alive Ping:**
```json
{
  "type": "ping"
}
```

**Chat Events:**
```json
{
  "type": "user_message",
  "payload": {
    "message": "User message content"
  }
}
```

**LLM Response:**
```json
{
  "type": "llm_response",
  "payload": {
    "response": "AI response content"
  }
}
```

**Workflow Events:**
```json
{
  "type": "workflow_step_started|workflow_step_completed|workflow_completed|workflow_failed",
  "payload": {
    "workflow_id": "workflow-uuid",
    "description": "Step description",
    "result": "Step result"
  }
}
```

**Error Events:**
```json
{
  "type": "error",
  "payload": {
    "message": "Error description"
  }
}
```

#### Client Messages to Server

**User Message:**
```json
{
  "type": "user_message",
  "payload": {
    "message": "Message content"
  }
}
```

**Pong Response:**
```json
{
  "type": "pong"
}
```

## 4. System Monitoring APIs

### 4.1 System API (`/api/system/`)

#### System Health Check
```http
GET /api/system/health
```

**Response:**
```json
{
  "status": "ok",
  "mode": "fast",
  "redis": true,
  "ollama": "connected",
  "details": {
    "ollama": {
      "status": "connected",
      "model": "llama3.2:1b-instruct-q4_K_M"
    }
  }
}
```

#### Frontend Configuration
```http
GET /api/system/frontend-config
```

**Response:**
```json
{
  "status": "success",
  "config": {
    "services": {
      "ollama": {
        "url": "http://127.0.0.1:11434",
        "endpoint": "http://127.0.0.1:11434/api/generate",
        "embedding_endpoint": "http://127.0.0.1:11434/api/embeddings"
      },
      "playwright": {
        "vnc_url": "http://172.16.168.25:6080",
        "api_url": "http://172.16.168.25:3000"
      },
      "redis": {
        "host": "172.16.168.23",
        "port": 6379,
        "enabled": true
      }
    },
    "api": {
      "timeout": 60000,
      "retry_attempts": 3,
      "streaming": false
    },
    "features": {
      "voice_enabled": false,
      "knowledge_base_enabled": true,
      "developer_mode": true
    }
  }
}
```

#### System Information
```http
GET /api/system/info
```

#### Available Models
```http
GET /api/system/models
```

### 4.2 Agent Configuration API (`/api/agent-config/`)

#### List All Agents
```http
GET /api/agent-config/agents
```

#### Get Specific Agent
```http
GET /api/agent-config/agents/{agent_id}
```

#### Agent Health Check
```http
GET /api/agent-config/agents/{agent_id}/health
```

#### Enable Agent
```http
POST /api/agent-config/agents/{agent_id}/enable
```

#### Disable Agent
```http
POST /api/agent-config/agents/{agent_id}/disable
```

#### Update Agent Model
```http
PUT /api/agent-config/agents/{agent_id}/model
Content-Type: application/json

{
  "model": "new-model-name"
}
```

### 4.3 Monitoring API (`/api/monitoring/`)

#### Service Health
```http
GET /api/monitoring/services/health
```

#### System Resources
```http
GET /api/monitoring/resources
```

#### Service Status
```http
GET /api/monitoring/services/status
```

#### Performance Monitoring Dashboard

```http
GET /api/monitoring/dashboard
```

#### Hardware Metrics
```http
GET /api/monitoring/hardware/gpu
GET /api/monitoring/hardware/npu
```

## 5. Authentication & Authorization

### Current Status
- **Authentication**: Currently no authentication required for API access
- **Rate Limiting**: No rate limiting implemented
- **CORS**: Configured for development mode

### Future Authentication (Planned)
```http
POST /api/system/login
Content-Type: application/json

{
  "username": "string",
  "password": "string"
}
```

**Expected Response:**
```json
{
  "token": "jwt-token",
  "expires_in": 3600,
  "user": {
    "id": "user-id",
    "username": "username",
    "roles": ["admin", "user"]
  }
}
```

## 6. Error Handling

### Standard Error Response Format
```json
{
  "detail": "Error message",
  "status_code": 400,
  "error_type": "validation_error|system_error|timeout_error"
}
```

### HTTP Status Codes
- `200`: Success
- `400`: Bad Request (validation error)
- `408`: Request Timeout  
- `422`: Validation Error
- `500`: Internal Server Error

### Common Error Scenarios

#### Timeout Errors
```json
{
  "detail": "Request timeout - chat processing took too long",
  "status_code": 408
}
```

#### Validation Errors
```json
{
  "detail": [
    {
      "loc": ["body", "message"],
      "msg": "ensure this value has at least 1 characters",
      "type": "value_error.any_str.min_length"
    }
  ],
  "status_code": 422
}
```

#### Service Unavailable
```json
{
  "detail": "Chat processing failed: LLM service unavailable",
  "status_code": 500
}
```

## 7. Integration Examples

### Frontend Framework Integration

#### React/TypeScript Example
```typescript
// API client configuration
const API_BASE = 'http://172.16.168.20:8001';

interface ChatMessage {
  message: string;
  options?: Record<string, any>;
}

interface ChatResponse {
  response: string;
  message_type: string;
  knowledge_status: string;
  processing_time: number;
  conversation_id: string;
}

// Create new chat
async function createNewChat(): Promise<string> {
  const response = await fetch(`${API_BASE}/api/async_chat/chats/new`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
  });
  
  if (!response.ok) {
    throw new Error(`Failed to create chat: ${response.statusText}`);
  }
  
  const data = await response.json();
  return data.chat_id;
}

// Send chat message
async function sendChatMessage(
  chatId: string, 
  message: ChatMessage
): Promise<ChatResponse> {
  const response = await fetch(
    `${API_BASE}/api/async_chat/chats/${chatId}/message`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(message),
    }
  );
  
  if (!response.ok) {
    throw new Error(`Failed to send message: ${response.statusText}`);
  }
  
  return await response.json();
}

// WebSocket connection
function connectWebSocket(onMessage: (data: any) => void) {
  const ws = new WebSocket(`ws://172.16.168.20:8001/ws`);
  
  ws.onopen = () => {
    console.log('WebSocket connected');
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    onMessage(data);
  };
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
  
  return ws;
}
```

#### Vue.js/Composition API Example
```typescript
import { ref, onMounted, onUnmounted } from 'vue';

export function useChatAPI() {
  const chatId = ref<string>('');
  const messages = ref<ChatResponse[]>([]);
  const isConnected = ref(false);
  const ws = ref<WebSocket | null>(null);

  const createChat = async () => {
    try {
      const response = await fetch('/api/async_chat/chats/new', {
        method: 'POST',
      });
      const data = await response.json();
      chatId.value = data.chat_id;
    } catch (error) {
      console.error('Failed to create chat:', error);
    }
  };

  const sendMessage = async (message: string) => {
    if (!chatId.value) await createChat();
    
    try {
      const response = await fetch(
        `/api/async_chat/chats/${chatId.value}/message`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message }),
        }
      );
      
      const result = await response.json();
      messages.value.push(result);
    } catch (error) {
      console.error('Failed to send message:', error);
    }
  };

  const connectWebSocket = () => {
    ws.value = new WebSocket('ws://172.16.168.20:8001/ws');
    
    ws.value.onopen = () => {
      isConnected.value = true;
    };
    
    ws.value.onmessage = (event) => {
      const data = JSON.parse(event.data);
      // Handle real-time updates
    };
    
    ws.value.onclose = () => {
      isConnected.value = false;
    };
  };

  onMounted(() => {
    connectWebSocket();
  });

  onUnmounted(() => {
    ws.value?.close();
  });

  return {
    chatId,
    messages,
    isConnected,
    createChat,
    sendMessage,
  };
}
```

## 8. Performance Considerations

### Request Timeouts
- **Chat Messages**: 20-second timeout implemented
- **Knowledge Search**: 5-second timeout
- **WebSocket**: 30-second keepalive ping

### Rate Limiting (Recommended)
```typescript
// Implement client-side rate limiting
class APIRateLimit {
  private requests: number[] = [];
  private maxRequests = 10;
  private windowMs = 60000; // 1 minute

  canMakeRequest(): boolean {
    const now = Date.now();
    this.requests = this.requests.filter(time => now - time < this.windowMs);
    return this.requests.length < this.maxRequests;
  }

  recordRequest() {
    this.requests.push(Date.now());
  }
}
```

### Error Recovery
```typescript
// Exponential backoff for failed requests
async function retryWithBackoff(
  fn: () => Promise<any>,
  maxRetries = 3,
  baseDelay = 1000
) {
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (attempt === maxRetries - 1) throw error;
      
      const delay = baseDelay * Math.pow(2, attempt);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}
```

## 9. Development & Testing

### Health Check Sequence
```typescript
// Verify all services are operational
async function systemHealthCheck() {
  const endpoints = [
    '/api/health',
    '/api/async_chat/health',
    '/api/chat_knowledge/health',
    '/api/monitoring/services/health'
  ];
  
  for (const endpoint of endpoints) {
    try {
      const response = await fetch(`${API_BASE}${endpoint}`);
      console.log(`${endpoint}: ${response.ok ? 'OK' : 'FAIL'}`);
    } catch (error) {
      console.error(`${endpoint}: ERROR - ${error.message}`);
    }
  }
}
```

### WebSocket Testing
```typescript
// Test WebSocket connectivity and message handling
function testWebSocket() {
  const ws = new WebSocket('ws://172.16.168.20:8001/ws-test');
  
  ws.onopen = () => {
    console.log('Test WebSocket connected');
    ws.send('test message');
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('Received:', data);
    
    if (data.type === 'echo') {
      console.log('Echo test successful');
      ws.close();
    }
  };
}
```

## 10. Migration & Updates

### API Versioning
Currently all APIs are unversioned. Future versions may introduce:
- `/api/v1/` prefix for versioned endpoints
- Deprecation headers for outdated endpoints
- Migration guides for breaking changes

### Backward Compatibility
- Current endpoints will remain functional
- New features will be additive, not replacing
- Breaking changes will be announced with migration period

---

## Summary

This specification covers all major API endpoints needed for frontend integration:

✅ **Chat System**: 7 endpoints for async chat functionality  
✅ **Knowledge Base**: 15+ endpoints for knowledge management  
✅ **WebSocket**: Real-time communication with 10+ message types  
✅ **System Monitoring**: Health checks and configuration endpoints  
✅ **Error Handling**: Standardized error responses and recovery  
✅ **Integration Examples**: TypeScript/React/Vue.js examples  
✅ **Performance Guidelines**: Timeouts, rate limiting, error recovery  

The AutoBot backend provides a comprehensive API surface for building sophisticated frontend applications with real-time chat, knowledge management, and system monitoring capabilities.