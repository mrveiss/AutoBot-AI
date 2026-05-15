# SLM Server API Endpoints

This document describes all API endpoints available in the Service Lifecycle Manager (SLM) server.

## Base URL

```
http://<slm-server>:8080/api
```

## Authentication

All endpoints (except `/health`) require JWT authentication. Include the token in the `Authorization` header:

```
Authorization: Bearer <token>
```

## Endpoints

### Health & Status

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "uptime_seconds": 3600.5,
  "database": "connected",
  "nodes_online": 5,
  "nodes_total": 10
}
```

---

### Authentication

#### POST /auth/token
Login and obtain JWT token.

**Request:**
```json
{
  "username": "admin",
  "password": "admin"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

---

### Node Management

#### GET /nodes
List all registered nodes with optional filtering.

**Query Parameters:**
- `status` (optional): Filter by status (pending, enrolling, online, degraded, offline, error, maintenance)
- `page` (default: 1): Page number
- `per_page` (default: 20, max: 100): Results per page

**Response:**
```json
{
  "nodes": [
    {
      "id": 1,
      "node_id": "abc123",
      "hostname": "vm-frontend",
      "ip_address": "172.16.168.21",
      "status": "online",
      "roles": ["frontend", "nginx"],
      "ssh_user": "autobot",
      "ssh_port": 22,
      "auth_method": "password",
      "cpu_percent": 45.2,
      "memory_percent": 62.1,
      "disk_percent": 35.8,
      "last_heartbeat": "2026-01-15T12:34:56",
      "agent_version": "1.0.0",
      "os_info": "Linux 5.15.0-91-generic x86_64",
      "created_at": "2026-01-15T10:00:00",
      "updated_at": "2026-01-15T12:34:56"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 20
}
```

#### POST /nodes
Register a new node.

**Request:**
```json
{
  "hostname": "vm-frontend",
  "ip_address": "172.16.168.21",
  "roles": ["frontend", "nginx"],
  "ssh_user": "autobot",
  "ssh_port": 22,
  "ssh_password": "optional_password"
}
```

**Response:** Node object (see GET /nodes)

#### GET /nodes/{node_id}
Get details of a specific node.

**Response:** Node object (see GET /nodes)

#### PATCH /nodes/{node_id}
Update node configuration.

**Request:**
```json
{
  "hostname": "new-hostname",
  "status": "maintenance",
  "roles": ["frontend", "nginx", "monitoring"]
}
```

**Response:** Updated node object

#### DELETE /nodes/{node_id}
Delete a node registration.

**Response:** 204 No Content

#### POST /nodes/{node_id}/heartbeat
Receive heartbeat from node agent (no auth required for agents).

**Request:**
```json
{
  "cpu_percent": 45.2,
  "memory_percent": 62.1,
  "disk_percent": 35.8,
  "agent_version": "1.0.0",
  "os_info": "Linux 5.15.0-91-generic x86_64",
  "extra_data": {}
}
```

**Response:** Node object

#### POST /nodes/{node_id}/enroll
Start node enrollment process.

**Response:** Node object with status updated to "enrolling"

---

### SSH Connection Testing

#### POST /nodes/test-connection
Test SSH connection to a host before registering.

**Request:**
```json
{
  "ip_address": "172.16.168.21",
  "ssh_user": "autobot",
  "ssh_port": 22,
  "ssh_password": "optional_password"
}
```

**Response:**
```json
{
  "success": true,
  "message": "SSH connection successful",
  "os_info": "Linux 5.15.0-91-generic x86_64",
  "connection_time_ms": 234.5
}
```

**Error Response:**
```json
{
  "success": false,
  "message": "Authentication failed - invalid credentials",
  "os_info": null,
  "connection_time_ms": null
}
```

---

### Node Events

#### GET /nodes/{node_id}/events
Get lifecycle events for a node.

**Query Parameters:**
- `type` (optional): Filter by event type
- `severity` (optional): Filter by severity (info, warning, error, critical)
- `page` (default: 1): Page number
- `per_page` (default: 20, max: 100): Results per page

**Response:**
```json
{
  "events": [
    {
      "id": 1,
      "event_id": "evt-abc123",
      "node_id": "abc123",
      "event_type": "node_registered",
      "severity": "info",
      "message": "Node registered successfully",
      "details": {},
      "created_at": "2026-01-15T10:00:00"
    }
  ],
  "total": 1,
  "page": 1,
  "per_page": 20
}
```

**Event Types:**
- `node_registered`
- `node_enrolled`
- `heartbeat_received`
- `heartbeat_missed`
- `status_changed`
- `deployment_started`
- `deployment_completed`
- `deployment_failed`
- `certificate_issued`
- `certificate_renewed`
- `certificate_expired`
- `ssh_connection_failed`
- `ssh_connection_success`

---

### Certificate Management

#### GET /nodes/{node_id}/certificate
Get certificate status for a node.

**Response:**
```json
{
  "id": 1,
  "certificate_id": "cert-abc123",
  "node_id": "abc123",
  "fingerprint": "sha256:a1b2c3d4...",
  "issued_at": "2026-01-15T10:00:00",
  "expires_at": "2027-01-15T10:00:00",
  "status": "active",
  "created_at": "2026-01-15T10:00:00",
  "updated_at": "2026-01-15T10:00:00"
}
```

#### POST /nodes/{node_id}/certificate/renew
Renew PKI certificate for a node.

**Response:**
```json
{
  "success": true,
  "message": "Certificate renewed successfully",
  "certificate": {
    "id": 2,
    "certificate_id": "cert-xyz789",
    "node_id": "abc123",
    "fingerprint": "sha256:e5f6g7h8...",
    "issued_at": "2026-01-15T12:00:00",
    "expires_at": "2027-01-15T12:00:00",
    "status": "active",
    "created_at": "2026-01-15T12:00:00",
    "updated_at": "2026-01-15T12:00:00"
  }
}
```

#### POST /nodes/{node_id}/certificate/deploy
Deploy certificate to node using Ansible.

**Response:**
```json
{
  "success": true,
  "message": "Certificate deployment job started",
  "job_id": "job-abc123"
}
```

---

### Update Management

#### GET /updates/check
Check for available updates.

**Query Parameters:**
- `node_id` (optional): Filter updates for specific node

**Response:**
```json
{
  "updates": [
    {
      "id": 1,
      "update_id": "upd-abc123",
      "node_id": "abc123",
      "package_name": "nginx",
      "current_version": "1.20.0",
      "available_version": "1.22.0",
      "update_type": "package",
      "severity": "normal",
      "description": "Security and bug fixes",
      "is_applied": false,
      "applied_at": null,
      "created_at": "2026-01-15T10:00:00",
      "updated_at": "2026-01-15T10:00:00"
    }
  ],
  "total": 1
}
```

**Update Types:**
- `package`: Regular package update
- `system`: System-level update
- `security`: Security patch

**Severity Levels:**
- `low`: Minor updates, cosmetic fixes
- `normal`: Regular updates
- `high`: Important updates
- `critical`: Critical security patches

#### POST /updates/apply
Apply updates to a node.

**Request:**
```json
{
  "node_id": "abc123",
  "update_ids": ["upd-abc123", "upd-def456"]
}
```

**Response:**
```json
{
  "success": true,
  "message": "Update job started for 2 package(s)",
  "job_id": "job-xyz789"
}
```

---

### Deployment Management

See existing documentation for deployment endpoints.

---

### Settings

See existing documentation for settings endpoints.

---

## Error Responses

All endpoints return consistent error responses:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**Common HTTP Status Codes:**
- `200 OK`: Success
- `201 Created`: Resource created successfully
- `204 No Content`: Success with no response body
- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

---

## WebSocket Events

See existing documentation for WebSocket events.
