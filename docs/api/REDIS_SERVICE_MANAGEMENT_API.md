# Redis Service Management API Documentation

**Version:** 1.0
**Last Updated:** 2025-10-10
**Status:** Production Ready

---

## Table of Contents

1. [Overview](#overview)
2. [Authentication & Authorization](#authentication--authorization)
3. [API Endpoints](#api-endpoints)
4. [Request/Response Examples](#requestresponse-examples)
5. [Error Handling](#error-handling)
6. [Rate Limiting](#rate-limiting)
7. [WebSocket Events](#websocket-events)
8. [Security Considerations](#security-considerations)

---

## Overview

The Redis Service Management API provides comprehensive control over the Redis service running on VM3 (172.16.168.23:6379) within AutoBot's distributed infrastructure. This API enables:

- **Service Control**: Start, stop, restart Redis service
- **Health Monitoring**: Real-time health checks and status reporting
- **Auto-Recovery**: Automated failure detection and recovery
- **Audit Logging**: Complete audit trail of all operations
- **Real-Time Updates**: WebSocket notifications for status changes

### Base URL

```
http://172.16.168.20:8001/api/services/redis
```

### API Versioning

This is version 1.0 of the Redis Service Management API. Future versions will use URL versioning (e.g., `/api/v2/services/redis`).

---

## Authentication & Authorization

### Authentication Methods

**Primary: JWT Bearer Token**

All authenticated endpoints require a valid JWT token in the Authorization header:

```http
Authorization: Bearer <your_jwt_token>
```

**Session-Based Authentication (Fallback)**

Session cookies are accepted as an alternative authentication method.

### Role-Based Access Control (RBAC)

Operations are restricted based on user roles:

| Role | Start Service | Restart Service | Stop Service | View Status | View Logs |
|------|--------------|----------------|--------------|-------------|-----------|
| **Admin** | ✓ | ✓ | ✓ | ✓ | ✓ |
| **Operator** | ✓ | ✓ | ✗ | ✓ | ✗ |
| **Viewer** | ✗ | ✗ | ✗ | ✓ | ✗ |
| **Anonymous** | ✗ | ✗ | ✗ | ✓ (limited) | ✗ |

---

## API Endpoints

### 1. Start Redis Service

**Endpoint:** `POST /api/services/redis/start`

**Description:** Starts the Redis service if it's currently stopped or failed.

**Authentication:** Required (Bearer token)

**Authorization:** `admin`, `operator` roles

**Request Body:** Empty

**Response Codes:**
- `200 OK` - Service started successfully or already running
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions
- `500 Internal Server Error` - Service start failed

**Response Schema:**

```json
{
  "success": boolean,
  "operation": "start",
  "message": string,
  "duration_seconds": number,
  "timestamp": string (ISO 8601),
  "new_status": "running" | "stopped" | "failed"
}
```

**Example Request:**

```bash
curl -X POST \
  http://172.16.168.20:8001/api/services/redis/start \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response (Success):**

```json
{
  "success": true,
  "operation": "start",
  "message": "Redis service started successfully",
  "duration_seconds": 12.5,
  "timestamp": "2025-10-10T14:30:00Z",
  "new_status": "running"
}
```

**Example Response (Already Running):**

```json
{
  "success": true,
  "operation": "start",
  "message": "Redis service already running",
  "duration_seconds": 0.5,
  "timestamp": "2025-10-10T14:30:00Z",
  "new_status": "running"
}
```

---

### 2. Stop Redis Service

**Endpoint:** `POST /api/services/redis/stop`

**Description:** Stops the Redis service. Requires explicit confirmation due to impact on dependent services.

**Authentication:** Required (Bearer token)

**Authorization:** `admin` role only

**Request Body:**

```json
{
  "confirmation": boolean (required)
}
```

**Response Codes:**
- `200 OK` - Service stopped successfully
- `400 Bad Request` - Confirmation not provided
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions (non-admin)
- `500 Internal Server Error` - Service stop failed

**Response Schema:**

```json
{
  "success": boolean,
  "operation": "stop",
  "message": string,
  "duration_seconds": number,
  "timestamp": string (ISO 8601),
  "new_status": "stopped" | "failed",
  "warning": string (optional)
}
```

**Example Request:**

```bash
curl -X POST \
  http://172.16.168.20:8001/api/services/redis/stop \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirmation": true}'
```

**Example Response (Success):**

```json
{
  "success": true,
  "operation": "stop",
  "message": "Redis service stopped successfully",
  "duration_seconds": 8.3,
  "timestamp": "2025-10-10T14:30:00Z",
  "new_status": "stopped",
  "warning": "All Redis-dependent services may be affected"
}
```

**Example Response (Confirmation Required):**

```json
{
  "error": "Confirmation required to stop Redis service",
  "message": "Stopping Redis will affect all dependent services",
  "affected_services": ["backend", "knowledge_base", "cache"],
  "confirmation_required": true
}
```

---

### 3. Restart Redis Service

**Endpoint:** `POST /api/services/redis/restart`

**Description:** Restarts the Redis service. Temporarily interrupts connections during restart.

**Authentication:** Required (Bearer token)

**Authorization:** `admin`, `operator` roles

**Request Body:** Empty

**Response Codes:**
- `200 OK` - Service restarted successfully
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions
- `500 Internal Server Error` - Service restart failed

**Response Schema:**

```json
{
  "success": boolean,
  "operation": "restart",
  "message": string,
  "duration_seconds": number,
  "timestamp": string (ISO 8601),
  "new_status": "running" | "failed",
  "previous_uptime_seconds": number (optional),
  "connections_terminated": number (optional)
}
```

**Example Request:**

```bash
curl -X POST \
  http://172.16.168.20:8001/api/services/redis/restart \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response (Success):**

```json
{
  "success": true,
  "operation": "restart",
  "message": "Redis service restarted successfully",
  "duration_seconds": 15.7,
  "timestamp": "2025-10-10T14:30:00Z",
  "new_status": "running",
  "previous_uptime_seconds": 86400,
  "connections_terminated": 42
}
```

---

### 4. Get Service Status

**Endpoint:** `GET /api/services/redis/status`

**Description:** Retrieves current Redis service status and basic metrics.

**Authentication:** Optional (public endpoint with limited data for unauthenticated requests)

**Authorization:** All roles (including anonymous)

**Request Body:** None

**Query Parameters:** None

**Response Codes:**
- `200 OK` - Status retrieved successfully
- `503 Service Unavailable` - Unable to determine status (VM unreachable)

**Response Schema:**

```json
{
  "status": "running" | "stopped" | "failed" | "unknown",
  "pid": number | null,
  "uptime_seconds": number | null,
  "memory_mb": number | null,
  "connections": number | null,
  "commands_processed": number | null,
  "last_check": string (ISO 8601),
  "vm_info": {
    "host": string,
    "name": string,
    "ssh_accessible": boolean
  }
}
```

**Example Request:**

```bash
curl -X GET \
  http://172.16.168.20:8001/api/services/redis/status
```

**Example Response (Running):**

```json
{
  "status": "running",
  "pid": 12345,
  "uptime_seconds": 86400,
  "memory_mb": 128.5,
  "connections": 42,
  "commands_processed": 1000000,
  "last_check": "2025-10-10T14:30:00Z",
  "vm_info": {
    "host": "172.16.168.23",
    "name": "Redis VM",
    "ssh_accessible": true
  }
}
```

**Example Response (Stopped):**

```json
{
  "status": "stopped",
  "pid": null,
  "uptime_seconds": null,
  "memory_mb": null,
  "connections": null,
  "last_check": "2025-10-10T14:30:00Z",
  "vm_info": {
    "host": "172.16.168.23",
    "name": "Redis VM",
    "ssh_accessible": true
  }
}
```

---

### 5. Get Health Status

**Endpoint:** `GET /api/services/redis/health`

**Description:** Performs comprehensive health check and returns detailed health information.

**Authentication:** Optional (public endpoint)

**Authorization:** All roles

**Request Body:** None

**Query Parameters:** None

**Response Codes:**
- `200 OK` - Health check completed (regardless of health status)

**Response Schema:**

```json
{
  "overall_status": "healthy" | "degraded" | "critical" | "unknown",
  "service_running": boolean,
  "connectivity": boolean,
  "response_time_ms": number | null,
  "last_successful_command": string (ISO 8601) | null,
  "error_count_last_hour": number,
  "health_checks": {
    "connectivity": {
      "status": "pass" | "fail" | "unknown",
      "duration_ms": number,
      "message": string,
      "error": string (optional)
    },
    "systemd": {
      "status": "pass" | "fail" | "unknown",
      "duration_ms": number,
      "message": string,
      "details": string (optional)
    },
    "performance": {
      "status": "pass" | "warning" | "fail" | "unknown",
      "duration_ms": number,
      "message": string,
      "metrics": {
        "memory_usage_mb": number,
        "memory_limit_mb": number,
        "cpu_usage_percent": number,
        "connections": number,
        "max_connections": number
      }
    }
  },
  "recommendations": string[],
  "auto_recovery": {
    "enabled": boolean,
    "recent_recoveries": number,
    "last_recovery": string (ISO 8601) | null,
    "recovery_status": "success" | "failed" | null,
    "requires_manual_intervention": boolean
  }
}
```

**Example Request:**

```bash
curl -X GET \
  http://172.16.168.20:8001/api/services/redis/health
```

**Example Response (Healthy):**

```json
{
  "overall_status": "healthy",
  "service_running": true,
  "connectivity": true,
  "response_time_ms": 2.5,
  "last_successful_command": "2025-10-10T14:29:55Z",
  "error_count_last_hour": 0,
  "health_checks": {
    "connectivity": {
      "status": "pass",
      "duration_ms": 2.5,
      "message": "PING successful"
    },
    "systemd": {
      "status": "pass",
      "duration_ms": 50.0,
      "message": "Service active and running"
    },
    "performance": {
      "status": "pass",
      "duration_ms": 15.0,
      "message": "All metrics within normal ranges",
      "metrics": {
        "memory_usage_mb": 128.5,
        "memory_limit_mb": 4096.0,
        "cpu_usage_percent": 5.2,
        "connections": 42,
        "max_connections": 10000
      }
    }
  },
  "recommendations": [],
  "auto_recovery": {
    "enabled": true,
    "recent_recoveries": 0,
    "last_recovery": null
  }
}
```

**Example Response (Critical):**

```json
{
  "overall_status": "critical",
  "service_running": false,
  "connectivity": false,
  "response_time_ms": null,
  "last_successful_command": "2025-10-10T14:15:00Z",
  "error_count_last_hour": 20,
  "health_checks": {
    "connectivity": {
      "status": "fail",
      "duration_ms": 5000.0,
      "message": "Connection timeout",
      "error": "Connection refused"
    },
    "systemd": {
      "status": "fail",
      "duration_ms": 50.0,
      "message": "Service failed",
      "details": "Exit code: 1"
    },
    "performance": {
      "status": "unknown",
      "duration_ms": 0,
      "message": "Cannot collect metrics - service not running"
    }
  },
  "recommendations": [
    "Check service logs for errors",
    "Verify system resources",
    "Consider manual intervention"
  ],
  "auto_recovery": {
    "enabled": true,
    "recent_recoveries": 3,
    "last_recovery": "2025-10-10T14:20:00Z",
    "recovery_status": "failed",
    "requires_manual_intervention": true
  }
}
```

---

### 6. Get Service Logs

**Endpoint:** `GET /api/services/redis/logs`

**Description:** Retrieves recent Redis service logs from systemd journal.

**Authentication:** Required (Bearer token)

**Authorization:** `admin` role only

**Request Body:** None

**Query Parameters:**
- `lines` (optional, default: 50) - Number of log lines to retrieve (1-1000)
- `since` (optional) - ISO 8601 timestamp to get logs since
- `level` (optional) - Filter by log level: `error`, `warning`, `info`

**Response Codes:**
- `200 OK` - Logs retrieved successfully
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions (non-admin)
- `500 Internal Server Error` - Failed to retrieve logs

**Response Schema:**

```json
{
  "logs": [
    {
      "timestamp": string (ISO 8601),
      "level": "error" | "warning" | "info",
      "message": string
    }
  ],
  "total_lines": number,
  "service": "redis-server",
  "vm": string
}
```

**Example Request:**

```bash
curl -X GET \
  "http://172.16.168.20:8001/api/services/redis/logs?lines=20&level=error" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**Example Response:**

```json
{
  "logs": [
    {
      "timestamp": "2025-10-10T14:29:55Z",
      "level": "info",
      "message": "DB saved on disk"
    },
    {
      "timestamp": "2025-10-10T14:29:50Z",
      "level": "info",
      "message": "Background saving started by pid 12346"
    },
    {
      "timestamp": "2025-10-10T14:25:00Z",
      "level": "warning",
      "message": "Memory usage approaching threshold: 3500 MB"
    }
  ],
  "total_lines": 20,
  "service": "redis-server",
  "vm": "172.16.168.23"
}
```

---

## Request/Response Examples

### Complete cURL Examples

#### Start Service (Authenticated)

```bash
# Start Redis service as operator
curl -X POST \
  http://172.16.168.20:8001/api/services/redis/start \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json"
```

#### Stop Service (Admin Only)

```bash
# Stop Redis service with confirmation
curl -X POST \
  http://172.16.168.20:8001/api/services/redis/stop \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json" \
  -d '{
    "confirmation": true
  }'
```

#### Restart Service

```bash
# Restart Redis service
curl -X POST \
  http://172.16.168.20:8001/api/services/redis/restart \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -H "Content-Type: application/json"
```

#### Get Status (Public)

```bash
# Get current status (no authentication required)
curl -X GET \
  http://172.16.168.20:8001/api/services/redis/status
```

#### Get Health (Public)

```bash
# Get detailed health status
curl -X GET \
  http://172.16.168.20:8001/api/services/redis/health
```

#### Get Logs (Admin)

```bash
# Get last 100 error logs
curl -X GET \
  "http://172.16.168.20:8001/api/services/redis/logs?lines=100&level=error" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

### Python Client Example

```python
import requests
from typing import Dict, Any

class RedisServiceClient:
    """Python client for Redis Service Management API"""

    def __init__(self, base_url: str, api_token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {api_token}',
            'Content-Type': 'application/json'
        }

    def start_service(self) -> Dict[str, Any]:
        """Start Redis service"""
        response = requests.post(
            f'{self.base_url}/api/services/redis/start',
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def stop_service(self, confirmation: bool = True) -> Dict[str, Any]:
        """Stop Redis service"""
        response = requests.post(
            f'{self.base_url}/api/services/redis/stop',
            headers=self.headers,
            json={'confirmation': confirmation}
        )
        response.raise_for_status()
        return response.json()

    def restart_service(self) -> Dict[str, Any]:
        """Restart Redis service"""
        response = requests.post(
            f'{self.base_url}/api/services/redis/restart',
            headers=self.headers
        )
        response.raise_for_status()
        return response.json()

    def get_status(self) -> Dict[str, Any]:
        """Get service status"""
        response = requests.get(
            f'{self.base_url}/api/services/redis/status'
        )
        response.raise_for_status()
        return response.json()

    def get_health(self) -> Dict[str, Any]:
        """Get health status"""
        response = requests.get(
            f'{self.base_url}/api/services/redis/health'
        )
        response.raise_for_status()
        return response.json()

    def get_logs(self, lines: int = 50, level: str = None) -> Dict[str, Any]:
        """Get service logs"""
        params = {'lines': lines}
        if level:
            params['level'] = level

        response = requests.get(
            f'{self.base_url}/api/services/redis/logs',
            headers=self.headers,
            params=params
        )
        response.raise_for_status()
        return response.json()


# Usage example
client = RedisServiceClient(
    base_url='http://172.16.168.20:8001',
    api_token='your_jwt_token_here'
)

# Get current status
status = client.get_status()
print(f"Redis status: {status['status']}")

# Restart service if needed
if status['status'] == 'failed':
    result = client.restart_service()
    print(f"Restart result: {result['message']}")
```

---

## Error Handling

### Standard Error Response Format

All API errors follow this consistent format:

```json
{
  "error": string,
  "message": string,
  "details": object (optional),
  "timestamp": string (ISO 8601)
}
```

### Common Error Codes

#### 400 Bad Request

**Cause:** Invalid request parameters or missing required fields

**Example:**

```json
{
  "error": "Confirmation required to stop Redis service",
  "message": "Stopping Redis will affect all dependent services",
  "affected_services": ["backend", "knowledge_base", "cache"],
  "confirmation_required": true,
  "timestamp": "2025-10-10T14:30:00Z"
}
```

#### 401 Unauthorized

**Cause:** Missing or invalid authentication token

**Example:**

```json
{
  "error": "Invalid authentication credentials",
  "message": "The provided JWT token is expired or invalid",
  "timestamp": "2025-10-10T14:30:00Z"
}
```

#### 403 Forbidden

**Cause:** User lacks required permissions for operation

**Example:**

```json
{
  "error": "Insufficient permissions",
  "message": "User role 'operator' cannot stop Redis service. Required role: admin",
  "required_roles": ["admin"],
  "user_role": "operator",
  "timestamp": "2025-10-10T14:30:00Z"
}
```

#### 500 Internal Server Error

**Cause:** Service operation failed or system error

**Example:**

```json
{
  "error": "Service operation failed",
  "message": "Failed to start Redis service",
  "details": {
    "exit_code": 1,
    "stderr": "Job for redis-server.service failed",
    "command": "sudo systemctl start redis-server"
  },
  "timestamp": "2025-10-10T14:30:00Z"
}
```

#### 503 Service Unavailable

**Cause:** Cannot reach Redis VM or determine service status

**Example:**

```json
{
  "error": "Redis VM unreachable",
  "message": "Cannot establish SSH connection to Redis VM",
  "details": {
    "host": "172.16.168.23",
    "error": "Connection timeout after 10 seconds"
  },
  "timestamp": "2025-10-10T14:30:00Z"
}
```

---

## Rate Limiting

### Rate Limit Configuration

To prevent abuse and ensure system stability, the following rate limits apply:

| Endpoint | Rate Limit | Window | Scope |
|----------|-----------|--------|-------|
| Start Service | 10 requests | 1 minute | Per user |
| Stop Service | 5 requests | 1 minute | Per user |
| Restart Service | 10 requests | 1 minute | Per user |
| Get Status | 60 requests | 1 minute | Per user |
| Get Health | 60 requests | 1 minute | Per user |
| Get Logs | 20 requests | 1 minute | Per user |

### Rate Limit Headers

Rate limit information is included in response headers:

```http
X-RateLimit-Limit: 10
X-RateLimit-Remaining: 7
X-RateLimit-Reset: 1696950000
```

### Rate Limit Exceeded Response

**HTTP Status:** `429 Too Many Requests`

```json
{
  "error": "Rate limit exceeded",
  "message": "Too many requests. Please wait before retrying.",
  "retry_after_seconds": 45,
  "limit": 10,
  "window_seconds": 60,
  "timestamp": "2025-10-10T14:30:00Z"
}
```

---

## WebSocket Events

### WebSocket Connection

**Endpoint:** `ws://172.16.168.20:8001/ws/services/redis/status`

**Authentication:** Required (JWT token in URL parameter or header)

**Connection Example:**

```javascript
// JavaScript WebSocket connection
const token = 'your_jwt_token_here';
const ws = new WebSocket(
  `ws://172.16.168.20:8001/ws/services/redis/status?token=${token}`
);

ws.onopen = () => {
  console.log('Connected to Redis service status updates');
};

ws.onmessage = (event) => {
  const message = JSON.parse(event.data);
  console.log('Status update:', message);

  switch(message.type) {
    case 'service_status':
      handleStatusUpdate(message);
      break;
    case 'service_event':
      handleServiceEvent(message);
      break;
    case 'auto_recovery':
      handleAutoRecovery(message);
      break;
  }
};

ws.onerror = (error) => {
  console.error('WebSocket error:', error);
};

ws.onclose = () => {
  console.log('Disconnected from Redis service updates');
};
```

### Event Message Types

#### 1. Service Status Update

**Type:** `service_status`

**Description:** Periodic status updates (every 30 seconds) or immediate updates after status changes

**Message Format:**

```json
{
  "type": "service_status",
  "service": "redis",
  "status": "running" | "stopped" | "failed" | "unknown",
  "timestamp": string (ISO 8601),
  "details": {
    "pid": number | null,
    "connections": number | null,
    "memory_mb": number | null,
    "uptime_seconds": number | null
  }
}
```

#### 2. Service Event

**Type:** `service_event`

**Description:** Notification when a service operation (start/stop/restart) is performed

**Message Format:**

```json
{
  "type": "service_event",
  "service": "redis",
  "event": "start" | "stop" | "restart",
  "user": string,
  "timestamp": string (ISO 8601),
  "result": "success" | "failure",
  "message": string (optional),
  "duration_seconds": number (optional)
}
```

#### 3. Auto-Recovery Event

**Type:** `auto_recovery`

**Description:** Notification when auto-recovery system detects and attempts to fix a failure

**Message Format:**

```json
{
  "type": "auto_recovery",
  "service": "redis",
  "recovery_level": "soft" | "standard" | "hard" | "critical",
  "status": "started" | "success" | "failed",
  "timestamp": string (ISO 8601),
  "message": string,
  "attempt_number": number (optional),
  "requires_manual_intervention": boolean (optional)
}
```

### WebSocket Example: React Hook

```javascript
import { useEffect, useState } from 'react';

function useRedisServiceStatus(token) {
  const [status, setStatus] = useState(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const ws = new WebSocket(
      `ws://172.16.168.20:8001/ws/services/redis/status?token=${token}`
    );

    ws.onopen = () => {
      setConnected(true);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      if (message.type === 'service_status') {
        setStatus({
          status: message.status,
          ...message.details,
          lastUpdate: message.timestamp
        });
      }
    };

    ws.onclose = () => {
      setConnected(false);
    };

    return () => {
      ws.close();
    };
  }, [token]);

  return { status, connected };
}

// Usage in component
function RedisStatusMonitor() {
  const { status, connected } = useRedisServiceStatus(userToken);

  return (
    <div>
      <span>Connection: {connected ? 'Connected' : 'Disconnected'}</span>
      {status && (
        <div>
          <p>Status: {status.status}</p>
          <p>Memory: {status.memory_mb} MB</p>
          <p>Connections: {status.connections}</p>
        </div>
      )}
    </div>
  );
}
```

---

## Security Considerations

### Command Validation

All service commands are validated using a strict whitelist:

```python
ALLOWED_REDIS_COMMANDS = {
    "start": "sudo systemctl start redis-server",
    "stop": "sudo systemctl stop redis-server",
    "restart": "sudo systemctl restart redis-server",
    "status": "systemctl status redis-server",
    "is-active": "systemctl is-active redis-server",
    "logs": "journalctl -u redis-server -n {lines}",
}
```

No arbitrary commands are allowed. Command injection attacks are prevented by:
1. Whitelist-only command execution
2. Input sanitization for all parameters
3. SecureCommandExecutor risk assessment

### SSH Security

- **Authentication:** SSH key-based only (no passwords)
- **Key Size:** 4096-bit RSA minimum
- **User:** Dedicated `autobot` service account with limited sudo permissions
- **Permissions:** Defined in `/etc/sudoers.d/autobot-redis` on Redis VM

### Audit Logging

All operations are logged with:
- User identity (ID, email, role)
- Source IP address
- Timestamp
- Operation performed
- Result (success/failure)
- Command executed
- Duration

Audit logs are stored in: `/home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log`

### Best Practices

1. **Use HTTPS in production** - Encrypt all API traffic
2. **Rotate JWT tokens regularly** - Implement token expiration
3. **Monitor audit logs** - Review for suspicious activity
4. **Limit stop operations** - Only admin users can stop service
5. **Require confirmation for destructive actions** - Stop operations need explicit confirmation
6. **Use rate limiting** - Prevent abuse and accidental DoS
7. **Monitor auto-recovery attempts** - Alert on repeated failures

---

## Appendix: API Change Log

### Version 1.0 (2025-10-10)

- Initial release of Redis Service Management API
- Endpoints: start, stop, restart, status, health, logs
- WebSocket real-time updates
- Auto-recovery system integration
- RBAC implementation
- Rate limiting
- Comprehensive error handling

---

## Support & Resources

**Documentation:**
- [User Guide](/home/kali/Desktop/AutoBot/docs/user-guides/REDIS_SERVICE_MANAGEMENT_GUIDE.md)
- [Operational Runbook](/home/kali/Desktop/AutoBot/docs/operations/REDIS_SERVICE_RUNBOOK.md)
- [Architecture Document](/home/kali/Desktop/AutoBot/docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md)

**Related APIs:**
- [Comprehensive API Documentation](/home/kali/Desktop/AutoBot/docs/api/comprehensive_api_documentation.md)
- [Health Monitoring API](/home/kali/Desktop/AutoBot/docs/api/health_monitoring.md)

**Contact:**
- GitHub Issues: [AutoBot Issues](https://github.com/autobot/autobot/issues)
- Email: support@autobot.local

---

**Document Version:** 1.0
**Last Updated:** 2025-10-10
**Maintained By:** AutoBot Documentation Team
