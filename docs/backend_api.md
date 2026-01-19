# AutoBot Backend API Documentation

## Base URL
- **Backend**: `http://localhost:8001`
- **API Prefix**: `/api`

## Authentication
Currently, authentication is disabled by default. When enabled, use the `/api/login` endpoint.

---

## Health & System Endpoints

### GET `/api/health`
**Description**: Health check endpoint for monitoring backend status
**Response**: 
```json
{
  "status": "healthy|unhealthy",
  "backend": "connected",
  "orchestrator": "connected|disconnected|error",
  "llm": "connected|disconnected",
  "timestamp": 1642781234.567
}
```
**Status Codes**: 
- `200`: System healthy
- `503`: System unhealthy

### GET `/api/hello`
**Description**: Simple test endpoint
**Response**:
```json
{
  "message": "Hello from AutoBot backend!"
}
```

### GET `/api/version`
**Description**: Get backend version information
**Response**:
```json
{
  "version_no": "1.0.0",
  "version_time": "2025-06-18 20:00 UTC"
}
```

### GET `/api/system_metrics`
**Description**: Get real-time system metrics (CPU, RAM, GPU/VRAM)
**Response**:
```json
{
  "cpu_percent": 45.2,
  "memory_percent": 67.8,
  "gpu_percent": 23.1,
  "vram_percent": 12.5
}
```

---

## Goal & Task Execution

### POST `/api/goal`
**Description**: Submit a goal for the AI agent to execute
**Request Body**:
```json
{
  "goal": "string - The task description",
  "use_phi2": false,
  "user_role": "user"
}
```
**Response**:
```json
{
  "message": "Task execution result or response text"
}
```
**Status Codes**:
- `200`: Goal processed successfully
- `403`: Permission denied
- `500`: Execution error

### POST `/api/command_approval`
**Description**: Approve or deny command execution requests
**Request Body**:
```json
{
  "task_id": "string - Task identifier",
  "approved": true,
  "user_role": "user"
}
```
**Response**:
```json
{
  "message": "Approval status received and forwarded",
  "task_id": "task_123",
  "approved": true
}
```

---

## Chat & Conversation Management

### GET `/api/chats`
**Description**: List all available chat sessions
**Response**:
```json
{
  "chats": ["session_1", "session_2", "session_3"]
}
```

### GET `/api/chats/{chat_id}`
**Description**: Get specific chat session history
**Parameters**:
- `chat_id` (path): Chat session identifier
**Response**:
```json
{
  "chat_id": "session_123",
  "history": [
    {
      "role": "user",
      "content": "Hello",
      "timestamp": "2025-07-17T19:30:00Z"
    }
  ]
}
```

### POST `/api/chats/new`
**Description**: Create a new chat session
**Response**:
```json
{
  "chat_id": "uuid-generated-id",
  "status": "success"
}
```

### GET `/api/chat/history`
**Description**: Get complete conversation history
**Response**:
```json
{
  "history": [...],
  "tokens": 1234
}
```

### POST `/api/chat/reset`
**Description**: Clear entire chat history
**Form Data**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Chat history cleared successfully"
}
```

### POST `/api/chat/new`
**Description**: Start new chat session (clears current)
**Form Data**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "New chat session started successfully"
}
```

### GET `/api/chat/list_sessions`
**Description**: List available chat sessions
**Query Parameters**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "sessions": ["session1", "session2"]
}
```

### GET `/api/chat/load_session/{session_id}`
**Description**: Load specific chat session
**Parameters**:
- `session_id` (path): Session identifier
**Query Parameters**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Session loaded successfully",
  "history": [...]
}
```

### POST `/api/chat/save_session`
**Description**: Save current chat as named session
**Form Data**:
- `session_id`: Session name (default: "default_session")
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Current chat session saved as 'session_name'"
}
```

---

## Configuration & Settings

### GET `/api/settings`
**Description**: Get complete system configuration
**Response**: Complete configuration object from ConfigManager

### POST `/api/settings`
**Description**: Update system configuration
**Request Body**: JSON object with configuration updates
**Response**:
```json
{
  "message": "Settings updated successfully"
}
```

### GET `/api/settings/backend`
**Description**: Get backend-specific settings
**Response**: Backend configuration section

### POST `/api/settings/backend`
**Description**: Update backend-specific settings
**Request Body**: JSON object with backend settings
**Response**:
```json
{
  "message": "Backend settings updated successfully"
}
```

---

## File Management

### GET `/api/files`
**Description**: List files and directories
**Query Parameters**:
- `path`: Directory path to list (default: "")
**Response**:
```json
{
  "files": [
    {
      "name": "filename.txt",
      "path": "relative/path/filename.txt", 
      "is_dir": false,
      "size": 1024,
      "last_modified": 1642781234.567
    }
  ]
}
```

### POST `/api/uploadfile/`
**Description**: Upload file to knowledge base
**Form Data**:
- `file`: File upload
- `file_type`: "txt|pdf|csv|docx"
- `metadata`: JSON string (optional)
**Response**:
```json
{
  "filename": "document.pdf",
  "message": "File uploaded and added to KB successfully",
  "kb_result": {...}
}
```

### DELETE `/api/delete_file`
**Description**: Delete file or empty directory
**Query Parameters**:
- `path`: File/directory path to delete
**Response**:
```json
{
  "message": "File 'path/file.txt' deleted successfully"
}
```

---

## Knowledge Base

### POST `/api/knowledge_base/store_fact`
**Description**: Store structured fact in knowledge base
**Form Data**:
- `content`: Fact content (required)
- `metadata`: JSON metadata (optional)
**Response**:
```json
{
  "status": "success",
  "message": "Fact stored successfully",
  "fact_id": 123
}
```

### GET `/api/knowledge_base/get_fact`
**Description**: Retrieve facts from knowledge base
**Query Parameters**:
- `fact_id`: Specific fact ID (optional)
- `query`: Search query string (optional)
**Response**:
```json
{
  "facts": [
    {
      "id": 123,
      "content": "Fact content",
      "metadata": {...},
      "timestamp": "2025-07-17T19:30:00Z"
    }
  ]
}
```

### POST `/api/knowledge_base/search`
**Description**: Search vector store in knowledge base
**Form Data**:
- `query`: Search query (required)
- `n_results`: Number of results (default: 5)
**Response**:
```json
{
  "results": [
    {
      "content": "Relevant document content...",
      "metadata": {...},
      "score": 0.85
    }
  ]
}
```

---

## System Commands

### POST `/api/execute_command`
**Description**: Execute shell command
**Request Body**:
```json
{
  "command": "ls -la"
}
```
**Form Data**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Command executed successfully",
  "output": "command output text",
  "status": "success"
}
```
**Status Codes**:
- `200`: Success
- `400`: No command provided
- `403`: Permission denied
- `500`: Execution error

---

## Voice Interface

### POST `/api/voice/listen`
**Description**: Convert speech to text
**Form Data**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Speech recognized",
  "text": "Recognized speech text"
}
```

### POST `/api/voice/speak`
**Description**: Convert text to speech
**Form Data**:
- `text`: Text to speak (required)
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Text spoken successfully"
}
```

---

## Agent Control

### POST `/api/agent/pause`
**Description**: Pause agent operations
**Form Data**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Agent paused successfully"
}
```

### POST `/api/agent/resume`
**Description**: Resume agent operations
**Form Data**:
- `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Agent resumed successfully"
}
```

---

## Authentication

### POST `/api/login`
**Description**: Authenticate user (when authentication enabled)
**Form Data**:
- `username`: User login name
- `password`: User password
**Response**:
```json
{
  "message": "Login successful",
  "role": "user|admin"
}
```
**Status Codes**:
- `200`: Login successful
- `401`: Invalid credentials

---

## Additional Endpoints

### GET `/api/prompts`
**Description**: Get available system prompts
**Response**:
```json
{
  "prompts": [
    {
      "name": "system_prompt",
      "content": "Prompt content..."
    }
  ]
}
```

### GET `/ctx_window_get`
**Description**: Get LLM context window content (development)
**Response**:
```json
{
  "content": "Context window content...",
  "tokens": 1234
}
```

---

## WebSocket Endpoints

### WebSocket `/ws`
**Description**: Real-time event stream for frontend updates
**Events**: 
- `goal_received`, `plan_ready`, `goal_completed`
- `command_execution_start`, `command_execution_end`
- `error`, `progress`, `llm_response`
- `settings_updated`, `file_uploaded`
- `diagnostics_report`, `user_permission_request`

---

## Error Responses

### Standard Error Format
```json
{
  "message": "Error description",
  "detail": "Additional error details (when available)"
}
```

### Common Status Codes
- `200`: Success
- `400`: Bad Request
- `401`: Unauthorized
- `403`: Forbidden
- `404`: Not Found
- `405`: Method Not Allowed
- `500`: Internal Server Error
- `503`: Service Unavailable

---

## Usage Examples

### Execute a Goal
```bash
curl -X POST http://localhost:8001/api/goal \
  -H "Content-Type: application/json" \
  -d '{"goal": "List files in current directory", "user_role": "user"}'
```

### Upload File to Knowledge Base
```bash
curl -X POST http://localhost:8001/api/uploadfile/ \
  -F "file=@document.pdf" \
  -F "file_type=pdf" \
  -F "metadata={\"source\": \"user_upload\"}"
```

### Search Knowledge Base
```bash
curl -X POST http://localhost:8001/api/knowledge_base/search \
  -F "query=machine learning" \
  -F "n_results=10"
```

### Get System Health
```bash
curl http://localhost:8001/api/health
