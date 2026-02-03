# AutoBot API Documentation

Complete API reference for AutoBot's REST endpoints, WebSocket connections, and authentication mechanisms.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Base URLs](#base-urls)
- [Response Format](#response-format)
- [Error Handling](#error-handling)
- [Core APIs](#core-apis)
- [Advanced Features](#advanced-features)
- [WebSocket APIs](#websocket-apis)
- [Rate Limiting](#rate-limiting)
- [Examples](#examples)

## Overview

AutoBot provides a comprehensive REST API and WebSocket interface for interacting with its AI-powered automation capabilities. The API follows RESTful principles and returns JSON responses.

### API Version
- **Current Version**: v1
- **Base Path**: `/api`
- **Documentation Version**: 2.0
- **Last Updated**: 2025-01-16

## Authentication

### Authentication Methods

#### 1. Session-Based Authentication (Default)
```http
POST /api/auth/login
Content-Type: application/json

{
  "username": "user@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "success": true,
  "session_id": "sess_abc123def456",
  "user": {
    "id": "user_123",
    "username": "user@example.com",
    "role": "developer",
    "permissions": ["allow_shell_execute", "read_files"]
  }
}
```

#### 2. API Key Authentication
```http
GET /api/system/health
Authorization: Bearer api_key_abc123def456ghi789
```

#### 3. Role-Based Access Control
```json
{
  "roles": {
    "admin": {
      "permissions": ["allow_all", "allow_shell_execute"],
      "restrictions": []
    },
    "developer": {
      "permissions": ["allow_shell_execute", "read_files"],
      "restrictions": ["no_sudo", "no_system_modify"]
    },
    "tester": {
      "permissions": ["read_only", "execute_tests"],
      "restrictions": ["no_shell", "no_network"]
    },
    "guest": {
      "permissions": ["read_only"],
      "restrictions": ["no_execute", "no_modify", "no_network"]
    }
  }
}
```

## Base URLs

| Environment | Base URL |
|-------------|----------|
| Development | `http://localhost:8001/api` |
| Production | `https://your-domain.com/api` |
| Docker | `http://autobot-backend:8001/api` |

## Response Format

### Standard Response Structure
```json
{
  "success": true,
  "data": {
    "key": "value"
  },
  "message": "Operation completed successfully",
  "timestamp": "2025-01-16T10:30:00Z",
  "request_id": "req_abc123"
}
```

### Error Response Structure
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameters",
    "details": {
      "field": "username",
      "reason": "Field is required"
    }
  },
  "timestamp": "2025-01-16T10:30:00Z",
  "request_id": "req_abc123"
}
```

## Error Handling

### HTTP Status Codes

| Status Code | Meaning | Description |
|-------------|---------|-------------|
| 200 | OK | Request successful |
| 201 | Created | Resource created successfully |
| 400 | Bad Request | Invalid request parameters |
| 401 | Unauthorized | Authentication required |
| 403 | Forbidden | Insufficient permissions |
| 404 | Not Found | Resource not found |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Internal Server Error | Server error |
| 503 | Service Unavailable | Service temporarily unavailable |

### Error Codes

| Error Code | Description |
|------------|-------------|
| `VALIDATION_ERROR` | Input validation failed |
| `AUTHENTICATION_FAILED` | Login credentials invalid |
| `PERMISSION_DENIED` | Insufficient user permissions |
| `RESOURCE_NOT_FOUND` | Requested resource does not exist |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `SECURITY_VIOLATION` | Security policy violation |
| `WORKFLOW_ERROR` | Workflow execution failed |
| `LLM_ERROR` | LLM service error |
| `SYSTEM_ERROR` | Internal system error |

## Core APIs

### 1. System Management

#### System Health Check
```http
GET /api/system/health
```

**Response:**
```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "2.0.0",
    "uptime": 86400,
    "components": {
      "llm_service": "online",
      "knowledge_base": "online",
      "redis": "online",
      "memory_system": "online"
    },
    "performance": {
      "memory_usage": 45.2,
      "cpu_usage": 12.5,
      "active_sessions": 3
    }
  }
}
```

#### System Information
```http
GET /api/system/info
```

**Response:**
```json
{
  "success": true,
  "data": {
    "system": {
      "os": "Linux",
      "version": "Ubuntu 22.04",
      "architecture": "x86_64",
      "python_version": "3.10.13"
    },
    "autobot": {
      "version": "2.0.0",
      "build": "20250116-dev",
      "features": ["multi_modal", "npu_acceleration", "workflow_orchestration"]
    },
    "hardware": {
      "cpu_cores": 8,
      "memory_total": "16GB",
      "gpu_available": true,
      "npu_available": false
    }
  }
}
```

#### System Metrics
```http
GET /api/metrics
```

**Query Parameters:**
- `interval` (optional): Time interval (1h, 24h, 7d)
- `component` (optional): Specific component metrics

**Response:**
```json
{
  "success": true,
  "data": {
    "interval": "1h",
    "metrics": {
      "requests_total": 1250,
      "requests_per_minute": 20.8,
      "average_response_time": 0.245,
      "error_rate": 0.02,
      "active_workflows": 5,
      "llm_requests": 320,
      "memory_usage_peak": 67.5
    },
    "by_endpoint": {
      "/api/chat/message": {
        "requests": 450,
        "avg_time": 0.180,
        "error_rate": 0.01
      },
      "/api/workflow/execute": {
        "requests": 85,
        "avg_time": 2.340,
        "error_rate": 0.05
      }
    }
  }
}
```

### 2. Chat & Messaging

#### Send Chat Message
```http
POST /api/chat/message
Content-Type: application/json

{
  "message": "Hello, how can you help me today?",
  "context": {
    "conversation_id": "conv_123",
    "user_preferences": {
      "response_style": "detailed",
      "include_code_examples": true
    }
  },
  "metadata": {
    "source": "web_interface",
    "timestamp": "2025-01-16T10:30:00Z"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "response": "Hello! I'm AutoBot, an AI assistant that can help you with automation tasks, system operations, research, and more. What would you like to work on?",
    "message_id": "msg_abc123",
    "conversation_id": "conv_123",
    "agent_used": "chat_agent",
    "model": "llama3.2:1b",
    "metadata": {
      "response_time": 0.245,
      "confidence": 0.95,
      "tokens_used": 45
    }
  }
}
```

#### Get Chat History
```http
GET /api/chat/history?limit=20&conversation_id=conv_123
```

**Response:**
```json
{
  "success": true,
  "data": {
    "messages": [
      {
        "id": "msg_123",
        "conversation_id": "conv_123",
        "role": "user",
        "content": "Hello, how can you help me today?",
        "timestamp": "2025-01-16T10:30:00Z"
      },
      {
        "id": "msg_124",
        "conversation_id": "conv_123",
        "role": "assistant",
        "content": "Hello! I'm AutoBot...",
        "timestamp": "2025-01-16T10:30:05Z",
        "metadata": {
          "agent": "chat_agent",
          "model": "llama3.2:1b"
        }
      }
    ],
    "total_count": 156,
    "has_more": true
  }
}
```

#### Delete Chat History
```http
DELETE /api/chat/history/conv_123
```

**Response:**
```json
{
  "success": true,
  "data": {
    "deleted_messages": 25,
    "conversation_id": "conv_123"
  },
  "message": "Chat history deleted successfully"
}
```

### 3. Knowledge Base

#### Search Knowledge Base
```http
POST /api/knowledge/search
Content-Type: application/json

{
  "query": "network security scanning tools",
  "limit": 10,
  "filters": {
    "document_type": ["research", "documentation"],
    "tags": ["security", "networking"],
    "date_range": {
      "start": "2024-01-01",
      "end": "2025-01-16"
    }
  },
  "options": {
    "include_metadata": true,
    "similarity_threshold": 0.7
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "results": [
      {
        "id": "doc_123",
        "content": "Nmap is a powerful network scanning tool that can discover hosts and services...",
        "similarity_score": 0.95,
        "metadata": {
          "title": "Network Scanning with Nmap",
          "source": "security_research",
          "tags": ["nmap", "security", "networking"],
          "created_at": "2024-12-15T14:30:00Z",
          "updated_at": "2025-01-10T09:15:00Z"
        }
      }
    ],
    "total_found": 47,
    "query_time": 0.156,
    "suggestions": ["vulnerability scanning", "port scanning", "network discovery"]
  }
}
```

#### Add Document to Knowledge Base
```http
POST /api/knowledge/documents
Content-Type: application/json

{
  "content": "This document contains information about Docker security best practices...",
  "metadata": {
    "title": "Docker Security Best Practices",
    "category": "security",
    "tags": ["docker", "containers", "security"],
    "source": "internal_documentation",
    "author": "security_team"
  },
  "options": {
    "auto_extract_entities": true,
    "generate_summary": true
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "document_id": "doc_456",
    "status": "indexed",
    "processing_time": 0.89,
    "extracted_entities": ["Docker", "containers", "security policies"],
    "generated_summary": "This document outlines essential security practices for Docker containers...",
    "embedding_created": true
  }
}
```

### 4. Workflow Orchestration

#### Execute Workflow
```http
POST /api/workflow/execute
Content-Type: application/json

{
  "user_message": "Research network security scanning tools and provide installation recommendations",
  "options": {
    "allow_system_commands": true,
    "require_approvals": true,
    "use_docker_sandbox": true,
    "max_execution_time": 1800
  },
  "context": {
    "user_role": "developer",
    "priority": "normal",
    "tags": ["research", "security"]
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "workflow_id": "wf_abc123",
    "status": "in_progress",
    "complexity": "complex",
    "estimated_duration": "5-10 minutes",
    "steps": [
      {
        "id": "step_1",
        "agent_type": "research",
        "action": "Research network security scanning tools",
        "status": "pending",
        "estimated_duration": "2-3 minutes"
      },
      {
        "id": "step_2",
        "agent_type": "knowledge_manager",
        "action": "Store research findings",
        "status": "pending",
        "dependencies": ["step_1"]
      }
    ],
    "approvals_required": 2,
    "created_at": "2025-01-16T10:30:00Z"
  }
}
```

#### Get Workflow Status
```http
GET /api/workflow/workflow/wf_abc123/status
```

**Response:**
```json
{
  "success": true,
  "data": {
    "workflow_id": "wf_abc123",
    "status": "completed",
    "progress": 100,
    "current_step": null,
    "completed_steps": 8,
    "total_steps": 8,
    "execution_time": 487.2,
    "result": {
      "summary": "Successfully researched and documented 5 network security scanning tools",
      "tools_found": ["nmap", "masscan", "zmap", "unicornscan", "hping3"],
      "documents_created": 3,
      "recommendations": [
        {
          "tool": "nmap",
          "recommendation": "Primary choice for comprehensive scanning",
          "installation": "apt-get install nmap"
        }
      ]
    },
    "metadata": {
      "agents_used": ["research", "knowledge_manager", "orchestrator"],
      "llm_requests": 12,
      "total_tokens": 3456
    }
  }
}
```

#### List Active Workflows
```http
GET /api/workflow/workflows?status=active&limit=10
```

**Response:**
```json
{
  "success": true,
  "data": {
    "workflows": [
      {
        "id": "wf_abc123",
        "status": "in_progress",
        "description": "Research network security tools",
        "progress": 60,
        "created_at": "2025-01-16T10:30:00Z",
        "estimated_completion": "2025-01-16T10:40:00Z"
      }
    ],
    "total_count": 3,
    "active_count": 2,
    "pending_approvals": 1
  }
}
```

#### Approve Workflow Step
```http
POST /api/workflow/workflow/wf_abc123/approve
Content-Type: application/json

{
  "step_id": "step_3",
  "approved": true,
  "comments": "Approved - proceed with installation",
  "user_role": "admin"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "workflow_id": "wf_abc123",
    "step_id": "step_3",
    "approval_status": "approved",
    "workflow_resumed": true,
    "next_step": "step_4"
  },
  "message": "Workflow step approved and execution resumed"
}
```

### 5. Enhanced Memory System

#### Store Memory
```http
POST /api/memory/store
Content-Type: application/json

{
  "content": "User prefers detailed explanations with code examples for Python topics",
  "memory_type": "preference",
  "context": {
    "user_id": "user_123",
    "conversation_id": "conv_456",
    "topic": "user_preferences"
  },
  "metadata": {
    "importance": "high",
    "tags": ["preferences", "python", "learning_style"],
    "expires_at": "2025-12-31T23:59:59Z"
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "memory_id": "mem_789",
    "stored_at": "2025-01-16T10:30:00Z",
    "embedding_created": true,
    "memory_type": "preference",
    "importance_score": 8.5
  }
}
```

#### Retrieve Memories
```http
POST /api/memory/retrieve
Content-Type: application/json

{
  "query": "user python preferences",
  "context": {
    "user_id": "user_123",
    "memory_types": ["preference", "episodic"]
  },
  "options": {
    "limit": 5,
    "similarity_threshold": 0.7,
    "include_expired": false
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "memories": [
      {
        "id": "mem_789",
        "content": "User prefers detailed explanations with code examples for Python topics",
        "memory_type": "preference",
        "similarity_score": 0.94,
        "importance_score": 8.5,
        "created_at": "2025-01-16T10:30:00Z",
        "context": {
          "user_id": "user_123",
          "topic": "user_preferences"
        }
      }
    ],
    "total_found": 3,
    "query_time": 0.078
  }
}
```

#### Memory Statistics
```http
GET /api/memory/stats
```

**Response:**
```json
{
  "success": true,
  "data": {
    "total_memories": 1247,
    "by_type": {
      "episodic": 856,
      "preference": 234,
      "semantic": 157
    },
    "recent_activity": {
      "last_24h": {
        "stored": 45,
        "retrieved": 189,
        "updated": 12
      }
    },
    "storage_info": {
      "database_size": "45.2MB",
      "embedding_count": 1247,
      "average_similarity": 0.73
    }
  }
}
```

### 6. Security Management

#### Get Security Status
```http
GET /api/security/status
```

**Response:**
```json
{
  "success": true,
  "data": {
    "security_enabled": true,
    "command_security_enabled": true,
    "docker_sandbox_enabled": true,
    "authentication_required": true,
    "pending_approvals": [
      {
        "approval_id": "app_123",
        "command": "sudo apt install nmap",
        "user": "developer_user",
        "risk_level": "medium",
        "requested_at": "2025-01-16T10:25:00Z"
      }
    ],
    "security_policies": {
      "max_approval_timeout": 300,
      "require_approval_for": ["sudo", "system_modify", "network_scan"],
      "blocked_commands": ["rm -rf /", "dd if=/dev/zero"]
    }
  }
}
```

#### Approve Command
```http
POST /api/security/approve-command
Content-Type: application/json

{
  "approval_id": "app_123",
  "approved": true,
  "comments": "Approved for security research purposes"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "approval_id": "app_123",
    "status": "approved",
    "command_executed": true,
    "execution_result": {
      "exit_code": 0,
      "output": "Reading package lists... Done\\nBuilding dependency tree... Done\\nnmap is already the newest version"
    }
  }
}
```

#### Get Security Audit Log
```http
GET /api/security/audit-log?limit=50&user=developer_user
```

**Response:**
```json
{
  "success": true,
  "data": {
    "audit_entries": [
      {
        "timestamp": "2025-01-16T10:30:00Z",
        "user": "developer_user",
        "action": "command_execution",
        "outcome": "approved",
        "details": {
          "command": "nmap -sS 192.168.1.0/24",
          "risk_level": "medium",
          "approval_id": "app_123"
        }
      }
    ],
    "total_entries": 245,
    "filters_applied": {
      "user": "developer_user",
      "limit": 50
    }
  }
}
```

### 7. Terminal & Command Execution

#### Create Terminal Session
```http
POST /api/terminal/session
Content-Type: application/json

{
  "session_type": "secure",
  "options": {
    "use_docker_sandbox": true,
    "audit_commands": true,
    "timeout": 3600
  },
  "user_context": {
    "role": "developer",
    "permissions": ["allow_shell_execute"]
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "session_id": "term_abc123",
    "websocket_url": "ws://localhost:8001/api/terminal/ws/term_abc123",
    "session_type": "secure",
    "created_at": "2025-01-16T10:30:00Z",
    "expires_at": "2025-01-16T11:30:00Z",
    "sandbox_info": {
      "container_id": "docker_xyz789",
      "image": "autobot-sandbox:latest"
    }
  }
}
```

#### Execute Command
```http
POST /api/terminal/execute
Content-Type: application/json

{
  "command": "ls -la /tmp",
  "options": {
    "timeout": 30,
    "capture_output": true,
    "use_sandbox": true
  },
  "session_id": "term_abc123"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "command": "ls -la /tmp",
    "exit_code": 0,
    "output": "total 12\\ndrwxrwxrwt 10 root root 4096 Jan 16 10:30 .\\ndrwxr-xr-x 20 root root 4096 Jan 15 08:00 ..\\n",
    "error": "",
    "execution_time": 0.045,
    "session_id": "term_abc123",
    "audit_logged": true
  }
}
```

## Advanced Features

### 8. Multi-Modal Processing

#### Process Multi-Modal Input
```http
POST /api/multimodal/process
Content-Type: application/json

{
  "input_data": {
    "modality_type": "combined",
    "processing_intent": "automation_task",
    "content": {
      "text": "Analyze this interface and click the submit button",
      "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEU...",
      "audio": "data:audio/wav;base64,UklGRnoGAABXQVZFZm10..."
    },
    "metadata": {
      "source": "user_interface",
      "session_id": "session_123"
    }
  }
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "processing_result": {
      "modality_type": "combined",
      "confidence": 0.92,
      "analysis": {
        "text_intent": "automation_request",
        "image_analysis": {
          "ui_elements": [
            {
              "type": "button",
              "text": "Submit",
              "confidence": 0.95,
              "bbox": [340, 450, 420, 480]
            }
          ],
          "automation_opportunities": [
            {
              "action": "click",
              "target": "submit_button",
              "confidence": 0.93
            }
          ]
        },
        "audio_analysis": {
          "transcription": "click submit button",
          "intent": "click_action",
          "confidence": 0.88
        }
      },
      "recommended_actions": [
        {
          "action": "click_element",
          "coordinates": [380, 465],
          "confidence": 0.91
        }
      ],
      "processing_time": 1.234
    }
  }
}
```

### 9. Voice Processing

#### Process Voice Command
```http
POST /api/voice/process
Content-Type: multipart/form-data

audio_file: [binary audio data]
options: {
  "language": "en-US",
  "format": "wav",
  "sample_rate": 16000,
  "intent_detection": true
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "transcription": "open the settings menu and change the theme to dark mode",
    "confidence": 0.94,
    "language_detected": "en-US",
    "intent_analysis": {
      "primary_intent": "navigation_and_configuration",
      "actions": [
        {
          "action": "navigate",
          "target": "settings_menu",
          "confidence": 0.92
        },
        {
          "action": "change_setting",
          "setting": "theme",
          "value": "dark_mode",
          "confidence": 0.89
        }
      ]
    },
    "processing_time": 0.756,
    "audio_metadata": {
      "duration": 3.2,
      "sample_rate": 16000,
      "channels": 1
    }
  }
}
```

### 10. NPU Acceleration

#### Get NPU Status
```http
GET /api/npu/status
```

**Response:**
```json
{
  "success": true,
  "data": {
    "npu_available": true,
    "npu_devices": [
      {
        "device_id": 0,
        "name": "Intel Neural Processing Unit",
        "driver_version": "1.2.3",
        "memory_total": "8GB",
        "memory_used": "2.1GB",
        "utilization": 34.5,
        "temperature": 45.2
      }
    ],
    "models_loaded": [
      {
        "model_name": "llama3.2:1b",
        "device_assignment": "npu",
        "optimization_level": "int8",
        "memory_usage": "1.2GB"
      }
    ],
    "performance_metrics": {
      "inference_speed": "125 tokens/sec",
      "power_consumption": "15W",
      "efficiency_score": 8.7
    }
  }
}
```

#### Optimize Model for NPU
```http
POST /api/npu/optimize
Content-Type: application/json

{
  "model_name": "llama3.2:3b",
  "optimization_options": {
    "precision": "int8",
    "batch_size": 1,
    "max_sequence_length": 2048
  },
  "target_device": "npu"
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "optimization_id": "opt_456",
    "status": "completed",
    "optimized_model": {
      "name": "llama3.2:3b-npu-int8",
      "size_original": "5.4GB",
      "size_optimized": "2.1GB",
      "compression_ratio": 2.57,
      "performance_improvement": {
        "inference_speed": "2.3x faster",
        "memory_usage": "61% reduction",
        "power_efficiency": "40% improvement"
      }
    },
    "optimization_time": 145.7
  }
}
```

## WebSocket APIs

### Real-Time Chat
```javascript
// Connection
const ws = new WebSocket('ws://localhost:8001/api/chat/ws');

// Send message
ws.send(JSON.stringify({
  type: 'message',
  data: {
    content: 'Hello, AutoBot!',
    conversation_id: 'conv_123'
  }
}));

// Receive response
ws.onmessage = (event) => {
  const response = JSON.parse(event.data);
  console.log('Type:', response.type);
  console.log('Data:', response.data);
};
```

**Message Types:**
- `message`: User message
- `response`: AI response
- `typing`: Typing indicator
- `status`: Connection status
- `error`: Error message

### Terminal WebSocket
```javascript
// Connection with session
const termWs = new WebSocket('ws://localhost:8001/api/terminal/ws/term_abc123?role=developer');

// Send command
termWs.send(JSON.stringify({
  type: 'input',
  data: 'ls -la\n'
}));

// Receive output
termWs.onmessage = (event) => {
  const message = JSON.parse(event.data);
  if (message.type === 'output') {
    console.log(message.data);
  }
};
```

### Workflow Progress WebSocket
```javascript
// Monitor workflow progress
const workflowWs = new WebSocket('ws://localhost:8001/api/workflow/ws/wf_abc123');

workflowWs.onmessage = (event) => {
  const update = JSON.parse(event.data);
  switch (update.type) {
    case 'step_started':
      console.log('Step started:', update.data.step_id);
      break;
    case 'step_completed':
      console.log('Step completed:', update.data.result);
      break;
    case 'approval_required':
      console.log('Approval needed:', update.data.approval_id);
      break;
    case 'workflow_completed':
      console.log('Workflow finished:', update.data.summary);
      break;
  }
};
```

## Rate Limiting

### Rate Limits by Endpoint

| Endpoint Category | Rate Limit | Window |
|------------------|------------|--------|
| Authentication | 10 requests | 15 minutes |
| Chat Messages | 60 requests | 1 minute |
| Knowledge Search | 30 requests | 1 minute |
| Workflow Execution | 10 requests | 5 minutes |
| System Commands | 20 requests | 1 minute |
| File Operations | 50 requests | 1 minute |

### Rate Limit Headers
```http
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 45
X-RateLimit-Reset: 1642334400
X-RateLimit-Retry-After: 15
```

## Examples

### Complete Workflow Example

```bash
# 1. Get system health
curl -X GET "http://localhost:8001/api/system/health"

# 2. Start chat conversation
curl -X POST "http://localhost:8001/api/chat/message" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Research network security tools and create installation guide",
    "context": {"conversation_id": "conv_123"}
  }'

# 3. Execute workflow
curl -X POST "http://localhost:8001/api/workflow/execute" \
  -H "Content-Type: application/json" \
  -d '{
    "user_message": "Research network security scanning tools",
    "options": {"require_approvals": true}
  }'

# 4. Monitor workflow progress
curl -X GET "http://localhost:8001/api/workflow/workflow/wf_abc123/status"

# 5. Approve workflow step
curl -X POST "http://localhost:8001/api/workflow/workflow/wf_abc123/approve" \
  -H "Content-Type: application/json" \
  -d '{
    "step_id": "step_3",
    "approved": true
  }'

# 6. Get final results
curl -X GET "http://localhost:8001/api/workflow/workflow/wf_abc123/status"
```

### Python Client Example

```python
import requests
import websocket
import json

class AutoBotClient:
    def __init__(self, base_url="http://localhost:8001"):
        self.base_url = base_url
        self.session = requests.Session()

    def send_message(self, message, conversation_id=None):
        """Send a chat message"""
        payload = {"message": message}
        if conversation_id:
            payload["context"] = {"conversation_id": conversation_id}

        response = self.session.post(
            f"{self.base_url}/api/chat/message",
            json=payload
        )
        return response.json()

    def execute_workflow(self, user_message, **options):
        """Execute a workflow"""
        payload = {
            "user_message": user_message,
            "options": options
        }

        response = self.session.post(
            f"{self.base_url}/api/workflow/execute",
            json=payload
        )
        return response.json()

    def get_workflow_status(self, workflow_id):
        """Get workflow status"""
        response = self.session.get(
            f"{self.base_url}/api/workflow/workflow/{workflow_id}/status"
        )
        return response.json()

    def search_knowledge(self, query, **filters):
        """Search knowledge base"""
        payload = {"query": query, "filters": filters}

        response = self.session.post(
            f"{self.base_url}/api/knowledge/search",
            json=payload
        )
        return response.json()

# Usage example
client = AutoBotClient()

# Send a message
response = client.send_message("Hello, AutoBot!")
print(f"Response: {response['data']['response']}")

# Execute workflow
workflow = client.execute_workflow(
    "Research Docker security best practices",
    require_approvals=True,
    use_docker_sandbox=True
)
print(f"Workflow ID: {workflow['data']['workflow_id']}")

# Monitor progress
status = client.get_workflow_status(workflow['data']['workflow_id'])
print(f"Status: {status['data']['status']}")
```

### JavaScript/Node.js Example

```javascript
const axios = require('axios');
const WebSocket = require('ws');

class AutoBotClient {
  constructor(baseUrl = 'http://localhost:8001') {
    this.baseUrl = baseUrl;
    this.axios = axios.create({ baseURL: baseUrl });
  }

  async sendMessage(message, conversationId) {
    const payload = { message };
    if (conversationId) {
      payload.context = { conversation_id: conversationId };
    }

    const response = await this.axios.post('/api/chat/message', payload);
    return response.data;
  }

  async executeWorkflow(userMessage, options = {}) {
    const payload = {
      user_message: userMessage,
      options: options
    };

    const response = await this.axios.post('/api/workflow/execute', payload);
    return response.data;
  }

  connectChatWebSocket(onMessage) {
    const ws = new WebSocket(`${this.baseUrl.replace('http', 'ws')}/api/chat/ws`);

    ws.on('message', (data) => {
      const message = JSON.parse(data);
      onMessage(message);
    });

    return ws;
  }

  async searchKnowledge(query, filters = {}) {
    const payload = { query, filters };
    const response = await this.axios.post('/api/knowledge/search', payload);
    return response.data;
  }
}

// Usage example
async function example() {
  const client = new AutoBotClient();

  try {
    // Send message
    const chatResponse = await client.sendMessage('Hello AutoBot!');
    console.log('Chat response:', chatResponse.data.response);

    // Execute workflow
    const workflow = await client.executeWorkflow(
      'Analyze system security and provide recommendations',
      { require_approvals: true }
    );
    console.log('Workflow started:', workflow.data.workflow_id);

    // Connect to WebSocket for real-time updates
    const ws = client.connectChatWebSocket((message) => {
      console.log('WebSocket message:', message);
    });

    // Search knowledge base
    const searchResults = await client.searchKnowledge(
      'security best practices',
      { document_type: ['documentation', 'research'] }
    );
    console.log('Found documents:', searchResults.data.results.length);

  } catch (error) {
    console.error('Error:', error.response?.data || error.message);
  }
}

example();
```

---

## Support

For additional help:
- **Documentation**: [Full Documentation](../README.md)
- **Issues**: [GitHub Issues](https://github.com/your-org/autobot/issues)
- **Community**: [Discord Server](https://discord.gg/autobot)

**Last Updated**: 2025-01-16
**API Version**: v1
**Documentation Version**: 2.0
