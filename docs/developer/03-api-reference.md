# AutoBot Backend API Documentation

## Base URL
- **Backend**: `http://localhost:8001` (configurable via `config/config.yaml`)
- **API Prefix**: `/api`

## Authentication & Security
Authentication is currently disabled by default. The system includes a security layer with audit logging and permission checks. When authentication is enabled, use the `/api/login` endpoint.

---

## Agent Management

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
**Status Codes**: `200` Success, `403` Permission denied, `500` Execution error

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

### POST `/api/pause`
**Description**: Pause agent operations
**Form Data**: `user_role`: "user" (default)
**Response**: `{"message": "Agent paused successfully"}`

### POST `/api/resume`
**Description**: Resume agent operations
**Form Data**: `user_role`: "user" (default)
**Response**: `{"message": "Agent resumed successfully"}`

### POST `/api/execute_command`
**Description**: Execute shell command
**Request Body**: `{"command": "ls -la"}`
**Form Data**: `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Command executed successfully",
  "output": "command output text",
  "status": "success"
}
```
**Status Codes**: `200` Success, `400` No command, `403` Permission denied, `500` Error

---

## Chat Management

### RESTful Chat Endpoints

#### POST `/api/chats/new`
**Description**: Create a new chat session
**Response**:
```json
{
  "chatId": "uuid-generated-id",
  "status": "success"
}
```

#### GET `/api/chats`
**Description**: List all available chat sessions
**Response**:
```json
{
  "chats": ["session_1", "session_2", "session_3"]
}
```

#### GET `/api/chats/{chat_id}`
**Description**: Get specific chat session history
**Parameters**: `chat_id` (path) - Chat session identifier
**Response**:
```json
{
  "chat_id": "session_123",
  "history": [
    {
      "sender": "user|bot",
      "text": "Message content",
      "messageType": "user|response",
      "rawData": null,
      "timestamp": "2025-07-17 19:30:00"
    }
  ]
}
```

#### POST `/api/chats/{chat_id}/message`
**Description**: Send a message to a specific chat and get a response
**Parameters**: `chat_id` (path) - Chat session identifier
**Request Body**:
```json
{
  "message": "User message text"
}
```
**Response**:
```json
{
  "response": "Bot response text",
  "status": "success",
  "chat_id": "chat_123",
  "message_count": 5
}
```

#### DELETE `/api/chats/{chat_id}`
**Description**: Delete a specific chat session
**Response**: `{"message": "Chat deleted successfully"}`

#### POST `/api/chats/{chat_id}/save`
**Description**: Save chat data for a specific session
**Request Body**:
```json
{
  "messages": [/* array of messages */]
}
```
**Response**: `{"status": "success"}`

#### POST `/api/chats/{chat_id}/reset`
**Description**: Reset a specific chat session
**Response**: `{"status": "success"}`

#### POST `/api/chats/cleanup_messages`
**Description**: Clean up leftover message files and temporary data
**Response**:
```json
{
  "status": "success",
  "message": "Cleaned up N leftover files",
  "cleaned_files": ["list of cleaned files"],
  "freed_space_bytes": 12345
}
```

### Legacy Chat Endpoints (Compatibility)

#### POST `/api/chat`
**Description**: Send a message (legacy endpoint for frontend compatibility)
**Request Body**:
```json
{
  "chatId": "chat_id",
  "message": "message text"
}
```

#### GET `/api/chat/history`
**Description**: Get complete conversation history
**Response**:
```json
{
  "history": [/* message array */],
  "tokens": 1234
}
```

#### POST `/api/chat/reset`
**Description**: Clear entire chat history
**Form Data**: `user_role`: "user" (default)
**Response**: `{"message": "Chat history cleared successfully"}`

#### POST `/api/chat/new`
**Description**: Start new chat session (clears current)
**Form Data**: `user_role`: "user" (default)
**Response**: `{"message": "New chat session started successfully"}`

#### GET `/api/chat/list_sessions`
**Description**: List available chat sessions
**Query Parameters**: `user_role`: "user" (default)
**Response**: `{"sessions": ["session1", "session2"]}`

#### GET `/api/chat/load_session/{session_id}`
**Description**: Load specific chat session
**Parameters**: `session_id` (path) - Session identifier
**Query Parameters**: `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Session loaded successfully",
  "history": [/* message array */]
}
```

#### POST `/api/chat/save_session`
**Description**: Save current chat as named session
**Form Data**: `session_id`, `user_role`: "user" (default)
**Response**: `{"message": "Current chat session saved as 'session_name'"}`

---

## File Management

### GET `/api/files/list`
**Description**: List files and directories in sandbox
**Query Parameters**: `path`: Directory path to list (default: "")
**Response**:
```json
{
  "current_path": "path/to/directory",
  "parent_path": "parent/path",
  "files": [
    {
      "name": "filename.txt",
      "path": "relative/path/filename.txt",
      "is_directory": false,
      "size": 1024,
      "mime_type": "text/plain",
      "last_modified": "2025-07-17T19:30:00Z",
      "permissions": "644",
      "extension": ".txt"
    }
  ],
  "total_files": 5,
  "total_directories": 2,
  "total_size": 12345
}
```

### POST `/api/files/upload`
**Description**: Upload file to sandbox
**Form Data**:
- `file`: File upload
- `path`: Target directory path (default: "")
- `overwrite`: Whether to overwrite existing files (default: false)
**Response**:
```json
{
  "success": true,
  "message": "File uploaded successfully",
  "file_info": {/* file info object */},
  "upload_id": "upload_20250717_193000"
}
```

### GET `/api/files/download/{path:path}`
**Description**: Download a file from sandbox
**Parameters**: `path` - File path within sandbox
**Response**: File download (FileResponse)

### GET `/api/files/view/{path:path}`
**Description**: View file content or get file info
**Parameters**: `path` - File path within sandbox
**Response**:
```json
{
  "file_info": {/* file info object */},
  "content": "file content for text files",
  "is_text": true
}
```

### DELETE `/api/files/delete`
**Description**: Delete file or directory
**Request Body**:
```json
{
  "path": "relative/path/to/file"
}
```
**Response**: `{"message": "File deleted successfully"}`

### POST `/api/files/create_directory`
**Description**: Create new directory
**Form Data**: `path` (parent directory), `name` (directory name)
**Response**:
```json
{
  "message": "Directory created successfully",
  "directory_info": {/* directory info object */}
}
```

### GET `/api/files/stats`
**Description**: Get file system statistics
**Response**:
```json
{
  "sandbox_root": "/path/to/sandbox",
  "total_files": 100,
  "total_directories": 20,
  "total_size": 1048576,
  "total_size_mb": 1.0,
  "max_file_size_mb": 50,
  "allowed_extensions": [".txt", ".pdf", /* etc */]
}
```

---

## Knowledge Base Management

### POST `/api/knowledge/search`
**Description**: Search knowledge base
**Request Body**:
```json
{
  "query": "search terms",
  "limit": 10
}
```
**Response**:
```json
{
  "results": [
    {
      "content": "Relevant content...",
      "metadata": {/* metadata object */},
      "score": 0.85
    }
  ],
  "query": "search terms",
  "limit": 10,
  "total_results": 5
}
```

### POST `/api/knowledge/add_text`
**Description**: Add text content to knowledge base
**Request Body**:
```json
{
  "text": "Content to add",
  "title": "Optional title",
  "source": "Manual Entry"
}
```
**Response**:
```json
{
  "status": "success",
  "message": "Text added to knowledge base successfully",
  "fact_id": 123,
  "text_length": 256,
  "title": "title",
  "source": "Manual Entry"
}
```

### POST `/api/knowledge/add_url`
**Description**: Add URL reference to knowledge base
**Request Body**:
```json
{
  "url": "https://example.com",
  "method": "fetch"
}
```
**Response**:
```json
{
  "status": "success",
  "message": "URL reference added to knowledge base",
  "fact_id": 124,
  "url": "https://example.com",
  "method": "fetch"
}
```

### POST `/api/knowledge/add_file`
**Description**: Add file to knowledge base
**Form Data**: `file` - File upload
**Response**:
```json
{
  "status": "success",
  "message": "File added to knowledge base successfully",
  "filename": "document.pdf",
  "file_type": "pdf",
  "file_size": 12345
}
```

### GET `/api/knowledge/export`
**Description**: Export all knowledge base data
**Response**:
```json
{
  "export_timestamp": "2025-07-17T19:30:00",
  "total_entries": 50,
  "version": "1.0",
  "data": [/* exported data array */]
}
```

### POST `/api/knowledge/cleanup`
**Description**: Clean up old knowledge base entries
**Response**:
```json
{
  "status": "success",
  "message": "Knowledge base cleanup completed",
  "removed_count": 10,
  "days_kept": 30
}
```

### GET `/api/knowledge/stats`
**Description**: Get knowledge base statistics
**Response**:
```json
{
  "total_facts": 100,
  "total_documents": 25,
  "total_vectors": 500,
  "db_size": 1048576
}
```

### GET `/api/knowledge/detailed_stats`
**Description**: Get detailed knowledge base statistics
**Response**: Detailed statistics object

### POST `/api/knowledge/get_fact`
**Description**: Retrieve facts from knowledge base
**Form Data**: `fact_id` (optional), `query` (optional)
**Response**: `{"facts": [/* facts array */]}`

### Legacy Knowledge Base Endpoints

#### POST `/api/knowledge_base/store_fact`
**Description**: Store structured fact (legacy)
**Form Data**: `content` (required), `metadata` (optional JSON)
**Response**:
```json
{
  "status": "success",
  "message": "Fact stored successfully",
  "fact_id": 123
}
```

#### GET `/api/knowledge_base/get_fact`
**Description**: Retrieve facts (legacy)
**Query Parameters**: `fact_id` (optional), `query` (optional)
**Response**: `{"facts": [/* facts array */]}`

#### POST `/api/knowledge_base/search`
**Description**: Search vector store (legacy)
**Form Data**: `query` (required), `n_results` (default: 5)
**Response**: `{"results": [/* results array */]}`

---

## LLM Management

### GET `/api/llm/config`
**Description**: Get current LLM configuration
**Response**: Current LLM configuration object

### POST `/api/llm/config`
**Description**: Update LLM configuration
**Request Body**: JSON object with configuration updates
**Response**: Updated configuration result

### POST `/api/llm/test_connection`
**Description**: Test LLM connection with current configuration
**Response**:
```json
{
  "status": "connected|disconnected",
  "message": "Connection status message"
}
```

### GET `/api/llm/models`
**Description**: Get list of available LLM models
**Response**:
```json
{
  "models": [/* model array */],
  "total_count": 10
}
```

### GET `/api/llm/current`
**Description**: Get current LLM model and configuration
**Response**:
```json
{
  "model": "llama3.1",
  "provider": "ollama",
  "config": {/* full config object */}
}
```

---

## Redis Management

### GET `/api/redis/config`
**Description**: Get current Redis configuration
**Response**: Redis configuration object

### POST `/api/redis/config`
**Description**: Update Redis configuration
**Request Body**: JSON object with Redis configuration updates
**Response**: Updated configuration result

### POST `/api/redis/test_connection`
**Description**: Test Redis connection
**Response**:
```json
{
  "status": "connected|disconnected",
  "message": "Connection status message"
}
```

---

## Settings Management

### GET `/api/settings/`
**Description**: Get complete application settings
**Response**: Complete settings object

### POST `/api/settings/`
**Description**: Save application settings
**Request Body**: JSON object with settings updates
**Response**: Save result

### GET `/api/settings/backend`
**Description**: Get backend-specific settings
**Response**: Backend settings object

### POST `/api/settings/backend`
**Description**: Save backend-specific settings
**Request Body**: JSON object with backend settings
**Response**: Save result

### GET `/api/settings/config`
**Description**: Get complete application configuration
**Response**: Full configuration object

---

## Prompt Management

### GET `/api/prompts/`
**Description**: Get all available system prompts
**Response**:
```json
{
  "prompts": [
    {
      "id": "prompt_id",
      "name": "prompt_name",
      "type": "prompt_type",
      "path": "relative/path",
      "content": "Prompt content..."
    }
  ],
  "defaults": {/* default prompts object */}
}
```

### POST `/api/prompts/{prompt_id}`
**Description**: Save a specific prompt
**Parameters**: `prompt_id` (path) - Prompt identifier
**Request Body**:
```json
{
  "content": "Updated prompt content"
}
```
**Response**: Updated prompt object

### POST `/api/prompts/{prompt_id}/revert`
**Description**: Revert prompt to default version
**Parameters**: `prompt_id` (path) - Prompt identifier
**Response**: Reverted prompt object

---

## Developer Tools

### GET `/api/developer/endpoints`
**Description**: Get all registered API endpoints (requires developer mode)
**Response**:
```json
{
  "total_endpoints": 50,
  "routers": ["chat", "files", "knowledge", /* etc */],
  "endpoints": {
    "GET /api/health": {
      "router": "system",
      "path": "/api/health",
      "method": "GET",
      "name": "health_check",
      "summary": "",
      "tags": []
    }
  }
}
```

### GET `/api/developer/config`
**Description**: Get developer mode configuration
**Response**:
```json
{
  "enabled": false,
  "enhanced_errors": true,
  "endpoint_suggestions": true,
  "debug_logging": false
}
```

### POST `/api/developer/config`
**Description**: Update developer mode configuration
**Request Body**: JSON object with developer configuration
**Response**: Updated configuration

### GET `/api/developer/system-info`
**Description**: Get system information for debugging (requires developer mode)
**Response**:
```json
{
  "config_loaded": true,
  "backend_config": {/* backend config */},
  "redis_config": {/* redis config */},
  "llm_config": {/* llm config */},
  "available_routers": ["chat", "files", /* etc */]
}
```

---

## System Health & Information

### GET `/api/health`
**Description**: Health check endpoint
**Response**:
```json
{
  "status": "healthy|unhealthy",
  "backend": "connected",
  "ollama": "connected|disconnected|error",
  "redis_status": "connected|disconnected",
  "redis_search_module_loaded": true,
  "timestamp": "2025-07-17T19:30:00Z"
}
```
**Status Codes**: `200` Healthy, `500` Unhealthy

### GET `/api/hello`
**Description**: Simple test endpoint
**Response**: `{"message": "Hello from AutoBot backend!"}`

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
**Description**: Get real-time system metrics
**Response**:
```json
{
  "cpu_percent": 45.2,
  "memory_percent": 67.8,
  "gpu_percent": 23.1,
  "vram_percent": 12.5
}
```

### POST `/api/restart`
**Description**: Restart system components
**Response**: `{"status": "success", "message": "Restart initiated"}`

### GET `/api/models`
**Description**: Get available LLM models (system-level)
**Response**:
```json
{
  "status": "success",
  "models": ["model1", "model2"],
  "configured_models": {"model1": "model1"},
  "detailed_models": [/* detailed model info */]
}
```

### GET `/api/status`
**Description**: Get current system status
**Response**:
```json
{
  "status": "success",
  "current_llm": "Ollama: llama3.1",
  "default_llm": "ollama_llama3_1",
  "task_llm": "ollama_llama3_1",
  "ollama_models": {/* model mappings */},
  "timestamp": "2025-07-17T19:30:00Z"
}
```

### POST `/api/login`
**Description**: User authentication endpoint
**Form Data**: `username`, `password`
**Response**:
```json
{
  "message": "Login successful",
  "role": "user|admin"
}
```
**Status Codes**: `200` Success, `401` Invalid credentials

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

## Voice Interface

### POST `/api/voice/listen`
**Description**: Convert speech to text
**Form Data**: `user_role`: "user" (default)
**Response**:
```json
{
  "message": "Speech recognized",
  "text": "Recognized speech text"
}
```

### POST `/api/voice/speak`
**Description**: Convert text to speech
**Form Data**: `text` (required), `user_role`: "user" (default)
**Response**: `{"message": "Text spoken successfully"}`

---

## Legacy Endpoints

### POST `/api/uploadfile/`
**Description**: Upload file to knowledge base (legacy endpoint)
**Form Data**:
- `file`: File upload
- `file_type`: "txt|pdf|csv|docx"
- `metadata`: JSON string (optional)
**Response**:
```json
{
  "filename": "document.pdf",
  "message": "File uploaded and added to KB successfully",
  "kb_result": {/* knowledge base result */}
}
```

### DELETE `/api/delete_file`
**Description**: Delete file (legacy endpoint)
**Query Parameters**: `path` - File path to delete
**Response**: `{"message": "File deleted successfully"}`

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
  "detail": "Error description",
  "developer_info": {
    "requested_method": "GET",
    "requested_path": "/api/nonexistent",
    "similar_endpoints": ["GET /api/health"],
    "suggestion": "Check available endpoints"
  }
}
```

### Common Status Codes
- `200` Success
- `400` Bad Request
- `401` Unauthorized
- `403` Forbidden
- `404` Not Found
- `405` Method Not Allowed
- `409` Conflict
- `413` Payload Too Large
- `500` Internal Server Error
- `503` Service Unavailable

### Enhanced Error Responses (Developer Mode)
When developer mode is enabled, error responses include helpful suggestions for similar endpoints and debugging information.

---

## Usage Examples

### Execute a Goal
```bash
curl -X POST http://localhost:8001/api/goal \
  -H "Content-Type: application/json" \
  -d '{"goal": "List files in current directory", "user_role": "user"}'
```

### Create New Chat and Send Message
```bash
# Create new chat
curl -X POST http://localhost:8001/api/chats/new

# Send message to chat
curl -X POST http://localhost:8001/api/chats/{chat_id}/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how can you help me?"}'
```

### Upload File to Knowledge Base
```bash
curl -X POST http://localhost:8001/api/knowledge/add_file \
  -F "file=@document.pdf"
```

### Search Knowledge Base
```bash
curl -X POST http://localhost:8001/api/knowledge/search \
  -H "Content-Type: application/json" \
  -d '{"query": "machine learning", "limit": 10}'
```

### List Files in Sandbox
```bash
curl "http://localhost:8001/api/files/list?path=documents"
```

### Get System Health
```bash
curl http://localhost:8001/api/health
```

### Test LLM Connection
```bash
curl -X POST http://localhost:8001/api/llm/test_connection
```

---

## API Router Organization

The backend API is organized into the following routers:

- **Agent** (`/api/goal`, `/api/pause`, `/api/resume`, `/api/execute_command`, `/api/command_approval`) - Agent control and goal execution
- **Chat** (`/api/chat/*`, `/api/chats/*`) - Chat management and messaging
- **Files** (`/api/files/*`) - Secure file management within sandbox
- **Knowledge** (`/api/knowledge/*`) - Knowledge base operations
- **LLM** (`/api/llm/*`) - Language model configuration and testing
- **Redis** (`/api/redis/*`) - Redis configuration and connection testing
- **Settings** (`/api/settings/*`) - Application settings management
- **Prompts** (`/api/prompts/*`) - System prompt management
- **Developer** (`/api/developer/*`) - Developer tools and debugging
- **System** (`/api/health`, `/api/version`, `/api/models`, `/api/status`, `/api/login`) - System information and health
- **Voice** (`/api/voice/*`) - Voice interface operations

---

## Configuration Notes

- All endpoints support configurable base URLs through `config/config.yaml`
- Port, host, and other connection settings are centrally managed
- Security policies and audit logging are configured via the security layer
- Authentication and permission systems can be enabled/disabled per deployment
- Developer mode provides enhanced error messages and debugging tools
- File operations are sandboxed to `data/file_manager_root/` for security
- Knowledge base supports multiple file formats: txt, pdf, csv, docx, md
- Maximum file upload size is 50MB (configurable)
