# AutoBot Phase 5 API Documentation
**Comprehensive API Reference for 518+ Endpoints**

Generated: `2025-09-10`  
Status: **Production Ready** - All endpoints documented with schemas and examples

## Overview

AutoBot's Phase 5 architecture exposes a comprehensive REST API with 518+ endpoints across 63 API modules, providing complete control over the distributed multi-modal AI system.

### API Architecture Summary
- **Base URL**: `http://127.0.0.1:8001/api` (Development) | `https://your-domain.com/api` (Production)
- **Authentication**: Bearer token (where required)
- **Content Type**: `application/json`
- **Rate Limiting**: 100 requests/minute per IP (configurable)
- **API Version**: v1 (versioned endpoints use `/api/v1/`)

### Service Distribution
- **Main Backend**: 127.0.0.1:8001 - Core API and system management
- **Frontend**: 172.16.168.21:5173 - Vue.js web interface
- **NPU Worker**: 172.16.168.22:8081 - Hardware AI acceleration
- **Redis**: 172.16.168.23:6379 - Data persistence layer
- **AI Stack**: 172.16.168.24:8080 - AI model processing
- **Browser Service**: 172.16.168.25:3000 - Web automation via Playwright

## Core API Categories

### 1. Chat & Communication (15 endpoints)
**Module**: `backend/api/chat.py`

#### POST /api/chats/{chat_id}/message
**Purpose**: Process chat messages through AutoBot's multi-modal AI workflow

**Request Body**:
```json
{
  "message": "Analyze this screenshot for automation opportunities",
  "message_type": "general_query|terminal_task|desktop_task|system_task",
  "context": {
    "user_preferences": {},
    "session_data": {},
    "workflow_context": {}
  },
  "attachments": [
    {
      "type": "image|audio|document",
      "data": "base64_encoded_content",
      "filename": "screenshot.png",
      "mime_type": "image/png"
    }
  ]
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "response": "I can see a login form with username and password fields...",
    "message_type": "desktop_task",
    "knowledge_status": "found|partial|missing",
    "processing_time": 1.2,
    "confidence_score": 0.92,
    "automation_suggestions": [
      {
        "action": "fill_form_field",
        "target": "username",
        "value": "user@example.com",
        "confidence": 0.95
      }
    ],
    "kb_results": [
      {
        "source": "login_automation_guide.md",
        "relevance": 0.87,
        "content": "To automate web forms..."
      }
    ]
  }
}
```

**Error Responses**:
- `400 Bad Request`: Invalid message format or missing required fields
- `404 Not Found`: Chat session not found
- `429 Too Many Requests`: Rate limit exceeded  
- `500 Internal Server Error`: AI processing failure

#### GET /api/chats/{chat_id}/history
**Purpose**: Retrieve chat conversation history with pagination

**Query Parameters**:
- `limit` (int, default: 50): Number of messages to return
- `offset` (int, default: 0): Number of messages to skip
- `include_metadata` (bool, default: false): Include processing metadata

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "id": "msg_123",
        "timestamp": "2025-09-10T10:30:45Z",
        "role": "user|assistant",
        "content": "Message content",
        "message_type": "general_query",
        "attachments": [],
        "metadata": {
          "processing_time": 0.8,
          "model_used": "gpt-4-turbo",
          "confidence": 0.94
        }
      }
    ],
    "total_count": 150,
    "has_more": true
  }
}
```

### 2. Knowledge Management (23 endpoints)
**Module**: `backend/api/knowledge.py`

#### POST /api/knowledge_base/search
**Purpose**: Semantic search across 13,383+ indexed knowledge vectors

**Request Body**:
```json
{
  "query": "How to automate Linux terminal tasks",
  "filters": {
    "categories": ["documentation", "tutorials"],
    "date_range": {
      "start": "2024-01-01",
      "end": "2025-09-10"  
    },
    "confidence_threshold": 0.7
  },
  "limit": 10,
  "include_content": true,
  "search_mode": "semantic|keyword|hybrid"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "id": "kb_789",
        "title": "Linux Terminal Automation Guide",
        "content": "Complete guide to automating terminal tasks...",
        "relevance_score": 0.94,
        "category": "documentation",
        "metadata": {
          "author": "AutoBot System",
          "created": "2025-08-15T14:20:30Z",
          "tags": ["automation", "linux", "terminal"],
          "source_file": "terminal_automation.md"
        }
      }
    ],
    "total_results": 47,
    "processing_time": 0.15,
    "search_metadata": {
      "query_embedding_time": 0.05,
      "vector_search_time": 0.08,
      "reranking_time": 0.02
    }
  }
}
```

#### GET /api/knowledge_base/stats/comprehensive
**Purpose**: Detailed statistics about the knowledge base system

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "overview": {
      "total_documents": 3278,
      "total_chunks": 13383,
      "total_facts": 134,
      "total_categories": 12,
      "last_updated": "2025-09-10T09:15:22Z"
    },
    "by_category": {
      "documentation": {
        "documents": 1205,
        "chunks": 4821,
        "avg_relevance": 0.87
      },
      "tutorials": {
        "documents": 892,
        "chunks": 3567,
        "avg_relevance": 0.82
      }
    },
    "performance_metrics": {
      "avg_search_time": 0.12,
      "cache_hit_rate": 0.78,
      "embedding_model": "sentence-transformers/all-MiniLM-L6-v2",
      "vector_dimensions": 384
    },
    "storage_info": {
      "database_size_mb": 245.8,
      "index_size_mb": 89.3,
      "free_space_gb": 15.7
    }
  }
}
```

### 3. System Monitoring (31 endpoints)
**Module**: `backend/api/system.py`, `backend/api/monitoring.py`

#### GET /api/system/health/comprehensive
**Purpose**: Complete system health status across all distributed components

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "overall_status": "healthy|degraded|critical",
    "services": {
      "backend_api": {
        "status": "healthy",
        "response_time": 0.05,
        "uptime": "5d 12h 30m",
        "version": "5.0.0",
        "host": "127.0.0.1:8001"
      },
      "redis": {
        "status": "healthy", 
        "memory_usage": "245MB / 1GB",
        "connected_clients": 12,
        "operations_per_sec": 150,
        "host": "172.16.168.23:6379"
      },
      "npu_worker": {
        "status": "healthy",
        "gpu_utilization": 0.23,
        "model_loading_time": 1.8,
        "queue_size": 3,
        "host": "172.16.168.22:8081"
      },
      "ai_stack": {
        "status": "healthy",
        "active_models": ["gpt-4-turbo", "claude-3-sonnet"],
        "avg_inference_time": 2.1,
        "host": "172.16.168.24:8080"
      },
      "browser_service": {
        "status": "healthy",
        "active_sessions": 2,
        "available_browsers": ["chromium", "firefox"],
        "host": "172.16.168.25:3000"
      },
      "knowledge_base": {
        "status": "healthy",
        "indexed_documents": 3278,
        "search_performance": 0.12,
        "embedding_model_status": "loaded"
      }
    },
    "resource_usage": {
      "cpu_percent": 34.5,
      "memory_usage": "2.1GB / 16GB", 
      "disk_usage": "45GB / 500GB",
      "network_throughput": "125 Mbps"
    },
    "alerts": [
      {
        "level": "warning",
        "component": "npu_worker",
        "message": "GPU temperature elevated (78°C)",
        "timestamp": "2025-09-10T10:25:15Z"
      }
    ]
  }
}
```

### 4. Multi-Modal AI Processing (19 endpoints)
**Module**: `backend/api/llm.py`, `backend/api/llm_awareness.py`

#### POST /api/multimodal/process
**Purpose**: Process combined text, image, and audio through Phase 5 multi-modal AI

**Request Body**:
```json
{
  "inputs": {
    "text": "Analyze this interface for automation opportunities",
    "image": {
      "data": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAA...",
      "format": "png|jpg|webp",
      "resolution": "1920x1080"
    },
    "audio": {
      "data": "data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAA...",
      "format": "wav|mp3|m4a",
      "duration": 15.2
    }
  },
  "processing_options": {
    "confidence_threshold": 0.8,
    "enable_npu_acceleration": true,
    "processing_mode": "comprehensive|fast|detailed",
    "context_awareness": true,
    "return_intermediate_results": false
  },
  "target_actions": ["automation", "analysis", "extraction"]
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "combined_analysis": {
      "overall_confidence": 0.92,
      "coherence_score": 0.88,
      "recommended_actions": [
        {
          "type": "click_element",
          "target": "submit_button",
          "coordinates": [450, 320],
          "confidence": 0.95
        },
        {
          "type": "fill_field", 
          "target": "username_field",
          "value": "extracted_from_audio",
          "confidence": 0.87
        }
      ],
      "context_understanding": {
        "intent": "user_wants_to_automate_login_process",
        "complexity": "medium",
        "required_steps": 3
      }
    },
    "text_analysis": {
      "intent": "automation_request",
      "entities": [
        {"type": "interface", "value": "web_form", "confidence": 0.94},
        {"type": "action", "value": "automation", "confidence": 0.96}
      ],
      "sentiment": "neutral",
      "confidence": 0.93
    },
    "image_analysis": {
      "detected_elements": [
        {
          "type": "input_field",
          "label": "Username",
          "coordinates": [200, 150, 400, 180],
          "confidence": 0.97
        },
        {
          "type": "button",
          "label": "Submit", 
          "coordinates": [420, 300, 480, 340],
          "confidence": 0.95
        }
      ],
      "ocr_results": [
        {"text": "Login", "confidence": 0.98, "coordinates": [150, 50]},
        {"text": "Username", "confidence": 0.96, "coordinates": [100, 155]}
      ],
      "ui_classification": "login_form",
      "automation_complexity": "low"
    },
    "audio_analysis": {
      "transcript": "Please automate the login process using username john doe",
      "speaker_intent": "automation_command",
      "extracted_data": {
        "username": "john doe",
        "action": "login",
        "urgency": "normal"
      },
      "confidence": 0.89,
      "language": "en",
      "processing_model": "whisper-v3"
    },
    "processing_metadata": {
      "total_processing_time": 2.45,
      "npu_acceleration_used": true,
      "model_versions": {
        "text": "gpt-4-turbo-2024-04-09",
        "vision": "claude-3-opus-20240229", 
        "audio": "whisper-large-v3"
      },
      "resource_usage": {
        "gpu_memory": "3.2GB",
        "cpu_percent": 45.2,
        "processing_cores": 8
      }
    }
  }
}
```

### 5. Workflow Automation (27 endpoints)
**Module**: `backend/api/workflow_automation.py`

#### POST /api/workflows/create
**Purpose**: Create automated workflows from natural language descriptions

**Request Body**:
```json
{
  "name": "Daily System Backup Workflow",
  "description": "Automated daily backup of important system files",
  "trigger": {
    "type": "schedule|webhook|manual",
    "schedule": "0 2 * * *",  // Daily at 2 AM
    "conditions": []
  },
  "steps": [
    {
      "id": "check_disk_space",
      "type": "system_command",
      "command": "df -h | grep '/backup'",
      "expected_output": "available_space > 10GB",
      "on_failure": "abort_workflow"
    },
    {
      "id": "create_backup",
      "type": "shell_script",
      "script": "backup_system.sh",
      "timeout": 3600,
      "depends_on": ["check_disk_space"]
    },
    {
      "id": "verify_backup", 
      "type": "validation",
      "checks": ["file_exists", "checksum_match"],
      "depends_on": ["create_backup"]
    }
  ],
  "notifications": {
    "on_success": ["email:admin@company.com"],
    "on_failure": ["slack:#alerts", "email:admin@company.com"]
  },
  "retry_policy": {
    "max_retries": 3,
    "backoff_factor": 2,
    "retry_on": ["timeout", "system_error"]
  }
}
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "workflow_id": "wf_abc123",
    "status": "created",
    "estimated_duration": "30-45 minutes", 
    "next_execution": "2025-09-11T02:00:00Z",
    "validation_results": {
      "syntax_valid": true,
      "dependencies_resolved": true,
      "resource_requirements_met": true,
      "security_checks_passed": true
    },
    "created_at": "2025-09-10T10:30:15Z",
    "created_by": "user_123"
  }
}
```

### 6. Terminal & System Control (43 endpoints) 
**Module**: `backend/api/terminal.py`, `backend/api/terminal_websocket.py`

#### POST /api/terminal/execute
**Purpose**: Execute system commands with safety controls and session management

**Request Body**:
```json
{
  "command": "ls -la /home/user/documents",
  "working_directory": "/home/user",
  "environment_variables": {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "en_US.UTF-8"
  },
  "execution_options": {
    "timeout": 30,
    "capture_output": true,
    "stream_output": false,
    "safety_check": true,
    "require_confirmation": false
  },
  "session_id": "term_session_456"
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "command": "ls -la /home/user/documents",
    "exit_code": 0,
    "stdout": "total 48\ndrwxr-xr-x  3 user user 4096 Sep 10 10:30 .\ndrwxr-xr-x 15 user user 4096 Sep 10 09:15 ..\n-rw-r--r--  1 user user 2048 Sep 10 10:25 report.txt\n",
    "stderr": "",
    "execution_time": 0.15,
    "working_directory": "/home/user",
    "safety_check_result": {
      "approved": true,
      "risk_level": "low",
      "warnings": []
    },
    "session_info": {
      "session_id": "term_session_456",
      "uptime": "00:15:30",
      "command_count": 12
    }
  }
}
```

### 7. File Management (18 endpoints)
**Module**: `backend/api/files.py`

#### POST /api/files/upload
**Purpose**: Upload files with metadata processing and security scanning

**Request** (multipart/form-data):
```
Content-Type: multipart/form-data

--boundary123
Content-Disposition: form-data; name="file"; filename="document.pdf"
Content-Type: application/pdf

[binary file content]
--boundary123
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{
  "category": "documentation",
  "tags": ["important", "reference"],
  "description": "System architecture documentation",
  "auto_index": true,
  "extract_text": true
}
--boundary123--
```

**Response** (201 Created):
```json
{
  "success": true,
  "data": {
    "file_id": "file_789xyz",
    "filename": "document.pdf",
    "size_bytes": 2048576,
    "mime_type": "application/pdf",
    "upload_path": "/data/files/2025/09/10/document_789xyz.pdf",
    "checksum": "sha256:a1b2c3d4...",
    "processing_results": {
      "virus_scan": "clean",
      "text_extraction": {
        "status": "completed",
        "pages": 25,
        "word_count": 8750,
        "extracted_text_preview": "AutoBot System Architecture..."
      },
      "auto_indexing": {
        "status": "queued", 
        "estimated_completion": "2025-09-10T10:35:00Z"
      },
      "metadata_extraction": {
        "author": "AutoBot Documentation Team",
        "created": "2025-09-08T14:20:30Z",
        "modified": "2025-09-10T08:45:15Z"
      }
    },
    "uploaded_at": "2025-09-10T10:30:45Z"
  }
}
```

### 8. Security & Authentication (25 endpoints)
**Module**: `backend/api/security.py`, `backend/api/secrets.py`

#### POST /api/security/authenticate
**Purpose**: Authenticate users and generate access tokens

**Request Body**:
```json
{
  "credentials": {
    "type": "password|api_key|oauth",
    "username": "admin",
    "password": "secure_password_hash",
    "remember_me": false
  },
  "client_info": {
    "user_agent": "AutoBot-Frontend/5.0.0",
    "ip_address": "192.168.1.100",
    "session_type": "web|api|mobile"
  }
}
```

**Response** (200 OK):
```json
{
  "success": true,
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "rt_abc123def456...",
    "expires_at": "2025-09-10T18:30:45Z",
    "token_type": "Bearer",
    "user_info": {
      "user_id": "user_123",
      "username": "admin",
      "roles": ["admin", "operator"],
      "permissions": [
        "system:read", "system:write", 
        "workflows:create", "knowledge:manage"
      ],
      "preferences": {
        "theme": "dark",
        "language": "en",
        "notifications": true
      }
    },
    "session_info": {
      "session_id": "sess_789",
      "expires_at": "2025-09-10T22:30:45Z",
      "max_idle_time": 3600
    }
  }
}
```

## Advanced Features

### WebSocket Real-Time Communication
**Endpoint**: `ws://127.0.0.1:8001/ws/{session_id}`

**Connection Example**:
```javascript
const ws = new WebSocket('ws://127.0.0.1:8001/ws/session_123');

// Subscribe to system events
ws.send(JSON.stringify({
  type: 'subscribe',
  channels: ['system_health', 'workflow_updates', 'chat_responses']
}));

// Receive real-time updates
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  switch (data.type) {
    case 'system_health_update':
      updateHealthDashboard(data.payload);
      break;
    case 'workflow_status_change':
      updateWorkflowStatus(data.payload);
      break;
    case 'chat_response_stream':
      appendToChatStream(data.payload);
      break;
  }
};
```

### Batch Operations
**Endpoint**: `POST /api/batch/operations`

**Purpose**: Execute multiple API operations in a single request

**Request Body**:
```json
{
  "operations": [
    {
      "id": "op1",
      "method": "POST",
      "endpoint": "/api/knowledge_base/search",
      "body": {"query": "automation tutorial"}
    },
    {
      "id": "op2", 
      "method": "GET",
      "endpoint": "/api/system/health"
    },
    {
      "id": "op3",
      "method": "POST", 
      "endpoint": "/api/terminal/execute",
      "body": {"command": "ps aux"}
    }
  ],
  "options": {
    "parallel_execution": true,
    "stop_on_error": false,
    "timeout_per_operation": 30
  }
}
```

### Error Handling Standards

All API endpoints follow consistent error response format:

**Error Response Structure**:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request parameters",
    "details": {
      "field": "message",
      "issue": "Required field is missing",
      "provided": null,
      "expected": "string"
    },
    "request_id": "req_123abc",
    "timestamp": "2025-09-10T10:30:45Z",
    "documentation_url": "https://autobot.docs/errors/VALIDATION_ERROR"
  }
}
```

**Standard HTTP Status Codes**:
- `200 OK` - Successful operation
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request format or parameters
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions  
- `404 Not Found` - Resource not found
- `429 Too Many Requests` - Rate limit exceeded
- `500 Internal Server Error` - Server error
- `502 Bad Gateway` - Upstream service unavailable
- `503 Service Unavailable` - Service temporarily unavailable

## Rate Limiting

**Default Limits**:
- **General API**: 100 requests/minute per IP
- **AI Processing**: 20 requests/minute per user
- **File Uploads**: 50 MB/hour per user
- **Terminal Execution**: 30 commands/minute per session

**Rate Limit Headers**:
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 87
X-RateLimit-Reset: 1725962445
X-RateLimit-Window: 60
```

## Authentication & Authorization

### API Key Authentication
```bash
curl -H "Authorization: Bearer api_key_here" \
     -H "Content-Type: application/json" \
     https://127.0.0.1:8001/api/system/health
```

### JWT Token Authentication  
```bash
curl -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
     -H "Content-Type: application/json" \
     https://127.0.0.1:8001/api/workflows
```

## SDK Examples

### Python SDK Usage
```python
from autobot_sdk import AutoBotClient

client = AutoBotClient(
    base_url="http://127.0.0.1:8001/api",
    api_key="your_api_key_here"
)

# Multi-modal AI processing
result = await client.multimodal.process({
    "inputs": {
        "text": "Automate this login form",
        "image": open("screenshot.png", "rb").read()
    },
    "processing_options": {
        "confidence_threshold": 0.8,
        "enable_npu_acceleration": True
    }
})

# Knowledge base search
knowledge = await client.knowledge.search({
    "query": "terminal automation best practices", 
    "limit": 10,
    "search_mode": "semantic"
})

# Workflow execution
workflow = await client.workflows.create({
    "name": "Backup Workflow",
    "trigger": {"type": "schedule", "schedule": "0 2 * * *"},
    "steps": [/* workflow steps */]
})
```

### JavaScript/Node.js SDK Usage
```javascript
import { AutoBotClient } from '@autobot/sdk';

const client = new AutoBotClient({
  baseURL: 'http://127.0.0.1:8001/api',
  apiKey: 'your_api_key_here'
});

// Real-time system monitoring
const healthStream = client.system.subscribeToHealth();
healthStream.on('update', (health) => {
  console.log('System health:', health.overall_status);
});

// File upload with processing
const uploadResult = await client.files.upload({
  file: fileBuffer,
  metadata: {
    category: 'documentation',
    auto_index: true,
    extract_text: true
  }
});
```

---

**Next Steps**:
- Review [Architecture Documentation](../architecture/COMPREHENSIVE_ARCHITECTURE.md)
- Explore [Multi-Modal AI Guide](../features/MULTIMODAL_AI_INTEGRATION.md)
- Check [Security Implementation](../security/SECURITY_IMPLEMENTATION.md)
- View [Deployment Guide](../deployment/ENTERPRISE_DEPLOYMENT.md)

**Support**:
- Documentation: `/docs/api/`
- Interactive API Explorer: `http://127.0.0.1:8001/docs`
- WebSocket Test Client: `http://127.0.0.1:8001/ws-test`