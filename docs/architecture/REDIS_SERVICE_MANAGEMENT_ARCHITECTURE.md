# Redis Service Management Architecture

**Document Version:** 1.0
**Date:** 2025-10-10
**Status:** Design Specification
**Target Implementation:** Phase 6

---

## Executive Summary

This document defines the architecture for Redis service management features in AutoBot's distributed VM infrastructure. The design enables frontend UI controls and backend auto-detection/auto-start capabilities for the Redis service running on VM3 (172.16.168.23), while maintaining security, auditability, and alignment with AutoBot's "No Temporary Fixes" policy.

---

## Table of Contents

1. [System Context](#1-system-context)
2. [Architecture Overview](#2-architecture-overview)
3. [Component Design](#3-component-design)
4. [API Specification](#4-api-specification)
5. [Frontend Integration](#5-frontend-integration)
6. [Security Model](#6-security-model)
7. [Monitoring & Health Detection](#7-monitoring--health-detection)
8. [Error Handling & Failover](#8-error-handling--failover)
9. [Implementation Phases](#9-implementation-phases)
10. [Testing Strategy](#10-testing-strategy)

---

## 1. System Context

### 1.1 Current State

**Infrastructure:**
- Redis service runs on VM3 (172.16.168.23:6379)
- SSH key-based authentication configured (~/.ssh/autobot_key)
- Existing SSHManager handles remote command execution
- ConsolidatedHealthService aggregates component health
- Frontend displays service status via MultiMachineHealth.vue

**Gaps:**
- No service control endpoints (start/stop/restart)
- No automated Redis health monitoring
- No automated service recovery
- No user-facing service management UI

### 1.2 Requirements

**Functional:**
1. Frontend UI to start/stop/restart Redis service
2. Backend auto-detection of Redis service failures
3. Backend auto-start of stopped Redis service
4. Real-time service status updates via WebSocket
5. Audit logging of all service management operations
6. User permission controls for service operations

**Non-Functional:**
- Response time: < 5 seconds for service commands
- Recovery time: < 30 seconds for auto-start
- Availability: 99.9% uptime for management API
- Security: Role-based access control (RBAC)
- Auditability: All operations logged with timestamps

---

## 2. Architecture Overview

### 2.1 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Frontend (VM1: 172.16.168.21)               │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  RedisServiceControl.vue                                      │  │
│  │  - Service status display                                     │  │
│  │  - Start/Stop/Restart buttons                                 │  │
│  │  - Real-time status updates (WebSocket)                       │  │
│  │  - Error notifications                                        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │                                           │
│                          │ HTTP/WebSocket                            │
└──────────────────────────┼───────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Backend API (Main: 172.16.168.20:8001)           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  /api/services/redis (ServiceManagementRouter)                │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  POST /start    - Start Redis service                   │  │  │
│  │  │  POST /stop     - Stop Redis service                    │  │  │
│  │  │  POST /restart  - Restart Redis service                 │  │  │
│  │  │  GET  /status   - Get current service status            │  │  │
│  │  │  GET  /health   - Detailed health check                 │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │                                           │
│                          ▼                                           │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  RedisServiceManager (Core Service)                           │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  - Service control operations                           │  │  │
│  │  │  - Health monitoring & detection                        │  │  │
│  │  │  - Auto-recovery orchestration                          │  │  │
│  │  │  - Status caching & event emission                      │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  │                      │              │                           │  │
│  │           ┌──────────┴────┬─────────┴────────┐                 │  │
│  │           ▼               ▼                  ▼                 │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │  │
│  │  │ SSHManager   │  │ Audit        │  │ WebSocket    │        │  │
│  │  │ - Remote     │  │ Logger       │  │ Manager      │        │  │
│  │  │   commands   │  │ - Track ops  │  │ - Push       │        │  │
│  │  │ - Connection │  │ - Compliance │  │   updates    │        │  │
│  │  │   pooling    │  │              │  │              │        │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘        │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                          │                                           │
│                          │ SSH Commands                              │
└──────────────────────────┼───────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Redis VM (VM3: 172.16.168.23)                    │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  systemd (redis-server.service)                               │  │
│  │  ┌─────────────────────────────────────────────────────────┐  │  │
│  │  │  sudo systemctl start redis-server                      │  │  │
│  │  │  sudo systemctl stop redis-server                       │  │  │
│  │  │  sudo systemctl restart redis-server                    │  │  │
│  │  │  sudo systemctl status redis-server                     │  │  │
│  │  └─────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  Redis Process: 172.16.168.23:6379                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                Background Health Monitor (Async Task)                │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Health Check Loop (every 30 seconds)                         │  │
│  │  1. Check Redis connectivity (redis-cli PING)                 │  │
│  │  2. Check systemd service status                              │  │
│  │  3. If failed: Trigger auto-recovery                          │  │
│  │  4. Emit status updates via WebSocket                         │  │
│  │  5. Log health check results                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 Data Flow

**Service Control Flow:**
```
User clicks "Restart" → Frontend POST /api/services/redis/restart
                     → Backend validates user permissions
                     → RedisServiceManager executes operation
                     → SSHManager sends "systemctl restart redis-server"
                     → systemd restarts Redis process
                     → Health check confirms service healthy
                     → Status update via WebSocket → Frontend updates UI
                     → Audit log records operation
```

**Auto-Recovery Flow:**
```
Health Monitor detects Redis down → RedisServiceManager.auto_recover()
                                 → Check recovery policy
                                 → Execute systemctl start
                                 → Verify service started
                                 → Emit WebSocket notification
                                 → Log recovery action
                                 → If failed: Alert administrators
```

---

## 3. Component Design

### 3.1 RedisServiceManager (Core Service)

**Purpose:** Central service for Redis service lifecycle management

**Responsibilities:**
- Execute service control operations (start/stop/restart)
- Monitor Redis health continuously
- Orchestrate auto-recovery
- Cache service status
- Emit status change events

**Key Methods:**

```python
class RedisServiceManager:
    """Manages Redis service lifecycle and health"""

    async def start_service(self, user_id: str) -> ServiceOperationResult:
        """Start Redis service"""

    async def stop_service(self, user_id: str) -> ServiceOperationResult:
        """Stop Redis service (requires confirmation)"""

    async def restart_service(self, user_id: str) -> ServiceOperationResult:
        """Restart Redis service"""

    async def get_service_status(self) -> ServiceStatus:
        """Get current service status (cached)"""

    async def check_health(self) -> HealthStatus:
        """Perform comprehensive health check"""

    async def auto_recover(self) -> RecoveryResult:
        """Attempt automatic service recovery"""

    async def _monitor_health_loop(self):
        """Background task: continuous health monitoring"""

    def register_status_listener(self, callback: Callable):
        """Register callback for status changes"""
```

**Configuration:**

```yaml
redis_service_management:
  health_check:
    interval_seconds: 30
    timeout_seconds: 5
    failure_threshold: 3  # Consecutive failures before auto-recovery

  auto_recovery:
    enabled: true
    max_attempts: 3
    retry_delay_seconds: 10
    notify_on_recovery: true

  service_control:
    operation_timeout: 30
    require_confirmation_for_stop: true
    allowed_operations: ["start", "stop", "restart", "status"]

  permissions:
    start: ["admin", "operator"]
    stop: ["admin"]
    restart: ["admin", "operator"]
    status: ["admin", "operator", "viewer"]
```

### 3.2 ServiceManagementRouter (API Layer)

**Purpose:** RESTful API endpoints for service management

**Location:** `/home/kali/Desktop/AutoBot/backend/api/service_management.py`

**Endpoints:**

```python
router = APIRouter(prefix="/api/services/redis", tags=["Service Management"])

@router.post("/start")
async def start_redis_service(
    current_user: User = Depends(get_current_user)
) -> ServiceOperationResponse:
    """Start Redis service"""

@router.post("/stop")
async def stop_redis_service(
    confirmation: bool = False,
    current_user: User = Depends(get_current_user)
) -> ServiceOperationResponse:
    """Stop Redis service (requires confirmation)"""

@router.post("/restart")
async def restart_redis_service(
    current_user: User = Depends(get_current_user)
) -> ServiceOperationResponse:
    """Restart Redis service"""

@router.get("/status")
async def get_redis_status() -> ServiceStatusResponse:
    """Get current Redis service status"""

@router.get("/health")
async def get_redis_health() -> HealthStatusResponse:
    """Get detailed health information"""

@router.get("/logs")
async def get_service_logs(
    lines: int = 50,
    current_user: User = Depends(require_admin)
) -> ServiceLogsResponse:
    """Get recent service logs"""
```

**Response Models:**

```python
class ServiceOperationResponse(BaseModel):
    success: bool
    operation: str  # "start", "stop", "restart"
    message: str
    duration_seconds: float
    timestamp: datetime
    new_status: str  # "running", "stopped", "failed"

class ServiceStatusResponse(BaseModel):
    status: str  # "running", "stopped", "failed", "unknown"
    pid: Optional[int]
    uptime_seconds: Optional[float]
    memory_mb: Optional[float]
    connections: Optional[int]
    last_check: datetime

class HealthStatusResponse(BaseModel):
    overall_status: str  # "healthy", "degraded", "critical"
    service_running: bool
    connectivity: bool
    response_time_ms: float
    last_successful_command: Optional[datetime]
    error_count_last_hour: int
    recommendations: List[str]
```

### 3.3 Health Monitoring System

**Purpose:** Continuous Redis health detection

**Components:**

1. **ConnectionHealthChecker:**
   - Tests Redis connectivity via redis-cli PING
   - Measures response time
   - Detects connection failures

2. **SystemdHealthChecker:**
   - Queries systemd service status
   - Monitors process state
   - Detects crashes/restarts

3. **PerformanceHealthChecker:**
   - Monitors memory usage
   - Tracks connection count
   - Checks command latency

**Detection Logic:**

```python
async def detect_redis_failure() -> HealthCheckResult:
    """
    Multi-layer Redis health detection

    Returns:
        HealthCheckResult with status and diagnostics
    """

    # Layer 1: Redis connectivity (fastest)
    try:
        response = await redis_client.ping()
        if not response:
            return HealthCheckResult(
                status="failed",
                layer="connectivity",
                message="Redis PING failed"
            )
    except Exception as e:
        return HealthCheckResult(
            status="failed",
            layer="connectivity",
            error=str(e)
        )

    # Layer 2: Systemd service status
    result = await ssh_manager.execute_command(
        host="redis",
        command="systemctl is-active redis-server",
        timeout=5
    )
    if result.stdout.strip() != "active":
        return HealthCheckResult(
            status="failed",
            layer="systemd",
            message=f"Service status: {result.stdout.strip()}"
        )

    # Layer 3: Performance metrics
    info = await redis_client.info()
    memory_usage_mb = info["used_memory"] / 1024 / 1024

    if memory_usage_mb > 4096:  # 4GB threshold
        return HealthCheckResult(
            status="degraded",
            layer="performance",
            message=f"High memory usage: {memory_usage_mb:.1f} MB"
        )

    return HealthCheckResult(
        status="healthy",
        layers_checked=["connectivity", "systemd", "performance"]
    )
```

**Monitoring Intervals:**

| Check Type | Interval | Timeout | Failure Threshold |
|-----------|----------|---------|------------------|
| Connectivity | 30s | 5s | 3 consecutive |
| Systemd Status | 60s | 10s | 2 consecutive |
| Performance | 120s | 15s | N/A (advisory) |

### 3.4 Auto-Recovery System

**Purpose:** Automated service recovery without manual intervention

**Recovery Strategies:**

1. **Soft Recovery (Level 1):**
   - Scenario: Redis process hung but systemd thinks it's running
   - Action: Send SIGHUP to reload configuration
   - Duration: ~5 seconds

2. **Standard Recovery (Level 2):**
   - Scenario: Redis service stopped
   - Action: systemctl start redis-server
   - Duration: ~15 seconds

3. **Hard Recovery (Level 3):**
   - Scenario: Redis service failed to start
   - Action: systemctl restart redis-server
   - Duration: ~30 seconds

4. **Critical Recovery (Level 4):**
   - Scenario: All recovery attempts failed
   - Action: Alert administrators, disable auto-recovery
   - Manual intervention required

**Recovery Decision Tree:**

```
Redis health check fails
    │
    ├─ Is service running? (systemctl status)
    │  ├─ YES: Soft Recovery (SIGHUP)
    │  │      ├─ Success? → Monitor
    │  │      └─ Failed? → Standard Recovery
    │  │
    │  └─ NO: Standard Recovery (systemctl start)
    │         ├─ Success? → Monitor
    │         └─ Failed? → Hard Recovery
    │
    └─ Hard Recovery (systemctl restart)
           ├─ Success? → Monitor
           └─ Failed? → Critical Alert
```

**Recovery Implementation:**

```python
async def auto_recover(self) -> RecoveryResult:
    """
    Attempt automatic Redis recovery

    Returns:
        RecoveryResult with success status and details
    """

    # Check if recovery is enabled
    if not self.config.auto_recovery.enabled:
        return RecoveryResult(
            success=False,
            reason="Auto-recovery disabled"
        )

    # Check recovery attempt limit
    if self.recovery_attempts >= self.config.auto_recovery.max_attempts:
        await self._send_critical_alert(
            "Max recovery attempts exceeded"
        )
        return RecoveryResult(
            success=False,
            reason="Max attempts exceeded",
            requires_manual_intervention=True
        )

    # Increment attempt counter
    self.recovery_attempts += 1

    # Get current service status
    status = await self._get_systemd_status()

    # Determine recovery strategy
    if status.is_running:
        # Soft recovery: service running but not responding
        result = await self._soft_recovery()
    elif status.is_failed:
        # Hard recovery: service in failed state
        result = await self._hard_recovery()
    else:
        # Standard recovery: service simply stopped
        result = await self._standard_recovery()

    # Verify recovery success
    if result.success:
        # Reset attempt counter on success
        self.recovery_attempts = 0

        # Verify service health
        health = await self.check_health()
        if health.overall_status == "healthy":
            await self._send_recovery_notification(
                f"Redis recovered successfully using {result.strategy}"
            )
            return result

    # Recovery failed, try next level
    if self.recovery_attempts < self.config.auto_recovery.max_attempts:
        # Wait before retry
        await asyncio.sleep(self.config.auto_recovery.retry_delay_seconds)
        # Escalate to next recovery level
        return await self._escalate_recovery(result)

    # All recovery attempts exhausted
    await self._send_critical_alert(
        f"All recovery attempts failed: {result.error}"
    )
    return RecoveryResult(
        success=False,
        reason="All recovery strategies failed",
        requires_manual_intervention=True
    )
```

---

## 4. API Specification

### 4.1 Service Control Endpoints

#### POST /api/services/redis/start

**Description:** Start Redis service on VM3

**Authentication:** Required (Bearer token)

**Authorization:** Roles: admin, operator

**Request:**
```json
{}
```

**Response (Success - 200):**
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

**Response (Already Running - 200):**
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

**Response (Failed - 500):**
```json
{
  "success": false,
  "operation": "start",
  "message": "Failed to start Redis service",
  "error": "systemctl start command failed: exit code 1",
  "duration_seconds": 5.0,
  "timestamp": "2025-10-10T14:30:00Z",
  "new_status": "failed"
}
```

**Response (Unauthorized - 403):**
```json
{
  "detail": "Insufficient permissions to start Redis service"
}
```

---

#### POST /api/services/redis/stop

**Description:** Stop Redis service on VM3

**Authentication:** Required (Bearer token)

**Authorization:** Roles: admin only

**Request:**
```json
{
  "confirmation": true
}
```

**Response (Success - 200):**
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

**Response (Confirmation Required - 400):**
```json
{
  "error": "Confirmation required to stop Redis service",
  "message": "Stopping Redis will affect all dependent services",
  "affected_services": ["backend", "knowledge_base", "cache"],
  "confirmation_required": true
}
```

---

#### POST /api/services/redis/restart

**Description:** Restart Redis service on VM3

**Authentication:** Required (Bearer token)

**Authorization:** Roles: admin, operator

**Request:**
```json
{}
```

**Response (Success - 200):**
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

#### GET /api/services/redis/status

**Description:** Get current Redis service status

**Authentication:** Not required (public endpoint)

**Authorization:** N/A

**Response (Running - 200):**
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

**Response (Stopped - 200):**
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

#### GET /api/services/redis/health

**Description:** Get detailed health status

**Authentication:** Not required

**Authorization:** N/A

**Response (Healthy - 200):**
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

**Response (Degraded - 200):**
```json
{
  "overall_status": "degraded",
  "service_running": true,
  "connectivity": true,
  "response_time_ms": 150.5,
  "last_successful_command": "2025-10-10T14:29:55Z",
  "error_count_last_hour": 5,
  "health_checks": {
    "connectivity": {
      "status": "pass",
      "duration_ms": 150.5,
      "message": "PING successful but slow"
    },
    "systemd": {
      "status": "pass",
      "duration_ms": 50.0,
      "message": "Service active and running"
    },
    "performance": {
      "status": "warning",
      "duration_ms": 15.0,
      "message": "High memory usage detected",
      "metrics": {
        "memory_usage_mb": 3500.0,
        "memory_limit_mb": 4096.0,
        "cpu_usage_percent": 45.0,
        "connections": 8500,
        "max_connections": 10000
      }
    }
  },
  "recommendations": [
    "Consider increasing memory limit",
    "Monitor connection usage",
    "Review slow queries"
  ],
  "auto_recovery": {
    "enabled": true,
    "recent_recoveries": 0,
    "last_recovery": null
  }
}
```

**Response (Critical - 200):**
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

#### GET /api/services/redis/logs

**Description:** Get recent Redis service logs

**Authentication:** Required (Bearer token)

**Authorization:** Roles: admin only

**Query Parameters:**
- `lines` (optional, default: 50): Number of log lines to retrieve
- `since` (optional): Timestamp to get logs since (ISO 8601)
- `level` (optional): Filter by log level (error, warning, info)

**Response (Success - 200):**
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
    }
  ],
  "total_lines": 50,
  "service": "redis-server",
  "vm": "172.16.168.23"
}
```

---

### 4.2 WebSocket Real-Time Updates

**Endpoint:** `ws://172.16.168.20:8001/ws/services/redis/status`

**Authentication:** Required (token in URL or header)

**Message Format (Status Update):**
```json
{
  "type": "service_status",
  "service": "redis",
  "status": "running",
  "timestamp": "2025-10-10T14:30:00Z",
  "details": {
    "pid": 12345,
    "connections": 42,
    "memory_mb": 128.5
  }
}
```

**Message Format (Service Event):**
```json
{
  "type": "service_event",
  "service": "redis",
  "event": "restart",
  "user": "admin@autobot.local",
  "timestamp": "2025-10-10T14:30:00Z",
  "result": "success"
}
```

**Message Format (Auto-Recovery):**
```json
{
  "type": "auto_recovery",
  "service": "redis",
  "recovery_level": "standard",
  "status": "success",
  "timestamp": "2025-10-10T14:30:00Z",
  "message": "Redis service recovered automatically"
}
```

---

## 5. Frontend Integration

### 5.1 Component Structure

**New Components:**

```
autobot-vue/src/
├── components/
│   └── services/
│       ├── RedisServiceControl.vue      # Main service control component
│       ├── ServiceStatusBadge.vue       # Status indicator badge
│       └── ServiceLogsViewer.vue        # Logs viewing component
├── composables/
│   └── useServiceManagement.js          # Service management composable
└── services/
    └── RedisServiceAPI.js               # API client for service management
```

### 5.2 RedisServiceControl.vue

**Purpose:** Main UI for Redis service management

**Location:** `/home/kali/Desktop/AutoBot/autobot-vue/src/components/services/RedisServiceControl.vue`

**Features:**
- Real-time service status display
- Start/Stop/Restart buttons
- Confirmation dialogs for destructive actions
- Error notifications
- Service logs viewer
- Auto-recovery status indicator

**Component Template:**

```vue
<template>
  <div class="redis-service-control">
    <!-- Service Status Header -->
    <div class="service-header">
      <h3>Redis Service</h3>
      <ServiceStatusBadge
        :status="serviceStatus.status"
        :loading="loading"
      />
    </div>

    <!-- Service Details -->
    <div class="service-details" v-if="serviceStatus.status === 'running'">
      <div class="detail-item">
        <span class="label">Uptime:</span>
        <span class="value">{{ formatUptime(serviceStatus.uptime_seconds) }}</span>
      </div>
      <div class="detail-item">
        <span class="label">Memory:</span>
        <span class="value">{{ serviceStatus.memory_mb }} MB</span>
      </div>
      <div class="detail-item">
        <span class="label">Connections:</span>
        <span class="value">{{ serviceStatus.connections }}</span>
      </div>
    </div>

    <!-- Control Buttons -->
    <div class="service-controls">
      <button
        @click="startService"
        :disabled="serviceStatus.status === 'running' || loading"
        class="btn btn-success"
      >
        <i class="fas fa-play"></i> Start
      </button>

      <button
        @click="restartService"
        :disabled="serviceStatus.status !== 'running' || loading"
        class="btn btn-warning"
      >
        <i class="fas fa-sync"></i> Restart
      </button>

      <button
        @click="stopService"
        :disabled="serviceStatus.status !== 'running' || loading"
        class="btn btn-danger"
      >
        <i class="fas fa-stop"></i> Stop
      </button>

      <button
        @click="refreshStatus"
        :disabled="loading"
        class="btn btn-secondary"
      >
        <i class="fas fa-refresh"></i> Refresh
      </button>
    </div>

    <!-- Health Status -->
    <div class="health-status" v-if="healthStatus">
      <h4>Health Status</h4>
      <div :class="['health-indicator', healthStatus.overall_status]">
        {{ healthStatus.overall_status.toUpperCase() }}
      </div>

      <div class="health-checks">
        <div
          v-for="(check, name) in healthStatus.health_checks"
          :key="name"
          class="health-check"
        >
          <span class="check-name">{{ name }}:</span>
          <span :class="['check-status', check.status]">
            {{ check.status }}
          </span>
          <span class="check-duration">{{ check.duration_ms }}ms</span>
        </div>
      </div>

      <div v-if="healthStatus.recommendations.length > 0" class="recommendations">
        <h5>Recommendations:</h5>
        <ul>
          <li v-for="(rec, idx) in healthStatus.recommendations" :key="idx">
            {{ rec }}
          </li>
        </ul>
      </div>
    </div>

    <!-- Auto-Recovery Status -->
    <div v-if="healthStatus?.auto_recovery" class="auto-recovery">
      <h4>Auto-Recovery</h4>
      <div class="recovery-status">
        <span class="label">Enabled:</span>
        <span class="value">{{ healthStatus.auto_recovery.enabled ? 'Yes' : 'No' }}</span>
      </div>
      <div class="recovery-status" v-if="healthStatus.auto_recovery.recent_recoveries > 0">
        <span class="label">Recent Recoveries:</span>
        <span class="value warning">{{ healthStatus.auto_recovery.recent_recoveries }}</span>
      </div>
      <div class="recovery-status" v-if="healthStatus.auto_recovery.requires_manual_intervention">
        <span class="alert alert-danger">
          Manual intervention required - auto-recovery failed
        </span>
      </div>
    </div>

    <!-- Service Logs -->
    <div class="service-logs">
      <button @click="toggleLogs" class="btn btn-link">
        {{ showLogs ? 'Hide Logs' : 'Show Logs' }}
      </button>
      <ServiceLogsViewer v-if="showLogs" :service="'redis'" />
    </div>

    <!-- Confirmation Dialog -->
    <ConfirmDialog
      v-if="showConfirmDialog"
      :title="confirmDialog.title"
      :message="confirmDialog.message"
      :warning="confirmDialog.warning"
      @confirm="confirmDialog.onConfirm"
      @cancel="showConfirmDialog = false"
    />
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue';
import { useServiceManagement } from '@/composables/useServiceManagement';
import ServiceStatusBadge from './ServiceStatusBadge.vue';
import ServiceLogsViewer from './ServiceLogsViewer.vue';
import ConfirmDialog from '@/components/common/ConfirmDialog.vue';

const {
  serviceStatus,
  healthStatus,
  loading,
  startService: apiStartService,
  stopService: apiStopService,
  restartService: apiRestartService,
  refreshStatus,
  subscribeToStatusUpdates
} = useServiceManagement('redis');

const showLogs = ref(false);
const showConfirmDialog = ref(false);
const confirmDialog = ref({
  title: '',
  message: '',
  warning: '',
  onConfirm: () => {}
});

onMounted(() => {
  // Initial status fetch
  refreshStatus();

  // Subscribe to real-time updates
  subscribeToStatusUpdates((update) => {
    console.log('Service status update:', update);
  });
});

onUnmounted(() => {
  // Cleanup subscriptions
});

const startService = async () => {
  try {
    loading.value = true;
    await apiStartService();
    // Success notification handled by composable
  } catch (error) {
    console.error('Failed to start service:', error);
  } finally {
    loading.value = false;
  }
};

const restartService = async () => {
  showConfirmDialog.value = true;
  confirmDialog.value = {
    title: 'Restart Redis Service',
    message: 'This will temporarily interrupt Redis service. Active connections will be dropped.',
    warning: 'All connected clients will be disconnected during restart.',
    onConfirm: async () => {
      try {
        showConfirmDialog.value = false;
        loading.value = true;
        await apiRestartService();
      } catch (error) {
        console.error('Failed to restart service:', error);
      } finally {
        loading.value = false;
      }
    }
  };
};

const stopService = async () => {
  showConfirmDialog.value = true;
  confirmDialog.value = {
    title: 'Stop Redis Service',
    message: 'This will stop Redis service completely. All dependent services will be affected.',
    warning: 'This action requires administrator confirmation and will affect system functionality.',
    onConfirm: async () => {
      try {
        showConfirmDialog.value = false;
        loading.value = true;
        await apiStopService();
      } catch (error) {
        console.error('Failed to stop service:', error);
      } finally {
        loading.value = false;
      }
    }
  };
};

const toggleLogs = () => {
  showLogs.value = !showLogs.value;
};

const formatUptime = (seconds) => {
  if (!seconds) return 'N/A';

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);

  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
};
</script>

<style scoped>
.redis-service-control {
  padding: 20px;
  background: var(--card-bg);
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.service-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.service-details {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 15px;
  margin-bottom: 20px;
  padding: 15px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.detail-item {
  display: flex;
  flex-direction: column;
}

.detail-item .label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 4px;
}

.detail-item .value {
  font-size: 1.1rem;
  font-weight: 600;
  color: var(--text-primary);
}

.service-controls {
  display: flex;
  gap: 10px;
  margin-bottom: 20px;
}

.service-controls button {
  flex: 1;
}

.health-indicator {
  display: inline-block;
  padding: 8px 16px;
  border-radius: 4px;
  font-weight: 600;
  margin-bottom: 15px;
}

.health-indicator.healthy {
  background: #d4edda;
  color: #155724;
}

.health-indicator.degraded {
  background: #fff3cd;
  color: #856404;
}

.health-indicator.critical {
  background: #f8d7da;
  color: #721c24;
}

.health-checks {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.health-check {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.check-status.pass {
  color: #28a745;
  font-weight: 600;
}

.check-status.warning {
  color: #ffc107;
  font-weight: 600;
}

.check-status.fail {
  color: #dc3545;
  font-weight: 600;
}

.recommendations {
  margin-top: 15px;
  padding: 15px;
  background: #fff3cd;
  border-left: 4px solid #ffc107;
  border-radius: 4px;
}

.recommendations ul {
  margin: 10px 0 0 20px;
}

.auto-recovery {
  margin-top: 20px;
  padding: 15px;
  background: var(--bg-secondary);
  border-radius: 6px;
}

.recovery-status {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.alert {
  padding: 10px;
  border-radius: 4px;
  margin-top: 10px;
}

.alert-danger {
  background: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}
</style>
```

### 5.3 useServiceManagement Composable

**Purpose:** Reusable service management logic

**Location:** `/home/kali/Desktop/AutoBot/autobot-vue/src/composables/useServiceManagement.js`

```javascript
import { ref, onMounted, onUnmounted } from 'vue';
import RedisServiceAPI from '@/services/RedisServiceAPI';
import { useNotification } from '@/composables/useNotification';
import { useWebSocket } from '@/composables/useWebSocket';

export function useServiceManagement(serviceName) {
  const { showSuccess, showError, showWarning } = useNotification();
  const { subscribe, unsubscribe } = useWebSocket();

  const serviceStatus = ref({
    status: 'unknown',
    pid: null,
    uptime_seconds: null,
    memory_mb: null,
    connections: null,
    last_check: null
  });

  const healthStatus = ref(null);
  const loading = ref(false);

  let statusSubscription = null;

  const refreshStatus = async () => {
    try {
      loading.value = true;
      const [status, health] = await Promise.all([
        RedisServiceAPI.getStatus(),
        RedisServiceAPI.getHealth()
      ]);

      serviceStatus.value = status;
      healthStatus.value = health;
    } catch (error) {
      console.error('Failed to refresh status:', error);
      showError('Failed to refresh service status');
    } finally {
      loading.value = false;
    }
  };

  const startService = async () => {
    try {
      loading.value = true;
      const result = await RedisServiceAPI.start();

      if (result.success) {
        showSuccess(result.message);
        await refreshStatus();
      } else {
        showError(result.message || 'Failed to start service');
      }

      return result;
    } catch (error) {
      console.error('Failed to start service:', error);
      showError('Failed to start service: ' + error.message);
      throw error;
    } finally {
      loading.value = false;
    }
  };

  const stopService = async () => {
    try {
      loading.value = true;
      const result = await RedisServiceAPI.stop(true); // confirmation=true

      if (result.success) {
        showWarning(result.message);
        await refreshStatus();
      } else {
        showError(result.message || 'Failed to stop service');
      }

      return result;
    } catch (error) {
      console.error('Failed to stop service:', error);
      showError('Failed to stop service: ' + error.message);
      throw error;
    } finally {
      loading.value = false;
    }
  };

  const restartService = async () => {
    try {
      loading.value = true;
      const result = await RedisServiceAPI.restart();

      if (result.success) {
        showSuccess(result.message);
        await refreshStatus();
      } else {
        showError(result.message || 'Failed to restart service');
      }

      return result;
    } catch (error) {
      console.error('Failed to restart service:', error);
      showError('Failed to restart service: ' + error.message);
      throw error;
    } finally {
      loading.value = false;
    }
  };

  const subscribeToStatusUpdates = (callback) => {
    statusSubscription = subscribe(`/ws/services/${serviceName}/status`, (message) => {
      if (message.type === 'service_status') {
        serviceStatus.value = {
          ...serviceStatus.value,
          ...message.details,
          status: message.status,
          last_check: message.timestamp
        };
      } else if (message.type === 'service_event') {
        if (message.result === 'success') {
          showSuccess(`Service ${message.event} completed`);
        } else {
          showError(`Service ${message.event} failed`);
        }
      } else if (message.type === 'auto_recovery') {
        if (message.status === 'success') {
          showWarning(`Auto-recovery: ${message.message}`);
        } else {
          showError(`Auto-recovery failed: ${message.message}`);
        }
      }

      // Refresh full status after events
      if (message.type !== 'service_status') {
        refreshStatus();
      }

      if (callback) {
        callback(message);
      }
    });
  };

  onMounted(() => {
    refreshStatus();
  });

  onUnmounted(() => {
    if (statusSubscription) {
      unsubscribe(statusSubscription);
    }
  });

  return {
    serviceStatus,
    healthStatus,
    loading,
    startService,
    stopService,
    restartService,
    refreshStatus,
    subscribeToStatusUpdates
  };
}
```

---

## 6. Security Model

### 6.1 Authentication & Authorization

**Authentication Methods:**
1. JWT Bearer Tokens (primary)
2. Session-based authentication (fallback)
3. Service-to-service authentication (internal)

**Role-Based Access Control (RBAC):**

| Operation | Admin | Operator | Viewer | Anonymous |
|-----------|-------|----------|--------|-----------|
| View Status | ✓ | ✓ | ✓ | ✓ |
| View Health | ✓ | ✓ | ✓ | ✓ |
| Start Service | ✓ | ✓ | ✗ | ✗ |
| Restart Service | ✓ | ✓ | ✗ | ✗ |
| Stop Service | ✓ | ✗ | ✗ | ✗ |
| View Logs | ✓ | ✗ | ✗ | ✗ |
| Configure Auto-Recovery | ✓ | ✗ | ✗ | ✗ |

**Permission Implementation:**

```python
from fastapi import Depends, HTTPException
from backend.security.auth import get_current_user, require_role

@router.post("/start")
async def start_redis_service(
    current_user: User = Depends(require_role(["admin", "operator"]))
):
    """Start Redis service - requires admin or operator role"""
    pass

@router.post("/stop")
async def stop_redis_service(
    confirmation: bool = False,
    current_user: User = Depends(require_role(["admin"]))
):
    """Stop Redis service - requires admin role only"""
    pass
```

### 6.2 Command Validation

**Security Layers:**

1. **Input Validation:**
   - Sanitize all user inputs
   - Validate command parameters
   - Prevent command injection

2. **Command Whitelisting:**
   - Only allow predefined systemctl commands
   - Block dangerous operations
   - Validate command structure

3. **SecureCommandExecutor Integration:**
   - Risk assessment for all commands
   - Block DANGEROUS risk level commands
   - Log all command executions

**Allowed Commands:**

```python
ALLOWED_REDIS_COMMANDS = {
    "start": "sudo systemctl start redis-server",
    "stop": "sudo systemctl stop redis-server",
    "restart": "sudo systemctl restart redis-server",
    "status": "systemctl status redis-server",
    "is-active": "systemctl is-active redis-server",
    "logs": "journalctl -u redis-server -n {lines}",
}

def validate_service_command(operation: str) -> str:
    """Validate and return whitelisted command"""
    if operation not in ALLOWED_REDIS_COMMANDS:
        raise ValueError(f"Operation '{operation}' not allowed")

    return ALLOWED_REDIS_COMMANDS[operation]
```

### 6.3 SSH Security

**SSH Key Requirements:**
- 4096-bit RSA keys minimum
- Key-based authentication only (no passwords)
- Dedicated service account (`autobot`)
- Limited sudo permissions via /etc/sudoers.d/

**sudoers Configuration (VM3):**

```bash
# /etc/sudoers.d/autobot-redis
# Allow autobot user to manage Redis service
autobot ALL=(ALL) NOPASSWD: /bin/systemctl start redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl stop redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl restart redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl status redis-server
autobot ALL=(ALL) NOPASSWD: /bin/journalctl -u redis-server *
```

### 6.4 Audit Logging

**Audit Requirements:**
- Log all service management operations
- Include user identity, timestamp, operation, result
- Store in dedicated audit log file
- Rotate logs regularly
- Integrate with centralized logging system

**Audit Log Format:**

```json
{
  "timestamp": "2025-10-10T14:30:00Z",
  "event_type": "service_operation",
  "service": "redis",
  "operation": "restart",
  "user": {
    "id": "user-123",
    "email": "admin@autobot.local",
    "role": "admin"
  },
  "source_ip": "172.16.168.20",
  "result": {
    "success": true,
    "duration_seconds": 15.7,
    "exit_code": 0
  },
  "security": {
    "command_validated": true,
    "risk_level": "moderate",
    "ssh_key_used": true
  }
}
```

---

## 7. Monitoring & Health Detection

### 7.1 Health Check Strategy

**Multi-Layer Health Detection:**

| Layer | Check Type | Frequency | Timeout | Purpose |
|-------|-----------|-----------|---------|---------|
| 1 | Redis PING | 30s | 5s | Connectivity verification |
| 2 | Systemd Status | 60s | 10s | Service state validation |
| 3 | Performance Metrics | 120s | 15s | Resource monitoring |
| 4 | Connection Pool | 60s | 5s | Client health check |

**Health Status Definitions:**

- **Healthy:** All checks pass, normal operation
- **Degraded:** Service running but performance issues detected
- **Critical:** Service not running or not responding
- **Unknown:** Unable to determine status

### 7.2 Failure Detection Logic

**Failure Criteria:**

1. **Connectivity Failure:**
   - 3 consecutive PING timeouts
   - Connection refused errors
   - Network unreachable

2. **Service Failure:**
   - systemd reports service as "failed"
   - Process not found (PID missing)
   - Exit code indicates crash

3. **Performance Degradation:**
   - Response time > 100ms consistently
   - Memory usage > 90% of limit
   - Connection count near maximum

**Detection Implementation:**

```python
class RedisHealthMonitor:
    def __init__(self):
        self.consecutive_failures = 0
        self.failure_threshold = 3

    async def monitor_loop(self):
        """Continuous health monitoring"""
        while True:
            try:
                health_result = await self.check_health()

                if health_result.status == "failed":
                    self.consecutive_failures += 1

                    if self.consecutive_failures >= self.failure_threshold:
                        await self.trigger_auto_recovery(health_result)
                else:
                    # Reset failure counter on success
                    self.consecutive_failures = 0

                await asyncio.sleep(self.config.health_check_interval)

            except Exception as e:
                logger.error(f"Health monitor exception: {e}")
                await asyncio.sleep(10)  # Backoff on errors
```

### 7.3 Integration with Existing Monitoring

**ConsolidatedHealthService Integration:**

```python
# Register Redis service management health checker
from backend.services.consolidated_health_service import consolidated_health

async def check_redis_service_management_health():
    """Health check for Redis service management"""
    try:
        service_manager = get_redis_service_manager()
        status = await service_manager.get_service_status()
        health = await service_manager.check_health()

        return {
            "status": "healthy" if health.overall_status == "healthy" else "degraded",
            "component": "redis_service_management",
            "service_status": status.status,
            "health_status": health.overall_status,
            "auto_recovery_enabled": service_manager.config.auto_recovery.enabled,
            "recent_operations": len(service_manager.operation_history),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "component": "redis_service_management",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Register with consolidated health service
consolidated_health.register_component(
    "redis_service_management",
    check_redis_service_management_health
)
```

### 7.4 Alerting & Notifications

**Alert Scenarios:**

1. **Service Down Alert:**
   - Trigger: Redis service stopped or crashed
   - Recipients: Administrators
   - Priority: Critical
   - Channels: Email, WebSocket, System notification

2. **Auto-Recovery Alert:**
   - Trigger: Auto-recovery attempted
   - Recipients: Operators, Administrators
   - Priority: Warning
   - Channels: WebSocket, System notification

3. **Recovery Failure Alert:**
   - Trigger: Auto-recovery failed after max attempts
   - Recipients: Administrators
   - Priority: Critical
   - Channels: Email, WebSocket, System notification, SMS (if configured)

4. **Performance Degradation Alert:**
   - Trigger: Performance metrics exceed thresholds
   - Recipients: Operators
   - Priority: Warning
   - Channels: WebSocket, System notification

---

## 8. Error Handling & Failover

### 8.1 Error Categories

**Error Taxonomy:**

| Category | Examples | Recovery Strategy | User Impact |
|----------|----------|-------------------|-------------|
| Transient | Network timeout, temporary overload | Automatic retry | Minimal |
| Recoverable | Service crashed, config error | Auto-recovery | Brief outage |
| Critical | Disk full, hardware failure | Manual intervention | Extended outage |
| Security | Permission denied, SSH key invalid | Alert and block | Operation fails |

### 8.2 Error Handling Strategies

**Retry Logic:**

```python
async def execute_service_command_with_retry(
    command: str,
    max_retries: int = 3,
    retry_delay: int = 5
) -> CommandResult:
    """Execute command with retry logic for transient failures"""

    last_error = None

    for attempt in range(max_retries):
        try:
            result = await ssh_manager.execute_command(
                host="redis",
                command=command,
                timeout=30
            )

            if result.success:
                return result

            # Command executed but failed - may not be retryable
            if result.exit_code != 0:
                # Check if error is retryable
                if is_transient_error(result.stderr):
                    logger.warning(
                        f"Transient error on attempt {attempt + 1}: {result.stderr}"
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    # Non-transient error, don't retry
                    return result

        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(f"Timeout on attempt {attempt + 1}")
            await asyncio.sleep(retry_delay)

        except ConnectionError as e:
            last_error = e
            logger.warning(f"Connection error on attempt {attempt + 1}")
            await asyncio.sleep(retry_delay)

    # All retries exhausted
    raise ServiceOperationError(
        f"Operation failed after {max_retries} attempts",
        last_error=last_error
    )
```

**Circuit Breaker Pattern:**

```python
class ServiceOperationCircuitBreaker:
    """Circuit breaker for service operations"""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout_seconds: int = 60,
        half_open_attempts: int = 1
    ):
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_attempts = half_open_attempts

        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open

    async def execute(self, operation: Callable) -> Any:
        """Execute operation with circuit breaker protection"""

        if self.state == "open":
            # Check if timeout has elapsed
            if (datetime.now() - self.last_failure_time).seconds > self.timeout_seconds:
                self.state = "half-open"
                logger.info("Circuit breaker entering half-open state")
            else:
                raise CircuitBreakerOpenError(
                    "Service operations blocked by circuit breaker"
                )

        try:
            result = await operation()

            if self.state == "half-open":
                # Success in half-open state, reset to closed
                self.state = "closed"
                self.failure_count = 0
                logger.info("Circuit breaker reset to closed state")

            return result

        except Exception as e:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.failure_count >= self.failure_threshold:
                self.state = "open"
                logger.error(
                    f"Circuit breaker opened after {self.failure_count} failures"
                )

            raise
```

### 8.3 Failover Scenarios

**Scenario 1: Redis VM Unreachable**

```
Problem: SSH connection to Redis VM fails
Detection: SSHManager connection timeout
Response:
  1. Verify main machine network connectivity
  2. Check Redis VM status via hypervisor (if available)
  3. Alert administrators with VM access details
  4. Disable auto-recovery (can't execute commands)
  5. Frontend displays "VM Unreachable" status
```

**Scenario 2: Redis Service Fails to Start**

```
Problem: systemctl start command succeeds but service doesn't start
Detection: systemd status shows "failed" after start attempt
Response:
  1. Check service logs for error details
  2. Identify failure reason (config error, port conflict, etc.)
  3. If config error: Restore last known good config
  4. If port conflict: Identify conflicting process
  5. Alert administrators with diagnostic details
  6. Disable auto-recovery until manual fix applied
```

**Scenario 3: Auto-Recovery Loop**

```
Problem: Service starts but immediately crashes, causing recovery loop
Detection: Multiple auto-recovery attempts in short time period
Response:
  1. Detect recovery loop (3+ recoveries in 5 minutes)
  2. Disable auto-recovery immediately
  3. Capture diagnostic snapshot:
     - Service logs
     - System resources
     - Configuration files
     - Recent changes
  4. Alert administrators with diagnostic bundle
  5. Frontend displays "Manual Intervention Required"
```

### 8.4 Graceful Degradation

**Degraded Mode Operations:**

When Redis service is unavailable, AutoBot should gracefully degrade:

1. **Session Management:**
   - Fall back to in-memory sessions (ephemeral)
   - Warn users about potential session loss

2. **Caching:**
   - Disable cache writes
   - Serve stale cached data if available
   - Direct database queries as fallback

3. **Real-Time Features:**
   - Queue messages for later delivery
   - Disable real-time notifications temporarily
   - Show "Limited Functionality" banner

4. **Knowledge Base:**
   - Use local embeddings cache
   - Disable vector search temporarily
   - Provide search degradation notice

**Implementation:**

```python
class RedisDegradationHandler:
    """Handle graceful degradation when Redis unavailable"""

    def __init__(self):
        self.degraded_mode = False
        self.degradation_start_time = None

    async def enable_degraded_mode(self):
        """Enable degraded mode"""
        self.degraded_mode = True
        self.degradation_start_time = datetime.now()

        # Notify all services
        await self._broadcast_degradation_status(True)

        # Switch to fallback mechanisms
        await self._enable_fallback_cache()
        await self._enable_memory_sessions()

        logger.warning("Redis degraded mode enabled")

    async def disable_degraded_mode(self):
        """Disable degraded mode"""
        self.degraded_mode = False

        degradation_duration = (
            datetime.now() - self.degradation_start_time
        ).seconds

        # Notify all services
        await self._broadcast_degradation_status(False)

        # Restore normal operations
        await self._disable_fallback_cache()
        await self._restore_redis_sessions()

        logger.info(
            f"Redis degraded mode disabled after {degradation_duration}s"
        )
```

---

## 9. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Objectives:**
- Implement RedisServiceManager core service
- Add service control API endpoints
- Integrate with existing SSHManager
- Basic health monitoring

**Deliverables:**
1. `backend/services/redis_service_manager.py` - Core service implementation
2. `backend/api/service_management.py` - API router with endpoints
3. Health check integration with ConsolidatedHealthService
4. Unit tests for service manager

**Success Criteria:**
- Can start/stop/restart Redis via API
- Health checks detect service status correctly
- SSH commands execute successfully
- Audit logging captures all operations

---

### Phase 2: Auto-Recovery System (Week 1-2)

**Objectives:**
- Implement background health monitoring
- Build auto-recovery orchestration
- Add recovery strategies (soft, standard, hard)
- Implement circuit breaker and retry logic

**Deliverables:**
1. Background health monitor task
2. Auto-recovery decision engine
3. Recovery strategy implementations
4. Error handling and failover logic
5. Integration tests for auto-recovery scenarios

**Success Criteria:**
- Detects Redis failures within 30 seconds
- Auto-recovery succeeds in test scenarios
- Recovery loops prevented by circuit breaker
- Alerts sent when manual intervention required

---

### Phase 3: Frontend Integration (Week 2)

**Objectives:**
- Build Redis service control UI component
- Implement real-time status updates
- Add service logs viewer
- Create confirmation dialogs for destructive operations

**Deliverables:**
1. `autobot-vue/src/components/services/RedisServiceControl.vue`
2. `autobot-vue/src/composables/useServiceManagement.js`
3. `autobot-vue/src/services/RedisServiceAPI.js`
4. WebSocket integration for real-time updates
5. UI/UX testing and refinement

**Success Criteria:**
- Frontend displays real-time service status
- Users can start/stop/restart Redis from UI
- Confirmation dialogs prevent accidental operations
- Error messages provide clear guidance
- Logs viewer displays recent service logs

---

### Phase 4: Security & Audit (Week 2-3)

**Objectives:**
- Implement RBAC for service operations
- Add comprehensive audit logging
- Configure sudo permissions on Redis VM
- Security testing and hardening

**Deliverables:**
1. Role-based permission enforcement
2. Audit log format and storage
3. sudoers configuration for Redis VM
4. Security documentation
5. Penetration testing report

**Success Criteria:**
- Only authorized users can perform operations
- All operations logged with user identity
- SSH keys properly secured and rotated
- Security audit passes without findings

---

### Phase 5: Testing & Documentation (Week 3)

**Objectives:**
- Comprehensive testing (unit, integration, E2E)
- Performance testing and optimization
- Complete user and developer documentation
- Deployment preparation

**Deliverables:**
1. Test suite with 90%+ coverage
2. Performance benchmarks
3. User guide and operational runbook
4. API documentation
5. Deployment checklist

**Success Criteria:**
- All tests pass consistently
- Performance meets SLA requirements
- Documentation complete and accurate
- Ready for production deployment

---

## 10. Testing Strategy

### 10.1 Unit Tests

**Test Coverage Areas:**

1. **RedisServiceManager:**
   - Service control operations (start/stop/restart)
   - Health check logic
   - Auto-recovery decision engine
   - Status caching
   - Event emission

2. **ServiceManagementRouter:**
   - API endpoint logic
   - Request validation
   - Response formatting
   - Permission enforcement

3. **Health Monitors:**
   - Connectivity checks
   - Systemd status parsing
   - Performance metric collection
   - Failure detection logic

**Example Unit Test:**

```python
import pytest
from backend.services.redis_service_manager import RedisServiceManager

@pytest.mark.asyncio
async def test_start_service_when_stopped():
    """Test starting Redis service when it's stopped"""
    manager = RedisServiceManager(config=test_config)

    # Mock SSH manager to simulate service stopped
    manager.ssh_manager.execute_command = AsyncMock(
        return_value=RemoteCommandResult(
            success=True,
            exit_code=0,
            stdout="",
            stderr=""
        )
    )

    # Mock health check to confirm service started
    manager.check_health = AsyncMock(
        return_value=HealthStatus(overall_status="healthy")
    )

    # Execute start operation
    result = await manager.start_service(user_id="test-user")

    # Assertions
    assert result.success is True
    assert result.operation == "start"
    assert result.new_status == "running"
    assert result.duration_seconds > 0

@pytest.mark.asyncio
async def test_auto_recovery_on_failure():
    """Test auto-recovery triggers when health check fails"""
    manager = RedisServiceManager(config=test_config)

    # Mock health check failure
    manager.check_health = AsyncMock(
        return_value=HealthStatus(overall_status="critical")
    )

    # Mock auto-recovery success
    manager._standard_recovery = AsyncMock(
        return_value=RecoveryResult(success=True, strategy="standard")
    )

    # Trigger health monitor
    await manager._monitor_health_loop_iteration()

    # Verify auto-recovery was called
    manager._standard_recovery.assert_called_once()
```

### 10.2 Integration Tests

**Test Scenarios:**

1. **End-to-End Service Control:**
   - Start Redis via API → Verify service running on VM
   - Stop Redis via API → Verify service stopped on VM
   - Restart Redis via API → Verify service restarted

2. **Auto-Recovery Flow:**
   - Stop Redis service manually → Verify auto-recovery starts it
   - Crash Redis process → Verify detection and recovery
   - Test recovery failure → Verify alerting

3. **WebSocket Updates:**
   - Subscribe to status updates → Perform service operation → Verify notification received

4. **Permission Enforcement:**
   - Attempt operation as unauthorized user → Verify blocked
   - Attempt stop as operator → Verify blocked
   - Attempt stop as admin → Verify allowed

**Example Integration Test:**

```python
import pytest
from httpx import AsyncClient

@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_restart_flow(client: AsyncClient, admin_token: str):
    """Test complete restart flow from API to Redis VM"""

    # Get initial status
    response = await client.get("/api/services/redis/status")
    assert response.status_code == 200
    initial_status = response.json()
    initial_pid = initial_status.get("pid")

    # Restart service
    response = await client.post(
        "/api/services/redis/restart",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 200
    restart_result = response.json()
    assert restart_result["success"] is True
    assert restart_result["new_status"] == "running"

    # Verify new PID (process restarted)
    response = await client.get("/api/services/redis/status")
    assert response.status_code == 200
    new_status = response.json()
    new_pid = new_status.get("pid")

    assert new_pid != initial_pid, "PID should change after restart"
    assert new_status["status"] == "running"
```

### 10.3 End-to-End Tests

**Test Scenarios:**

1. **UI Service Control:**
   - User logs in → Navigates to service management → Clicks restart → Confirms → Verifies success notification → Checks service status updated

2. **Auto-Recovery UI:**
   - Admin stops Redis manually on VM → UI shows service down → Auto-recovery triggers → UI shows recovery in progress → Service status updates to healthy

3. **Permission Workflows:**
   - Operator logs in → Attempts to stop service → Sees permission denied → Contacts admin → Admin stops service → Operator sees service stopped

**Example E2E Test (Playwright):**

```javascript
test('Admin can restart Redis service from UI', async ({ page }) => {
  // Login as admin
  await page.goto('http://172.16.168.21:5173/login');
  await page.fill('[name="email"]', 'admin@autobot.local');
  await page.fill('[name="password"]', 'admin-password');
  await page.click('button[type="submit"]');

  // Navigate to service management
  await page.click('text=Services');
  await page.click('text=Redis Service');

  // Verify service is running
  await expect(page.locator('.service-status')).toContainText('running');

  // Click restart button
  await page.click('button:has-text("Restart")');

  // Confirm in dialog
  await page.click('button:has-text("Confirm")');

  // Wait for operation to complete
  await page.waitForSelector('.notification:has-text("restarted successfully")');

  // Verify service status still running
  await expect(page.locator('.service-status')).toContainText('running');
});
```

### 10.4 Performance Tests

**Performance Metrics:**

| Operation | Target | Maximum | Measurement |
|-----------|--------|---------|-------------|
| Service Start | < 15s | 30s | Time to healthy status |
| Service Stop | < 10s | 20s | Time to stopped status |
| Service Restart | < 20s | 40s | Time to healthy status |
| Status Query | < 100ms | 500ms | API response time |
| Health Check | < 2s | 5s | Complete check duration |
| Auto-Recovery | < 30s | 60s | Time to recovery completion |

**Load Testing:**

```python
import asyncio
import time
from httpx import AsyncClient

async def load_test_status_endpoint(duration_seconds: int = 60):
    """Load test status endpoint for sustained period"""

    client = AsyncClient(base_url="http://172.16.168.20:8001")

    request_count = 0
    error_count = 0
    total_duration = 0

    start_time = time.time()
    end_time = start_time + duration_seconds

    while time.time() < end_time:
        request_start = time.time()

        try:
            response = await client.get("/api/services/redis/status")
            request_duration = time.time() - request_start

            if response.status_code == 200:
                request_count += 1
                total_duration += request_duration
            else:
                error_count += 1

        except Exception as e:
            error_count += 1

        # Maintain rate of 10 requests/second
        await asyncio.sleep(0.1)

    # Calculate metrics
    avg_response_time = total_duration / request_count if request_count > 0 else 0
    error_rate = error_count / (request_count + error_count)

    print(f"Load Test Results ({duration_seconds}s):")
    print(f"  Requests: {request_count}")
    print(f"  Errors: {error_count}")
    print(f"  Error Rate: {error_rate:.2%}")
    print(f"  Avg Response Time: {avg_response_time*1000:.2f}ms")

    # Assertions
    assert error_rate < 0.01, "Error rate must be < 1%"
    assert avg_response_time < 0.5, "Avg response time must be < 500ms"
```

---

## Appendix A: Configuration Reference

### Complete Configuration Example

```yaml
# config/services/redis_service_management.yaml

redis_service_management:
  # Service Configuration
  service:
    name: "redis-server"
    systemd_unit: "redis-server.service"
    host: "redis"  # Reference to SSH host config
    ip: "172.16.168.23"
    port: 6379

  # Health Monitoring
  health_check:
    enabled: true
    interval_seconds: 30
    timeout_seconds: 5
    failure_threshold: 3  # Consecutive failures before action

    checks:
      connectivity:
        enabled: true
        command: "redis-cli -h 172.16.168.23 PING"
        expected_output: "PONG"

      systemd:
        enabled: true
        command: "systemctl is-active redis-server"
        expected_output: "active"

      performance:
        enabled: true
        thresholds:
          memory_mb_warning: 3072
          memory_mb_critical: 4096
          cpu_percent_warning: 70
          cpu_percent_critical: 90
          connections_warning: 8000
          connections_critical: 9500

  # Auto-Recovery Configuration
  auto_recovery:
    enabled: true
    max_attempts: 3
    retry_delay_seconds: 10
    backoff_multiplier: 2  # Exponential backoff

    strategies:
      soft:
        enabled: true
        command: "sudo systemctl reload redis-server"
        timeout_seconds: 10

      standard:
        enabled: true
        command: "sudo systemctl start redis-server"
        timeout_seconds: 30

      hard:
        enabled: true
        command: "sudo systemctl restart redis-server"
        timeout_seconds: 45

    notifications:
      on_recovery_start: true
      on_recovery_success: true
      on_recovery_failure: true
      on_manual_intervention_required: true

    circuit_breaker:
      enabled: true
      failure_threshold: 5
      timeout_seconds: 300  # 5 minutes
      half_open_attempts: 1

  # Service Control
  service_control:
    operation_timeout_seconds: 30
    require_confirmation_for_stop: true
    confirmation_timeout_seconds: 60

    allowed_operations:
      - start
      - stop
      - restart
      - status
      - reload

    commands:
      start: "sudo systemctl start redis-server"
      stop: "sudo systemctl stop redis-server"
      restart: "sudo systemctl restart redis-server"
      status: "systemctl status redis-server"
      reload: "sudo systemctl reload redis-server"
      logs: "journalctl -u redis-server -n {lines} --no-pager"

  # Permissions (RBAC)
  permissions:
    start:
      - admin
      - operator
    stop:
      - admin
    restart:
      - admin
      - operator
    status:
      - admin
      - operator
      - viewer
      - anonymous
    health:
      - admin
      - operator
      - viewer
      - anonymous
    logs:
      - admin

  # Audit Logging
  audit:
    enabled: true
    log_file: "logs/audit/redis_service_management.log"
    log_level: "INFO"
    include_command_output: false
    include_user_details: true
    rotate_logs: true
    max_log_size_mb: 100
    backup_count: 10

  # Status Caching
  cache:
    enabled: true
    ttl_seconds: 10
    invalidate_on_operation: true

  # WebSocket Notifications
  websocket:
    enabled: true
    endpoint: "/ws/services/redis/status"
    broadcast_status_changes: true
    broadcast_health_changes: true
    broadcast_operations: true
    broadcast_auto_recovery: true

  # Alerting
  alerts:
    enabled: true

    channels:
      websocket: true
      email: true
      sms: false  # Requires SMS gateway configuration

    severity_levels:
      critical:
        - service_down
        - recovery_failed
        - manual_intervention_required
      warning:
        - auto_recovery_attempted
        - performance_degraded
      info:
        - service_restarted
        - health_check_passed

    recipients:
      critical:
        - admin@autobot.local
      warning:
        - operator@autobot.local
        - admin@autobot.local
      info: []

  # Degraded Mode
  degraded_mode:
    enabled: true
    fallback_cache: true
    memory_sessions: true
    broadcast_status: true
    show_banner: true
```

---

## Appendix B: API Endpoint Summary

| Method | Endpoint | Description | Auth | Roles |
|--------|----------|-------------|------|-------|
| POST | /api/services/redis/start | Start Redis service | Required | admin, operator |
| POST | /api/services/redis/stop | Stop Redis service | Required | admin |
| POST | /api/services/redis/restart | Restart Redis service | Required | admin, operator |
| GET | /api/services/redis/status | Get service status | Optional | All |
| GET | /api/services/redis/health | Get health status | Optional | All |
| GET | /api/services/redis/logs | Get service logs | Required | admin |
| WS | /ws/services/redis/status | Real-time status updates | Required | All |

---

## Appendix C: Implementation Checklist

### Backend Implementation

- [ ] Create `RedisServiceManager` core service
  - [ ] Service control methods (start/stop/restart)
  - [ ] Health check methods
  - [ ] Auto-recovery orchestration
  - [ ] Status caching
  - [ ] Event emission

- [ ] Create `ServiceManagementRouter` API
  - [ ] POST /start endpoint
  - [ ] POST /stop endpoint
  - [ ] POST /restart endpoint
  - [ ] GET /status endpoint
  - [ ] GET /health endpoint
  - [ ] GET /logs endpoint

- [ ] Integrate with existing systems
  - [ ] SSHManager integration
  - [ ] ConsolidatedHealthService registration
  - [ ] Audit logging setup
  - [ ] WebSocket notifications

- [ ] Implement health monitoring
  - [ ] Connectivity checker
  - [ ] Systemd status checker
  - [ ] Performance metrics collector
  - [ ] Background monitoring task

- [ ] Implement auto-recovery
  - [ ] Recovery strategies (soft/standard/hard)
  - [ ] Circuit breaker
  - [ ] Retry logic with exponential backoff
  - [ ] Recovery failure alerting

- [ ] Security implementation
  - [ ] RBAC permission enforcement
  - [ ] Command validation and whitelisting
  - [ ] Audit logging
  - [ ] SSH key management

### Frontend Implementation

- [ ] Create UI components
  - [ ] RedisServiceControl.vue
  - [ ] ServiceStatusBadge.vue
  - [ ] ServiceLogsViewer.vue
  - [ ] ConfirmDialog.vue

- [ ] Create composables
  - [ ] useServiceManagement.js

- [ ] Create services
  - [ ] RedisServiceAPI.js

- [ ] WebSocket integration
  - [ ] Subscribe to status updates
  - [ ] Handle service events
  - [ ] Handle auto-recovery notifications

- [ ] UI/UX implementation
  - [ ] Status display and badges
  - [ ] Control buttons (start/stop/restart)
  - [ ] Confirmation dialogs
  - [ ] Error notifications
  - [ ] Health status display
  - [ ] Logs viewer

### Infrastructure Setup

- [ ] Redis VM configuration
  - [ ] Create sudoers file for autobot user
  - [ ] Verify SSH key authentication
  - [ ] Test systemctl commands

- [ ] Monitoring setup
  - [ ] Configure health check intervals
  - [ ] Set up audit log rotation
  - [ ] Configure alerting channels

- [ ] Documentation
  - [ ] API documentation
  - [ ] User guide
  - [ ] Operational runbook
  - [ ] Security policies

### Testing

- [ ] Unit tests
  - [ ] RedisServiceManager tests
  - [ ] API endpoint tests
  - [ ] Health monitor tests

- [ ] Integration tests
  - [ ] End-to-end service control flow
  - [ ] Auto-recovery scenarios
  - [ ] WebSocket notifications
  - [ ] Permission enforcement

- [ ] E2E tests
  - [ ] UI service control workflows
  - [ ] Auto-recovery UI updates
  - [ ] Permission workflows

- [ ] Performance tests
  - [ ] Load testing status endpoint
  - [ ] Service operation timing
  - [ ] Health check performance

### Deployment

- [ ] Deploy backend changes
  - [ ] Update backend API on main machine
  - [ ] Restart backend service

- [ ] Deploy frontend changes
  - [ ] Sync frontend to VM1
  - [ ] Restart frontend service

- [ ] Configure Redis VM
  - [ ] Deploy sudoers configuration
  - [ ] Verify permissions

- [ ] Verify deployment
  - [ ] Test all API endpoints
  - [ ] Test UI functionality
  - [ ] Verify auto-recovery
  - [ ] Check audit logs

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-10 | Claude (Systems Architect) | Initial architecture document |

---

**End of Document**
