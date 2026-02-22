# Redis Service Management Implementation - Comprehensive Task List

**Document Version:** 1.0
**Created:** 2025-10-10
**Architecture Reference:** [`docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md`](../../docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md)
**Priority:** HIGH (User-Requested Feature)

---

## Executive Summary

This document breaks down the Redis Service Management architecture into concrete, actionable implementation tasks. The architecture is organized into 5 phases focusing on building an MVP first, then adding advanced features.

**User Requirements:**
1. Frontend UI control to start/stop/restart Redis service
2. Backend auto-detection and auto-start when Redis service stops
3. Real-time status updates and monitoring
4. Secure, auditable operations

**Implementation Strategy:**
- **Phase 1:** Core infrastructure (service manager + API endpoints) - MVP Foundation
- **Phase 2:** Auto-recovery system (health monitoring + recovery) - MVP Complete
- **Phase 3:** Frontend integration (UI components + real-time updates)
- **Phase 4:** Security hardening (RBAC + audit + sudoers)
- **Phase 5:** Comprehensive testing

---

## Task Organization

**Task ID Format:** `REDIS-<Phase>.<Section>.<Number>`

**Complexity Estimates:**
- **Simple:** < 2 hours, straightforward implementation, minimal dependencies
- **Medium:** 2-6 hours, moderate complexity, some dependencies
- **Complex:** 6+ hours, high complexity, multiple dependencies

**Priority Levels:**
- **P0 (Critical):** MVP blocker, must complete for basic functionality
- **P1 (High):** Important for production use, should complete soon
- **P2 (Medium):** Nice to have, can be deferred
- **P3 (Low):** Future enhancement, optional

---

## Phase 1: Core Infrastructure (Week 1, Days 1-3)

**Objective:** Build RedisServiceManager service and basic API endpoints for service control

### 1.1 Backend Core Service

#### REDIS-1.1.1: Create RedisServiceManager Service Class
**Description:** Implement core service class for Redis lifecycle management

**Affected Files:**
- **CREATE:** `backend/services/redis_service_manager.py`

**Dependencies:** None

**Complexity:** Medium

**Priority:** P0 (Critical - MVP Foundation)

**Acceptance Criteria:**
- [ ] Service class created with proper initialization
- [ ] Configuration loading from YAML (uses existing config system)
- [ ] Integration with existing SSHManager for remote commands
- [ ] Basic logging and error handling
- [ ] Singleton pattern or dependency injection setup

**Implementation Notes:**
```python
# Key methods to implement:
class RedisServiceManager:
    def __init__(self, ssh_manager: SSHManager, config: dict)
    async def start_service(self, user_id: str) -> ServiceOperationResult
    async def stop_service(self, user_id: str) -> ServiceOperationResult
    async def restart_service(self, user_id: str) -> ServiceOperationResult
    async def get_service_status(self) -> ServiceStatus
```

---

#### REDIS-1.1.2: Implement Service Control Methods
**Description:** Implement start/stop/restart operations using systemctl via SSH

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.1

**Complexity:** Medium

**Priority:** P0 (Critical - MVP Core)

**Acceptance Criteria:**
- [ ] `start_service()` executes `sudo systemctl start redis-server`
- [ ] `stop_service()` executes `sudo systemctl stop redis-server` with confirmation check
- [ ] `restart_service()` executes `sudo systemctl restart redis-server`
- [ ] All methods use SSHManager.execute_command() with proper timeout
- [ ] Return structured ServiceOperationResult with success/failure details
- [ ] Command validation via SecureCommandExecutor integration
- [ ] Proper error handling for SSH failures, timeouts, command failures

**Implementation Notes:**
```python
# Use existing SSHManager:
result = await self.ssh_manager.execute_command(
    host='redis',
    command='sudo systemctl start redis-server',
    timeout=30,
    validate=True
)
```

---

#### REDIS-1.1.3: Implement Service Status Check
**Description:** Query current Redis service status via systemctl

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.1

**Complexity:** Simple

**Priority:** P0 (Critical - MVP Core)

**Acceptance Criteria:**
- [ ] `get_service_status()` queries systemctl status and Redis connection
- [ ] Parse systemd output to extract: PID, uptime, memory usage, active/inactive state
- [ ] Test Redis connectivity via PING command
- [ ] Return ServiceStatus with all relevant fields populated
- [ ] Cache status with 10-second TTL to reduce SSH overhead
- [ ] Handle cases where service is stopped, failed, or unreachable

**Implementation Notes:**
```python
# Commands to execute:
# 1. systemctl is-active redis-server
# 2. systemctl status redis-server
# 3. redis-cli -h 172.16.168.23 PING
```

---

### 1.2 API Endpoints

#### REDIS-1.2.1: Create Service Management Router
**Description:** Create FastAPI router with service control endpoints

**Affected Files:**
- **CREATE:** `autobot-user-backend/api/service_management.py`
- **MODIFY:** `backend/app_factory_enhanced.py` (register router)

**Dependencies:** REDIS-1.1.1, REDIS-1.1.2, REDIS-1.1.3

**Complexity:** Medium

**Priority:** P0 (Critical - MVP API)

**Acceptance Criteria:**
- [ ] Router created with prefix `/api/services/redis`
- [ ] POST `/start` endpoint implemented
- [ ] POST `/stop` endpoint implemented (with confirmation parameter)
- [ ] POST `/restart` endpoint implemented
- [ ] GET `/status` endpoint implemented
- [ ] GET `/health` endpoint implemented (basic health check)
- [ ] All endpoints use dependency injection for RedisServiceManager
- [ ] Proper HTTP status codes and error responses
- [ ] Router registered in FastAPI app factory

**Implementation Notes:**
```python
router = APIRouter(prefix="/api/services/redis", tags=["Service Management"])

@router.post("/start")
async def start_redis_service(
    service_manager: RedisServiceManager = Depends(get_redis_service_manager),
    current_user: User = Depends(get_current_user)
) -> ServiceOperationResponse:
    pass
```

---

#### REDIS-1.2.2: Implement Pydantic Response Models
**Description:** Create response models for API endpoints

**Affected Files:**
- **CREATE:** `backend/models/service_management.py`

**Dependencies:** None

**Complexity:** Simple

**Priority:** P0 (Critical - MVP API)

**Acceptance Criteria:**
- [ ] ServiceOperationResponse model (success, operation, message, duration, timestamp, new_status)
- [ ] ServiceStatusResponse model (status, pid, uptime, memory, connections, last_check)
- [ ] HealthStatusResponse model (overall_status, service_running, connectivity, response_time, error_count, recommendations)
- [ ] All models use proper Pydantic typing with validation
- [ ] Models match architecture specification exactly

---

#### REDIS-1.2.3: Implement Service Manager Dependency Injection
**Description:** Setup dependency injection for RedisServiceManager in FastAPI

**Affected Files:**
- **CREATE:** `backend/dependencies/services.py` (or extend existing)
- **MODIFY:** `backend/app_factory_enhanced.py` (setup DI)

**Dependencies:** REDIS-1.1.1

**Complexity:** Simple

**Priority:** P0 (Critical - MVP Infrastructure)

**Acceptance Criteria:**
- [ ] Dependency function `get_redis_service_manager()` created
- [ ] Singleton instance management (one manager per application)
- [ ] Proper initialization with SSHManager and config
- [ ] Lifecycle management (startup/shutdown hooks)
- [ ] Available for injection in API endpoints

**Implementation Notes:**
```python
_redis_service_manager: Optional[RedisServiceManager] = None

async def get_redis_service_manager() -> RedisServiceManager:
    global _redis_service_manager
    if _redis_service_manager is None:
        ssh_manager = get_ssh_manager()
        config = load_service_config()
        _redis_service_manager = RedisServiceManager(ssh_manager, config)
    return _redis_service_manager
```

---

### 1.3 Configuration & Integration

#### REDIS-1.3.1: Create Service Management Configuration
**Description:** Define configuration structure for Redis service management

**Affected Files:**
- **CREATE:** `config/services/redis_service_management.yaml`
- **MODIFY:** `config/config.yaml` (reference new config file)

**Dependencies:** None

**Complexity:** Simple

**Priority:** P0 (Critical - MVP Configuration)

**Acceptance Criteria:**
- [ ] Configuration file with all settings from architecture (health check intervals, timeouts, recovery settings)
- [ ] Service connection details (host, port, SSH config)
- [ ] Operation timeouts and retry settings
- [ ] Permission mappings (admin, operator, viewer roles)
- [ ] Sensible defaults for all settings
- [ ] Configuration validation on load

**Configuration Structure:**
```yaml
redis_service_management:
  service:
    name: "redis-server"
    systemd_unit: "redis-server.service"
    host: "redis"
    ip: "172.16.168.23"
    port: 6379

  health_check:
    enabled: true
    interval_seconds: 30
    timeout_seconds: 5
    failure_threshold: 3

  auto_recovery:
    enabled: true
    max_attempts: 3
    retry_delay_seconds: 10

  service_control:
    operation_timeout_seconds: 30
    require_confirmation_for_stop: true

  permissions:
    start: ["admin", "operator"]
    stop: ["admin"]
    restart: ["admin", "operator"]
```

---

#### REDIS-1.3.2: Integrate with ConsolidatedHealthService
**Description:** Register Redis service management health checker

**Affected Files:**
- **MODIFY:** `backend/services/consolidated_health_service.py`
- **MODIFY:** `backend/services/redis_service_manager.py` (add health check method)

**Dependencies:** REDIS-1.1.1, REDIS-1.1.3

**Complexity:** Simple

**Priority:** P1 (High - Monitoring Integration)

**Acceptance Criteria:**
- [ ] Health check function for service management component
- [ ] Returns health status: healthy/degraded/unhealthy
- [ ] Includes service status and auto-recovery status
- [ ] Registered with ConsolidatedHealthService
- [ ] Appears in `/api/health` endpoint

**Implementation Notes:**
```python
async def check_redis_service_management_health():
    service_manager = get_redis_service_manager()
    status = await service_manager.get_service_status()
    return {
        "status": "healthy" if status.status == "running" else "degraded",
        "component": "redis_service_management",
        "service_status": status.status,
        "timestamp": datetime.now().isoformat()
    }

consolidated_health.register_component(
    "redis_service_management",
    check_redis_service_management_health
)
```

---

#### REDIS-1.3.3: Setup Audit Logging Integration
**Description:** Integrate service management operations with audit logging system

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`
- **MODIFY:** `backend/services/audit_logger.py` (if needed)

**Dependencies:** REDIS-1.1.2

**Complexity:** Simple

**Priority:** P1 (High - Security/Compliance)

**Acceptance Criteria:**
- [ ] All service operations logged to audit system
- [ ] Audit entries include: timestamp, user_id, operation, success/failure, duration
- [ ] Uses existing AuditLogger service
- [ ] Separate log file: `logs/audit/redis_service_management.log`
- [ ] Audit logs rotated automatically

**Implementation Notes:**
```python
# After every service operation:
await self.audit_logger.log_event(
    event_type='redis_service_operation',
    user_id=user_id,
    operation=operation,
    success=result.success,
    details={
        'duration_seconds': result.duration_seconds,
        'new_status': result.new_status
    }
)
```

---

### 1.4 Testing (Phase 1)

#### REDIS-1.4.1: Unit Tests for RedisServiceManager
**Description:** Comprehensive unit tests for service manager

**Affected Files:**
- **CREATE:** `tests/unit/services/test_redis_service_manager.py`

**Dependencies:** REDIS-1.1.1, REDIS-1.1.2, REDIS-1.1.3

**Complexity:** Medium

**Priority:** P1 (High - Quality Assurance)

**Acceptance Criteria:**
- [ ] Test start_service() with mocked SSHManager
- [ ] Test stop_service() with mocked SSHManager
- [ ] Test restart_service() with mocked SSHManager
- [ ] Test get_service_status() with various systemd outputs
- [ ] Test error handling (SSH failures, timeouts, command failures)
- [ ] Test status caching logic
- [ ] 80%+ code coverage for service manager

**Test Structure:**
```python
@pytest.mark.asyncio
async def test_start_service_when_stopped():
    # Mock SSH manager
    # Execute start_service()
    # Assert command executed correctly
    # Assert result success
    pass

@pytest.mark.asyncio
async def test_stop_service_requires_confirmation():
    pass
```

---

#### REDIS-1.4.2: Unit Tests for API Endpoints
**Description:** Unit tests for service management API

**Affected Files:**
- **CREATE:** `tests/unit/api/test_service_management.py`

**Dependencies:** REDIS-1.2.1

**Complexity:** Medium

**Priority:** P1 (High - Quality Assurance)

**Acceptance Criteria:**
- [ ] Test POST /start endpoint (success case)
- [ ] Test POST /stop endpoint (with/without confirmation)
- [ ] Test POST /restart endpoint (success case)
- [ ] Test GET /status endpoint
- [ ] Test GET /health endpoint
- [ ] Test error responses (400, 403, 500)
- [ ] Test authentication/authorization (if implemented)
- [ ] 80%+ code coverage for API endpoints

---

#### REDIS-1.4.3: Integration Test - End-to-End Service Control
**Description:** Integration test for complete service control flow

**Affected Files:**
- **CREATE:** `tests/integration/test_redis_service_management_integration.py`

**Dependencies:** REDIS-1.2.1, REDIS-1.1.2

**Complexity:** Medium

**Priority:** P1 (High - Integration Validation)

**Acceptance Criteria:**
- [ ] Test: API call → RedisServiceManager → SSHManager → VM3 systemctl
- [ ] Test service start via API (verify service actually starts on VM3)
- [ ] Test service restart via API (verify PID changes)
- [ ] Test service status query (verify accurate status)
- [ ] Tests run against test environment (not production)
- [ ] Tests cleanup after themselves (restore service state)

**Test Requirements:**
```python
@pytest.mark.integration
@pytest.mark.requires_vm_access
async def test_full_service_restart_flow(test_client, admin_auth_token):
    # Get initial status
    # Restart via API
    # Verify service restarted
    # Check new PID different from old PID
    pass
```

---

**Phase 1 Summary:**
- **Total Tasks:** 13
- **P0 (Critical):** 10 tasks
- **P1 (High):** 3 tasks
- **Estimated Duration:** 3-4 days
- **MVP Deliverable:** Basic service control via API endpoints ✅

---

## Phase 2: Auto-Recovery System (Week 1-2, Days 4-7)

**Objective:** Implement background health monitoring and automated service recovery

### 2.1 Health Monitoring

#### REDIS-2.1.1: Implement Connectivity Health Checker
**Description:** Health checker for Redis connectivity via PING

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py` (add health checker class)

**Dependencies:** REDIS-1.1.3

**Complexity:** Simple

**Priority:** P0 (Critical - Auto-Recovery Foundation)

**Acceptance Criteria:**
- [ ] ConnectionHealthChecker class with async check method
- [ ] Executes `redis-cli -h 172.16.168.23 PING` via SSH
- [ ] Measures response time in milliseconds
- [ ] Returns HealthCheckResult (status, layer, response_time, error)
- [ ] Timeout handling (5 seconds max)
- [ ] Connection failure detection

**Implementation Notes:**
```python
class ConnectionHealthChecker:
    async def check(self) -> HealthCheckResult:
        start_time = time.time()
        try:
            result = await ssh_manager.execute_command(
                host='redis',
                command='redis-cli -h 172.16.168.23 PING',
                timeout=5
            )
            response_time = (time.time() - start_time) * 1000

            if result.success and 'PONG' in result.stdout:
                return HealthCheckResult(status="healthy", layer="connectivity", response_time_ms=response_time)
            else:
                return HealthCheckResult(status="failed", layer="connectivity", message="PING failed")
        except Exception as e:
            return HealthCheckResult(status="failed", layer="connectivity", error=str(e))
```

---

#### REDIS-2.1.2: Implement Systemd Health Checker
**Description:** Health checker for systemd service status

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.3

**Complexity:** Simple

**Priority:** P0 (Critical - Auto-Recovery Foundation)

**Acceptance Criteria:**
- [ ] SystemdHealthChecker class with async check method
- [ ] Executes `systemctl is-active redis-server` and `systemctl status redis-server`
- [ ] Parses output to determine service state (active, inactive, failed, unknown)
- [ ] Extracts process PID and uptime if available
- [ ] Returns HealthCheckResult with systemd layer info
- [ ] Handles all systemd service states correctly

---

#### REDIS-2.1.3: Implement Performance Health Checker
**Description:** Health checker for Redis performance metrics

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.3

**Complexity:** Medium

**Priority:** P1 (High - Advanced Monitoring)

**Acceptance Criteria:**
- [ ] PerformanceHealthChecker class with async check method
- [ ] Executes `redis-cli INFO` to get performance metrics
- [ ] Extracts: memory usage, connection count, CPU usage
- [ ] Compares against thresholds (configurable)
- [ ] Returns "healthy", "degraded", or "warning" status
- [ ] Includes recommendations for degraded performance

**Metrics Thresholds:**
```yaml
thresholds:
  memory_mb_warning: 3072
  memory_mb_critical: 4096
  cpu_percent_warning: 70
  cpu_percent_critical: 90
  connections_warning: 8000
  connections_critical: 9500
```

---

#### REDIS-2.1.4: Implement Comprehensive Health Check
**Description:** Multi-layer health check orchestration

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-2.1.1, REDIS-2.1.2, REDIS-2.1.3

**Complexity:** Medium

**Priority:** P0 (Critical - Auto-Recovery Core)

**Acceptance Criteria:**
- [ ] `check_health()` method executes all health checkers in sequence
- [ ] Layer 1: Connectivity (fastest, fails fast)
- [ ] Layer 2: Systemd status (moderate speed)
- [ ] Layer 3: Performance metrics (slowest)
- [ ] Aggregates results into overall health status
- [ ] Short-circuit on critical failures (don't continue if service down)
- [ ] Returns comprehensive HealthStatus with all layer results

**Health Status Logic:**
```python
async def check_health(self) -> HealthStatus:
    # Layer 1: Connectivity
    conn_result = await self.connectivity_checker.check()
    if conn_result.status == "failed":
        return HealthStatus(overall_status="critical", layers=[conn_result])

    # Layer 2: Systemd
    systemd_result = await self.systemd_checker.check()
    if systemd_result.status == "failed":
        return HealthStatus(overall_status="critical", layers=[conn_result, systemd_result])

    # Layer 3: Performance
    perf_result = await self.performance_checker.check()

    # Aggregate
    overall = self._determine_overall_status([conn_result, systemd_result, perf_result])
    return HealthStatus(overall_status=overall, layers=[...])
```

---

#### REDIS-2.1.5: Implement Background Health Monitor Task
**Description:** Async background task for continuous health monitoring

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`
- **MODIFY:** `backend/app_factory_enhanced.py` (register background task)

**Dependencies:** REDIS-2.1.4

**Complexity:** Medium

**Priority:** P0 (Critical - Auto-Recovery Trigger)

**Acceptance Criteria:**
- [ ] Background async task `_monitor_health_loop()`
- [ ] Runs continuously every 30 seconds (configurable)
- [ ] Executes comprehensive health check
- [ ] Tracks consecutive failures (failure threshold: 3)
- [ ] Triggers auto-recovery when threshold exceeded
- [ ] Proper exception handling (doesn't crash on errors)
- [ ] Graceful shutdown on application stop
- [ ] Registered as FastAPI background task

**Implementation Notes:**
```python
async def _monitor_health_loop(self):
    """Background task: continuous health monitoring"""
    while True:
        try:
            health_result = await self.check_health()

            if health_result.overall_status in ["critical", "failed"]:
                self.consecutive_failures += 1
                logger.warning(f"Redis health check failed ({self.consecutive_failures}/{self.failure_threshold})")

                if self.consecutive_failures >= self.failure_threshold:
                    logger.error("Failure threshold exceeded, triggering auto-recovery")
                    await self.auto_recover()
            else:
                # Reset failure counter on success
                self.consecutive_failures = 0

            await asyncio.sleep(self.config.health_check_interval)

        except Exception as e:
            logger.error(f"Health monitor exception: {e}")
            await asyncio.sleep(10)  # Backoff on errors
```

---

### 2.2 Auto-Recovery System

#### REDIS-2.2.1: Implement Soft Recovery Strategy
**Description:** Level 1 recovery - reload service configuration

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.2

**Complexity:** Simple

**Priority:** P1 (High - Recovery Strategy)

**Acceptance Criteria:**
- [ ] `_soft_recovery()` method sends SIGHUP to Redis process
- [ ] Executes `sudo systemctl reload redis-server` or `kill -HUP <pid>`
- [ ] Waits for service to respond (max 10 seconds)
- [ ] Returns RecoveryResult with success/failure and strategy used
- [ ] Logs recovery attempt and result
- [ ] Used when service running but not responding

---

#### REDIS-2.2.2: Implement Standard Recovery Strategy
**Description:** Level 2 recovery - start stopped service

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.2

**Complexity:** Simple

**Priority:** P0 (Critical - Primary Recovery)

**Acceptance Criteria:**
- [ ] `_standard_recovery()` executes `sudo systemctl start redis-server`
- [ ] Waits for service to start (max 30 seconds)
- [ ] Verifies service health after start
- [ ] Returns RecoveryResult with success/failure
- [ ] Used when service simply stopped (most common case)

---

#### REDIS-2.2.3: Implement Hard Recovery Strategy
**Description:** Level 3 recovery - restart failed service

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.2

**Complexity:** Simple

**Priority:** P0 (Critical - Failure Recovery)

**Acceptance Criteria:**
- [ ] `_hard_recovery()` executes `sudo systemctl restart redis-server`
- [ ] Waits for service to restart (max 45 seconds)
- [ ] Verifies service health after restart
- [ ] Returns RecoveryResult with success/failure
- [ ] Used when service in failed state

---

#### REDIS-2.2.4: Implement Recovery Orchestration
**Description:** Main auto-recovery logic with strategy selection

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-2.2.1, REDIS-2.2.2, REDIS-2.2.3

**Complexity:** Complex

**Priority:** P0 (Critical - Auto-Recovery Core)

**Acceptance Criteria:**
- [ ] `auto_recover()` method implements recovery decision tree
- [ ] Checks if auto-recovery enabled in config
- [ ] Enforces max attempts limit (default: 3)
- [ ] Selects recovery strategy based on service state:
  - Service running but not responding → Soft recovery
  - Service stopped → Standard recovery
  - Service failed → Hard recovery
- [ ] Implements exponential backoff between retry attempts
- [ ] Resets attempt counter on successful recovery
- [ ] Sends critical alert if all attempts exhausted
- [ ] Disables auto-recovery after max failures (requires manual intervention)

**Recovery Decision Tree:**
```python
async def auto_recover(self) -> RecoveryResult:
    if not self.config.auto_recovery.enabled:
        return RecoveryResult(success=False, reason="Auto-recovery disabled")

    if self.recovery_attempts >= self.config.auto_recovery.max_attempts:
        await self._send_critical_alert("Max recovery attempts exceeded")
        return RecoveryResult(success=False, requires_manual_intervention=True)

    self.recovery_attempts += 1

    # Determine current service state
    status = await self._get_systemd_status()

    if status.is_running:
        result = await self._soft_recovery()
    elif status.is_failed:
        result = await self._hard_recovery()
    else:
        result = await self._standard_recovery()

    if result.success:
        self.recovery_attempts = 0
        await self._send_recovery_notification(f"Recovered using {result.strategy}")
        return result

    # Recovery failed, wait before retry
    await asyncio.sleep(self.config.auto_recovery.retry_delay_seconds * (2 ** (self.recovery_attempts - 1)))

    # Escalate to next level if more attempts available
    if self.recovery_attempts < self.config.auto_recovery.max_attempts:
        return await self._escalate_recovery(result)

    await self._send_critical_alert(f"All recovery attempts failed: {result.error}")
    return RecoveryResult(success=False, requires_manual_intervention=True)
```

---

#### REDIS-2.2.5: Implement Circuit Breaker Pattern
**Description:** Circuit breaker to prevent recovery loops

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-2.2.4

**Complexity:** Medium

**Priority:** P1 (High - Safety Mechanism)

**Acceptance Criteria:**
- [ ] ServiceOperationCircuitBreaker class implementation
- [ ] Three states: closed (normal), open (blocked), half-open (testing)
- [ ] Opens circuit after 5 consecutive failures
- [ ] Remains open for 5 minutes (configurable timeout)
- [ ] Transitions to half-open to test recovery
- [ ] Closes circuit on successful operation in half-open state
- [ ] Blocks all service operations when circuit open
- [ ] Logs circuit state transitions

**Circuit Breaker States:**
- **Closed:** Normal operation, operations allowed
- **Open:** Too many failures, operations blocked (prevents damage)
- **Half-Open:** Testing if service recovered, limited operations allowed

---

#### REDIS-2.2.6: Implement Recovery Loop Detection
**Description:** Detect and prevent infinite recovery loops

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-2.2.4

**Complexity:** Medium

**Priority:** P1 (High - Safety Mechanism)

**Acceptance Criteria:**
- [ ] Track recovery attempts with timestamps
- [ ] Detect recovery loop: 3+ recoveries within 5 minutes
- [ ] Disable auto-recovery when loop detected
- [ ] Send critical alert with diagnostic information
- [ ] Capture diagnostic snapshot: logs, config, recent changes
- [ ] Require manual intervention to re-enable auto-recovery

---

### 2.3 Alerting & Notifications

#### REDIS-2.3.1: Implement Recovery Notification System
**Description:** Send notifications for recovery events

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`
- **MODIFY:** `autobot-user-backend/api/websockets.py` (WebSocket notifications)

**Dependencies:** REDIS-2.2.4

**Complexity:** Medium

**Priority:** P1 (High - User Awareness)

**Acceptance Criteria:**
- [ ] Send WebSocket notification on auto-recovery attempt
- [ ] Send WebSocket notification on recovery success
- [ ] Send WebSocket notification on recovery failure
- [ ] Notification format: type, service, status, message, timestamp
- [ ] Broadcast to all connected WebSocket clients
- [ ] Integration with existing WebSocket manager

**Notification Format:**
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

#### REDIS-2.3.2: Implement Critical Alert System
**Description:** Alert administrators for critical failures

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-2.2.4

**Complexity:** Medium

**Priority:** P1 (High - Critical Notifications)

**Acceptance Criteria:**
- [ ] Send alert when max recovery attempts exceeded
- [ ] Send alert when recovery loop detected
- [ ] Send alert when manual intervention required
- [ ] Alert channels: WebSocket, logging (email optional in future)
- [ ] Alert includes: diagnostic details, recommended actions, timestamp
- [ ] Alerts not rate-limited (critical alerts always sent)

---

### 2.4 Testing (Phase 2)

#### REDIS-2.4.1: Unit Tests for Health Checkers
**Description:** Unit tests for all health checker classes

**Affected Files:**
- **CREATE:** `tests/unit/services/test_redis_health_checkers.py`

**Dependencies:** REDIS-2.1.1, REDIS-2.1.2, REDIS-2.1.3, REDIS-2.1.4

**Complexity:** Medium

**Priority:** P1 (High - Quality Assurance)

**Acceptance Criteria:**
- [ ] Test ConnectionHealthChecker (success, timeout, connection refused)
- [ ] Test SystemdHealthChecker (active, inactive, failed states)
- [ ] Test PerformanceHealthChecker (healthy, degraded, critical)
- [ ] Test comprehensive health check aggregation
- [ ] 80%+ code coverage for health checkers

---

#### REDIS-2.4.2: Unit Tests for Auto-Recovery
**Description:** Unit tests for recovery strategies and orchestration

**Affected Files:**
- **CREATE:** `tests/unit/services/test_redis_auto_recovery.py`

**Dependencies:** REDIS-2.2.1, REDIS-2.2.2, REDIS-2.2.3, REDIS-2.2.4

**Complexity:** Complex

**Priority:** P1 (High - Quality Assurance)

**Acceptance Criteria:**
- [ ] Test soft recovery (service running but not responding)
- [ ] Test standard recovery (service stopped)
- [ ] Test hard recovery (service failed)
- [ ] Test recovery orchestration decision tree
- [ ] Test max attempts enforcement
- [ ] Test exponential backoff
- [ ] Test recovery loop detection
- [ ] Test circuit breaker behavior
- [ ] Mock all SSH commands and external dependencies
- [ ] 80%+ code coverage for auto-recovery

---

#### REDIS-2.4.3: Integration Test - Auto-Recovery Scenarios
**Description:** End-to-end auto-recovery integration tests

**Affected Files:**
- **CREATE:** `tests/integration/test_redis_auto_recovery_integration.py`

**Dependencies:** REDIS-2.2.4, REDIS-2.1.5

**Complexity:** Complex

**Priority:** P1 (High - Integration Validation)

**Acceptance Criteria:**
- [ ] Test: Stop Redis manually → Auto-recovery starts it
- [ ] Test: Kill Redis process → Auto-recovery restarts it
- [ ] Test: Verify recovery happens within 30 seconds (SLA)
- [ ] Test: Verify WebSocket notification sent
- [ ] Test: Verify audit log entry created
- [ ] Tests run against test environment
- [ ] Tests cleanup and restore service state

---

**Phase 2 Summary:**
- **Total Tasks:** 15
- **P0 (Critical):** 7 tasks
- **P1 (High):** 8 tasks
- **Estimated Duration:** 4-5 days
- **MVP Deliverable:** Auto-recovery system with health monitoring ✅

---

## Phase 3: Frontend Integration (Week 2, Days 8-10)

**Objective:** Build user interface for Redis service management with real-time updates

### 3.1 UI Components

#### REDIS-3.1.1: Create RedisServiceControl Component
**Description:** Main Vue component for Redis service management

**Affected Files:**
- **CREATE:** `autobot-user-frontend/src/components/services/RedisServiceControl.vue`

**Dependencies:** REDIS-1.2.1

**Complexity:** Complex

**Priority:** P0 (Critical - MVP UI)

**Acceptance Criteria:**
- [ ] Component displays current service status with badge
- [ ] Start/Stop/Restart buttons with proper state management
- [ ] Disabled states when service in transition or unavailable
- [ ] Service details: uptime, memory, connections (when running)
- [ ] Health status display with color indicators
- [ ] Auto-recovery status indicator
- [ ] Loading states during operations
- [ ] Error message display
- [ ] Responsive design (mobile-friendly)
- [ ] Follows AutoBot design system

**Component Structure:**
```vue
<template>
  <div class="redis-service-control">
    <div class="service-header">
      <h3>Redis Service</h3>
      <ServiceStatusBadge :status="serviceStatus.status" :loading="loading" />
    </div>

    <div class="service-details" v-if="serviceStatus.status === 'running'">
      <!-- Service metrics -->
    </div>

    <div class="service-controls">
      <button @click="startService" :disabled="isStartDisabled">Start</button>
      <button @click="restartService" :disabled="isRestartDisabled">Restart</button>
      <button @click="stopService" :disabled="isStopDisabled">Stop</button>
      <button @click="refreshStatus">Refresh</button>
    </div>

    <div class="health-status" v-if="healthStatus">
      <!-- Health details -->
    </div>
  </div>
</template>
```

---

#### REDIS-3.1.2: Create ServiceStatusBadge Component
**Description:** Reusable status badge component

**Affected Files:**
- **CREATE:** `autobot-user-frontend/src/components/services/ServiceStatusBadge.vue`

**Dependencies:** None

**Complexity:** Simple

**Priority:** P0 (Critical - MVP UI)

**Acceptance Criteria:**
- [ ] Badge component with status prop (running, stopped, failed, unknown)
- [ ] Color coding: green (running), red (stopped/failed), gray (unknown)
- [ ] Loading spinner when status unknown
- [ ] Icon for each status
- [ ] Tooltip with additional status info

---

#### REDIS-3.1.3: Create ServiceLogsViewer Component
**Description:** Component to view Redis service logs

**Affected Files:**
- **CREATE:** `autobot-user-frontend/src/components/services/ServiceLogsViewer.vue`

**Dependencies:** REDIS-1.2.1 (logs endpoint)

**Complexity:** Medium

**Priority:** P2 (Medium - Optional Enhancement)

**Acceptance Criteria:**
- [ ] Fetch and display recent service logs (50 lines default)
- [ ] Log level filtering (error, warning, info)
- [ ] Auto-refresh toggle
- [ ] Search/filter logs
- [ ] Syntax highlighting for log entries
- [ ] Timestamp display

---

#### REDIS-3.1.4: Create ConfirmDialog Component
**Description:** Reusable confirmation dialog for destructive operations

**Affected Files:**
- **CREATE:** `autobot-user-frontend/src/components/common/ConfirmDialog.vue` (or use existing)

**Dependencies:** None

**Complexity:** Simple

**Priority:** P0 (Critical - Safety)

**Acceptance Criteria:**
- [ ] Modal dialog with title, message, warning text
- [ ] Confirm and Cancel buttons
- [ ] Warning icon for destructive actions
- [ ] Keyboard shortcuts (Enter=confirm, Esc=cancel)
- [ ] Emits confirm/cancel events

---

### 3.2 Composables & Services

#### REDIS-3.2.1: Create useServiceManagement Composable
**Description:** Vue composable for service management logic

**Affected Files:**
- **CREATE:** `autobot-user-frontend/src/composables/useServiceManagement.js`

**Dependencies:** REDIS-1.2.1

**Complexity:** Medium

**Priority:** P0 (Critical - MVP Logic)

**Acceptance Criteria:**
- [ ] Reactive service status state
- [ ] Reactive health status state
- [ ] Loading state management
- [ ] `startService()` method
- [ ] `stopService()` method
- [ ] `restartService()` method
- [ ] `refreshStatus()` method
- [ ] Error handling with user notifications
- [ ] WebSocket subscription handling
- [ ] Cleanup on component unmount

**Composable Structure:**
```javascript
export function useServiceManagement(serviceName) {
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

  const refreshStatus = async () => { /* ... */ };
  const startService = async () => { /* ... */ };
  const stopService = async () => { /* ... */ };
  const restartService = async () => { /* ... */ };
  const subscribeToStatusUpdates = (callback) => { /* ... */ };

  onMounted(() => {
    refreshStatus();
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

#### REDIS-3.2.2: Create RedisServiceAPI Service
**Description:** API client for Redis service management

**Affected Files:**
- **CREATE:** `autobot-user-frontend/src/services/RedisServiceAPI.js`

**Dependencies:** REDIS-1.2.1

**Complexity:** Simple

**Priority:** P0 (Critical - MVP API Client)

**Acceptance Criteria:**
- [ ] `getStatus()` method → GET /api/services/redis/status
- [ ] `getHealth()` method → GET /api/services/redis/health
- [ ] `start()` method → POST /api/services/redis/start
- [ ] `stop(confirmation)` method → POST /api/services/redis/stop
- [ ] `restart()` method → POST /api/services/redis/restart
- [ ] `getLogs(lines)` method → GET /api/services/redis/logs
- [ ] Proper error handling
- [ ] Request timeout configuration
- [ ] Uses existing HTTP client utilities

**API Client Structure:**
```javascript
import api from '@/utils/api';

export default {
  async getStatus() {
    const response = await api.get('/api/services/redis/status');
    return response.data;
  },

  async start() {
    const response = await api.post('/api/services/redis/start');
    return response.data;
  },

  async stop(confirmation = false) {
    const response = await api.post('/api/services/redis/stop', { confirmation });
    return response.data;
  },

  async restart() {
    const response = await api.post('/api/services/redis/restart');
    return response.data;
  },

  async getHealth() {
    const response = await api.get('/api/services/redis/health');
    return response.data;
  },

  async getLogs(lines = 50) {
    const response = await api.get('/api/services/redis/logs', { params: { lines } });
    return response.data;
  }
};
```

---

### 3.3 WebSocket Integration

#### REDIS-3.3.1: Implement WebSocket Status Updates (Backend)
**Description:** WebSocket endpoint for real-time status updates

**Affected Files:**
- **MODIFY:** `autobot-user-backend/api/websockets.py`
- **MODIFY:** `backend/services/redis_service_manager.py` (emit events)

**Dependencies:** REDIS-1.1.1, REDIS-2.1.5

**Complexity:** Medium

**Priority:** P0 (Critical - Real-Time Updates)

**Acceptance Criteria:**
- [ ] WebSocket endpoint: `wss://172.16.168.20:8443/ws/services/redis/status`
- [ ] Authentication via token (URL parameter or header)
- [ ] Broadcast service status changes to all subscribed clients
- [ ] Message types: service_status, service_event, auto_recovery
- [ ] RedisServiceManager emits events via WebSocket manager
- [ ] Proper connection/disconnection handling

**Message Formats:**
```javascript
// Service status update
{
  "type": "service_status",
  "service": "redis",
  "status": "running",
  "timestamp": "2025-10-10T14:30:00Z",
  "details": { "pid": 12345, "connections": 42, "memory_mb": 128.5 }
}

// Service operation event
{
  "type": "service_event",
  "service": "redis",
  "event": "restart",
  "user": "admin@autobot.local",
  "timestamp": "2025-10-10T14:30:00Z",
  "result": "success"
}

// Auto-recovery event
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

#### REDIS-3.3.2: Integrate WebSocket in Frontend Composable
**Description:** Subscribe to WebSocket updates in useServiceManagement

**Affected Files:**
- **MODIFY:** `autobot-user-frontend/src/composables/useServiceManagement.js`
- **MODIFY:** `autobot-user-frontend/src/composables/useWebSocket.js` (or use existing)

**Dependencies:** REDIS-3.2.1, REDIS-3.3.1

**Complexity:** Medium

**Priority:** P0 (Critical - Real-Time Updates)

**Acceptance Criteria:**
- [ ] Subscribe to `/ws/services/redis/status` on component mount
- [ ] Update reactive status when receiving service_status messages
- [ ] Show notification when receiving service_event messages
- [ ] Show notification when receiving auto_recovery messages
- [ ] Refresh full status after important events
- [ ] Unsubscribe on component unmount
- [ ] Handle WebSocket connection errors gracefully

**WebSocket Integration:**
```javascript
const subscribeToStatusUpdates = (callback) => {
  statusSubscription = subscribe(`/ws/services/redis/status`, (message) => {
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
      refreshStatus();
    } else if (message.type === 'auto_recovery') {
      if (message.status === 'success') {
        showWarning(`Auto-recovery: ${message.message}`);
      } else {
        showError(`Auto-recovery failed: ${message.message}`);
      }
      refreshStatus();
    }

    if (callback) {
      callback(message);
    }
  });
};
```

---

### 3.4 UI Integration & Routing

#### REDIS-3.4.1: Add Service Management to Navigation
**Description:** Add link to service management page in navigation menu

**Affected Files:**
- **MODIFY:** `autobot-user-frontend/src/components/NavigationMenu.vue` (or similar)
- **MODIFY:** `autobot-user-frontend/src/router/index.js`

**Dependencies:** REDIS-3.1.1

**Complexity:** Simple

**Priority:** P0 (Critical - Navigation)

**Acceptance Criteria:**
- [ ] Add "Services" menu item to navigation
- [ ] Add route: `/services` or `/system/services`
- [ ] Link navigates to RedisServiceControl component
- [ ] Menu item shows active state when on services page
- [ ] Proper icon for services menu item

---

#### REDIS-3.4.2: Add Service Status to System Dashboard
**Description:** Display Redis service status on main dashboard

**Affected Files:**
- **MODIFY:** `autobot-user-frontend/src/views/Dashboard.vue` (or similar)

**Dependencies:** REDIS-3.1.2, REDIS-3.2.2

**Complexity:** Simple

**Priority:** P1 (High - Visibility)

**Acceptance Criteria:**
- [ ] Add Redis service status card to dashboard
- [ ] Shows current status badge
- [ ] Link to full service management page
- [ ] Real-time status updates
- [ ] Compact view for dashboard (full view on services page)

---

### 3.5 Testing (Phase 3)

#### REDIS-3.5.1: Component Tests for RedisServiceControl
**Description:** Vue component tests for service control UI

**Affected Files:**
- **CREATE:** `autobot-user-frontend/tests/components/RedisServiceControl.spec.js`

**Dependencies:** REDIS-3.1.1

**Complexity:** Medium

**Priority:** P1 (High - Quality Assurance)

**Acceptance Criteria:**
- [ ] Test component renders correctly
- [ ] Test start button click triggers startService()
- [ ] Test stop button shows confirmation dialog
- [ ] Test restart button with confirmation flow
- [ ] Test status badge displays correctly for each state
- [ ] Test loading states
- [ ] Test error display
- [ ] Mock API calls and WebSocket

---

#### REDIS-3.5.2: E2E Tests for Service Management UI
**Description:** End-to-end tests for complete user workflow

**Affected Files:**
- **CREATE:** `autobot-user-frontend/tests/e2e/service-management.spec.js`

**Dependencies:** REDIS-3.1.1, REDIS-3.2.1, REDIS-3.2.2

**Complexity:** Medium

**Priority:** P1 (High - Integration Validation)

**Acceptance Criteria:**
- [ ] Test: User navigates to services page
- [ ] Test: User restarts Redis service via UI
- [ ] Test: Confirmation dialog appears and user confirms
- [ ] Test: Success notification appears
- [ ] Test: Service status updates to "running"
- [ ] Test: Auto-recovery notification appears (simulate failure)
- [ ] Tests run with Playwright or Cypress

**E2E Test Example:**
```javascript
test('Admin can restart Redis service from UI', async ({ page }) => {
  await page.goto('http://172.16.168.21:5173/login');
  await page.fill('[name="email"]', 'admin@autobot.local');
  await page.fill('[name="password"]', 'admin-password');
  await page.click('button[type="submit"]');

  await page.click('text=Services');
  await page.click('text=Redis Service');

  await expect(page.locator('.service-status')).toContainText('running');

  await page.click('button:has-text("Restart")');
  await page.click('button:has-text("Confirm")');

  await page.waitForSelector('.notification:has-text("restarted successfully")');
  await expect(page.locator('.service-status')).toContainText('running');
});
```

---

**Phase 3 Summary:**
- **Total Tasks:** 14
- **P0 (Critical):** 9 tasks
- **P1 (High):** 4 tasks
- **P2 (Medium):** 1 task
- **Estimated Duration:** 3-4 days
- **MVP Deliverable:** User interface for service management ✅

---

## Phase 4: Security & Audit (Week 2-3, Days 11-13)

**Objective:** Implement RBAC, audit logging, SSH security, and production hardening

### 4.1 Role-Based Access Control

#### REDIS-4.1.1: Implement Permission Enforcement
**Description:** RBAC for service management operations

**Affected Files:**
- **MODIFY:** `autobot-user-backend/api/service_management.py`
- **CREATE:** `backend/security/service_permissions.py` (or extend existing)

**Dependencies:** REDIS-1.2.1

**Complexity:** Medium

**Priority:** P1 (High - Security)

**Acceptance Criteria:**
- [ ] Permission dependency: `require_role(["admin", "operator"])`
- [ ] Permission enforcement on all endpoints:
  - `/start` → admin, operator
  - `/stop` → admin only
  - `/restart` → admin, operator
  - `/status` → all (including anonymous)
  - `/health` → all
  - `/logs` → admin only
- [ ] 403 Forbidden response for unauthorized users
- [ ] Permission checks integrated with existing auth system
- [ ] Audit log entry when permission denied

**Permission Implementation:**
```python
from backend.security.auth import get_current_user, require_role

@router.post("/start")
async def start_redis_service(
    current_user: User = Depends(require_role(["admin", "operator"]))
) -> ServiceOperationResponse:
    # Only admin or operator can start service
    pass

@router.post("/stop")
async def stop_redis_service(
    confirmation: bool = False,
    current_user: User = Depends(require_role(["admin"]))
) -> ServiceOperationResponse:
    # Only admin can stop service
    pass
```

---

#### REDIS-4.1.2: Add Permission Tests
**Description:** Unit tests for permission enforcement

**Affected Files:**
- **CREATE:** `tests/unit/security/test_service_permissions.py`

**Dependencies:** REDIS-4.1.1

**Complexity:** Simple

**Priority:** P1 (High - Security Validation)

**Acceptance Criteria:**
- [ ] Test admin can perform all operations
- [ ] Test operator can start/restart but not stop
- [ ] Test viewer can only view status
- [ ] Test anonymous can view status/health
- [ ] Test 403 responses for unauthorized operations

---

### 4.2 VM Security Configuration

#### REDIS-4.2.1: Create sudoers Configuration for Redis VM
**Description:** Configure passwordless sudo for Redis service management

**Affected Files:**
- **CREATE:** `ansible/files/sudoers.d/autobot-redis`
- **CREATE:** `ansible/playbooks/configure-redis-sudoers.yml`

**Dependencies:** REDIS-1.1.2

**Complexity:** Simple

**Priority:** P0 (Critical - Required for Operations)

**Acceptance Criteria:**
- [ ] Sudoers file allows autobot user to run Redis systemctl commands without password
- [ ] Allowed commands:
  - `/bin/systemctl start redis-server`
  - `/bin/systemctl stop redis-server`
  - `/bin/systemctl restart redis-server`
  - `/bin/systemctl status redis-server`
  - `/bin/journalctl -u redis-server *`
- [ ] File permissions: 0440 (read-only)
- [ ] File ownership: root:root
- [ ] Ansible playbook to deploy sudoers file
- [ ] Validation step in playbook (visudo -cf)

**Sudoers Configuration:**
```bash
# /etc/sudoers.d/autobot-redis
# Allow autobot user to manage Redis service

autobot ALL=(ALL) NOPASSWD: /bin/systemctl start redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl stop redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl restart redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl status redis-server
autobot ALL=(ALL) NOPASSWD: /bin/journalctl -u redis-server *
```

**Ansible Playbook:**
```yaml
---
- name: Configure Redis VM sudoers for service management
  hosts: redis
  become: yes
  tasks:
    - name: Copy sudoers file for autobot user
      copy:
        src: files/sudoers.d/autobot-redis
        dest: /etc/sudoers.d/autobot-redis
        owner: root
        group: root
        mode: '0440'

    - name: Validate sudoers configuration
      command: visudo -cf /etc/sudoers.d/autobot-redis
      register: sudoers_validation
      failed_when: sudoers_validation.rc != 0
```

---

#### REDIS-4.2.2: Deploy and Test sudoers Configuration
**Description:** Deploy sudoers configuration to Redis VM and verify

**Affected Files:**
- **MODIFY:** `ansible/inventory` (ensure Redis VM configured)

**Dependencies:** REDIS-4.2.1

**Complexity:** Simple

**Priority:** P0 (Critical - Deployment)

**Acceptance Criteria:**
- [ ] Ansible playbook runs successfully
- [ ] sudoers file deployed to VM3
- [ ] Manual test: SSH to VM3, run `sudo systemctl status redis-server` (no password prompt)
- [ ] Manual test: SSH to VM3, run `sudo systemctl restart redis-server` (no password prompt)
- [ ] Documented deployment procedure

**Deployment Commands:**
```bash
# Deploy sudoers configuration
ansible-playbook -i ansible/inventory ansible/playbooks/configure-redis-sudoers.yml

# Verify deployment
ansible redis -i ansible/inventory -m shell -a "sudo systemctl status redis-server"
```

---

### 4.3 Enhanced Audit Logging

#### REDIS-4.3.1: Enhance Audit Logging with Security Context
**Description:** Add security context to all audit log entries

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`
- **MODIFY:** `backend/services/audit_logger.py` (if needed)

**Dependencies:** REDIS-1.3.3

**Complexity:** Simple

**Priority:** P1 (High - Compliance)

**Acceptance Criteria:**
- [ ] All audit entries include:
  - User ID and email
  - User role
  - Source IP address
  - Operation timestamp
  - Operation result (success/failure)
  - Execution duration
- [ ] Security context: command validated, risk level, SSH key used
- [ ] Audit logs stored in: `logs/audit/redis_service_management.log`
- [ ] Log rotation enabled (max 100MB, keep 10 backups)

**Enhanced Audit Entry Format:**
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

#### REDIS-4.3.2: Create Audit Log Analysis Tool
**Description:** Tool to query and analyze audit logs

**Affected Files:**
- **CREATE:** `scripts/audit/analyze_redis_service_logs.py`

**Dependencies:** REDIS-4.3.1

**Complexity:** Simple

**Priority:** P2 (Medium - Operational Tool)

**Acceptance Criteria:**
- [ ] Parse audit log file
- [ ] Query by: user, operation, date range, result (success/failure)
- [ ] Statistics: total operations, success rate, users, most common operations
- [ ] Export to CSV or JSON
- [ ] Command-line interface

---

### 4.4 Security Hardening

#### REDIS-4.4.1: Implement Rate Limiting for Service Operations
**Description:** Prevent abuse via rate limiting

**Affected Files:**
- **MODIFY:** `autobot-user-backend/api/service_management.py`

**Dependencies:** REDIS-1.2.1

**Complexity:** Medium

**Priority:** P2 (Medium - Protection)

**Acceptance Criteria:**
- [ ] Rate limit: 10 operations per minute per user
- [ ] Rate limit enforced on start/stop/restart endpoints
- [ ] 429 Too Many Requests response when limit exceeded
- [ ] Rate limit info in response headers
- [ ] Use existing rate limiting middleware if available

---

#### REDIS-4.4.2: Implement Operation Cooldown Period
**Description:** Prevent rapid successive operations

**Affected Files:**
- **MODIFY:** `backend/services/redis_service_manager.py`

**Dependencies:** REDIS-1.1.2

**Complexity:** Simple

**Priority:** P2 (Medium - Safety)

**Acceptance Criteria:**
- [ ] Enforce 5-second cooldown between service operations
- [ ] Track last operation timestamp per service
- [ ] Return error if operation attempted during cooldown
- [ ] Cooldown does not apply to status queries
- [ ] Configurable cooldown period

---

#### REDIS-4.4.3: Security Audit & Penetration Testing
**Description:** Security review and penetration testing

**Affected Files:**
- **CREATE:** `docs/security/redis_service_management_security_audit.md`

**Dependencies:** All Phase 4 tasks

**Complexity:** Medium

**Priority:** P1 (High - Production Readiness)

**Acceptance Criteria:**
- [ ] Security checklist completed:
  - [ ] Command injection prevention verified
  - [ ] Authentication/authorization tested
  - [ ] Rate limiting validated
  - [ ] Audit logging coverage verified
  - [ ] SSH security confirmed
  - [ ] Error handling doesn't leak sensitive info
- [ ] Penetration testing scenarios:
  - [ ] Attempt unauthorized operations
  - [ ] Test permission bypass attempts
  - [ ] Validate rate limiting effectiveness
  - [ ] Test command injection vectors
- [ ] Security audit report documenting findings and mitigations
- [ ] All critical/high vulnerabilities resolved before production

---

**Phase 4 Summary:**
- **Total Tasks:** 11
- **P0 (Critical):** 2 tasks
- **P1 (High):** 6 tasks
- **P2 (Medium):** 3 tasks
- **Estimated Duration:** 3-4 days
- **MVP Deliverable:** Production-ready security and compliance ✅

---

## Phase 5: Comprehensive Testing & Documentation (Week 3, Days 14-15)

**Objective:** Complete testing coverage, documentation, and production preparation

### 5.1 Performance Testing

#### REDIS-5.1.1: Load Testing - Service Status Endpoint
**Description:** Performance test for status query endpoint

**Affected Files:**
- **CREATE:** `tests/performance/test_redis_service_status_load.py`

**Dependencies:** REDIS-1.2.1

**Complexity:** Medium

**Priority:** P1 (High - Performance Validation)

**Acceptance Criteria:**
- [ ] Load test: 10 requests/second for 60 seconds
- [ ] Measure: average response time, p95, p99, max
- [ ] Target: Average response time < 100ms
- [ ] Target: p95 response time < 500ms
- [ ] Target: Error rate < 1%
- [ ] Generate performance report

**Load Test Script:**
```python
import asyncio
import time
from httpx import AsyncClient

async def load_test_status_endpoint(duration_seconds: int = 60):
    client = AsyncClient(base_url="https://172.16.168.20:8443")

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
        except Exception:
            error_count += 1

        await asyncio.sleep(0.1)  # 10 requests/sec

    avg_response_time = total_duration / request_count if request_count > 0 else 0
    error_rate = error_count / (request_count + error_count)

    print(f"Load Test Results:")
    print(f"  Requests: {request_count}")
    print(f"  Errors: {error_count}")
    print(f"  Error Rate: {error_rate:.2%}")
    print(f"  Avg Response Time: {avg_response_time*1000:.2f}ms")

    assert error_rate < 0.01
    assert avg_response_time < 0.5
```

---

#### REDIS-5.1.2: Performance Testing - Service Operations
**Description:** Performance benchmarks for service operations

**Affected Files:**
- **CREATE:** `tests/performance/test_redis_service_operations_performance.py`

**Dependencies:** REDIS-1.2.1, REDIS-1.1.2

**Complexity:** Medium

**Priority:** P1 (High - SLA Validation)

**Acceptance Criteria:**
- [ ] Benchmark: Service start time (target: < 15s)
- [ ] Benchmark: Service stop time (target: < 10s)
- [ ] Benchmark: Service restart time (target: < 20s)
- [ ] Benchmark: Health check time (target: < 2s)
- [ ] Benchmark: Auto-recovery time (target: < 30s)
- [ ] 10 iterations per operation
- [ ] Performance report with statistics (mean, median, std dev)

---

### 5.2 Documentation

#### REDIS-5.2.1: Create User Guide
**Description:** End-user documentation for service management

**Affected Files:**
- **CREATE:** `docs/user-guides/redis-service-management-user-guide.md`

**Dependencies:** REDIS-3.1.1

**Complexity:** Simple

**Priority:** P1 (High - User Documentation)

**Acceptance Criteria:**
- [ ] How to access service management UI
- [ ] How to check service status
- [ ] How to start/stop/restart Redis service
- [ ] Understanding health status indicators
- [ ] What to do when auto-recovery fails
- [ ] Troubleshooting common issues
- [ ] Screenshots of UI
- [ ] Step-by-step procedures

---

#### REDIS-5.2.2: Create Operational Runbook
**Description:** Administrator documentation for operations

**Affected Files:**
- **CREATE:** `docs/operations/redis-service-management-runbook.md`

**Dependencies:** All phases

**Complexity:** Medium

**Priority:** P1 (High - Operations Documentation)

**Acceptance Criteria:**
- [ ] System architecture overview
- [ ] Service dependencies and requirements
- [ ] Configuration reference
- [ ] Monitoring and alerting setup
- [ ] Troubleshooting procedures
- [ ] Recovery procedures (when auto-recovery fails)
- [ ] Security considerations
- [ ] Disaster recovery procedures
- [ ] SSH key management
- [ ] Audit log analysis

---

#### REDIS-5.2.3: Create Developer Documentation
**Description:** Technical documentation for developers

**Affected Files:**
- **CREATE:** `docs/developer/redis-service-management-developer-guide.md`

**Dependencies:** All phases

**Complexity:** Medium

**Priority:** P1 (High - Developer Documentation)

**Acceptance Criteria:**
- [ ] Architecture overview
- [ ] Component descriptions (RedisServiceManager, health checkers, recovery strategies)
- [ ] API endpoint documentation
- [ ] WebSocket message formats
- [ ] Configuration reference
- [ ] Extension points (adding new services)
- [ ] Testing guide
- [ ] Code examples

---

#### REDIS-5.2.4: Update API Documentation
**Description:** Add service management endpoints to API docs

**Affected Files:**
- **MODIFY:** `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`

**Dependencies:** REDIS-1.2.1

**Complexity:** Simple

**Priority:** P1 (High - API Documentation)

**Acceptance Criteria:**
- [ ] Document all 6 API endpoints with examples
- [ ] Request/response schemas
- [ ] Error responses
- [ ] Authentication requirements
- [ ] Permission requirements
- [ ] WebSocket endpoint documentation

---

### 5.3 Deployment Preparation

#### REDIS-5.3.1: Create Deployment Checklist
**Description:** Pre-deployment verification checklist

**Affected Files:**
- **CREATE:** `docs/deployment/redis-service-management-deployment-checklist.md`

**Dependencies:** All phases

**Complexity:** Simple

**Priority:** P0 (Critical - Deployment)

**Acceptance Criteria:**
- [ ] Pre-deployment checklist:
  - [ ] SSH key deployed and tested on Redis VM
  - [ ] sudoers configuration deployed
  - [ ] Configuration files deployed
  - [ ] Ansible playbooks tested
  - [ ] Backend changes deployed
  - [ ] Frontend changes synced to VM1
  - [ ] Database migrations (if any)
- [ ] Deployment steps documented
- [ ] Rollback procedure documented
- [ ] Smoke test procedures
- [ ] Post-deployment validation

---

#### REDIS-5.3.2: Create Ansible Deployment Playbook
**Description:** Ansible playbook for complete deployment

**Affected Files:**
- **CREATE:** `ansible/playbooks/deploy-redis-service-management.yml`

**Dependencies:** REDIS-4.2.1

**Complexity:** Medium

**Priority:** P1 (High - Automated Deployment)

**Acceptance Criteria:**
- [ ] Playbook deploys all components:
  - [ ] sudoers configuration to Redis VM
  - [ ] Backend service restart (main machine)
  - [ ] Frontend sync to VM1
  - [ ] Configuration file deployment
- [ ] Idempotent (can run multiple times safely)
- [ ] Validation steps included
- [ ] Rollback capability
- [ ] Dry-run mode

**Deployment Playbook Structure:**
```yaml
---
- name: Deploy Redis Service Management Feature
  hosts: all
  become: yes

  tasks:
    - name: Deploy sudoers configuration
      include_tasks: configure-redis-sudoers.yml

    - name: Restart backend service
      service:
        name: autobot-backend
        state: restarted
      when: inventory_hostname == 'main'

    - name: Sync frontend to VM1
      synchronize:
        src: /home/kali/Desktop/AutoBot/autobot-user-frontend/
        dest: /home/autobot/autobot-user-frontend/
      when: inventory_hostname == 'frontend'

    - name: Validate deployment
      include_tasks: validate-service-management.yml
```

---

#### REDIS-5.3.3: Production Deployment & Smoke Testing
**Description:** Deploy to production and verify

**Affected Files:**
- **CREATE:** `docs/deployment/redis-service-management-production-deployment-report.md`

**Dependencies:** REDIS-5.3.1, REDIS-5.3.2

**Complexity:** Medium

**Priority:** P0 (Critical - Go-Live)

**Acceptance Criteria:**
- [ ] Deployment executed via Ansible playbook
- [ ] Smoke tests passed:
  - [ ] Backend API endpoints accessible
  - [ ] Frontend UI accessible
  - [ ] Service status query works
  - [ ] Service restart works (test environment)
  - [ ] Auto-recovery tested (simulated failure)
  - [ ] WebSocket notifications received
  - [ ] Audit logging working
- [ ] Production validation:
  - [ ] All services healthy
  - [ ] No errors in logs
  - [ ] Performance within SLA
- [ ] Deployment report documented

---

### 5.4 Final Testing

#### REDIS-5.4.1: End-to-End Testing - Complete User Workflow
**Description:** Full E2E test covering all user scenarios

**Affected Files:**
- **CREATE:** `tests/e2e/test_complete_service_management_workflow.py`

**Dependencies:** All phases

**Complexity:** Complex

**Priority:** P1 (High - Final Validation)

**Acceptance Criteria:**
- [ ] Test Scenario 1: Admin restarts service via UI
- [ ] Test Scenario 2: Operator starts stopped service
- [ ] Test Scenario 3: Viewer views service status (no controls)
- [ ] Test Scenario 4: Auto-recovery after simulated failure
- [ ] Test Scenario 5: WebSocket notifications received
- [ ] Test Scenario 6: Audit log entries created
- [ ] All tests pass consistently

---

#### REDIS-5.4.2: Failure Scenario Testing
**Description:** Test all failure and edge case scenarios

**Affected Files:**
- **CREATE:** `tests/integration/test_redis_service_failure_scenarios.py`

**Dependencies:** All phases

**Complexity:** Complex

**Priority:** P1 (High - Reliability Validation)

**Acceptance Criteria:**
- [ ] Test: SSH connection to Redis VM fails
- [ ] Test: Redis service fails to start (port conflict)
- [ ] Test: Redis service crashes repeatedly (recovery loop)
- [ ] Test: Max recovery attempts exceeded
- [ ] Test: Circuit breaker opens after failures
- [ ] Test: Manual intervention required scenario
- [ ] Test: Service operation timeout
- [ ] Test: Invalid commands rejected
- [ ] All failure scenarios handled gracefully

---

**Phase 5 Summary:**
- **Total Tasks:** 13
- **P0 (Critical):** 2 tasks
- **P1 (High):** 11 tasks
- **Estimated Duration:** 2-3 days
- **MVP Deliverable:** Production-ready system with full testing and documentation ✅

---

## Task Dependency Graph

**Critical Path (MVP):**

```
Phase 1 (Days 1-3):
REDIS-1.1.1 (Service Manager Class)
  ↓
REDIS-1.1.2 (Service Control Methods) + REDIS-1.1.3 (Status Check)
  ↓
REDIS-1.2.1 (API Router) + REDIS-1.2.2 (Response Models) + REDIS-1.2.3 (DI Setup)
  ↓
REDIS-1.3.1 (Configuration) + REDIS-1.3.2 (Health Integration) + REDIS-1.3.3 (Audit Logging)
  ↓
REDIS-1.4.1 + REDIS-1.4.2 + REDIS-1.4.3 (Unit & Integration Tests)

Phase 2 (Days 4-7):
REDIS-2.1.1 + REDIS-2.1.2 + REDIS-2.1.3 (Health Checkers)
  ↓
REDIS-2.1.4 (Comprehensive Health Check)
  ↓
REDIS-2.1.5 (Background Monitor Task)
  ↓
REDIS-2.2.1 + REDIS-2.2.2 + REDIS-2.2.3 (Recovery Strategies)
  ↓
REDIS-2.2.4 (Recovery Orchestration)
  ↓
REDIS-2.2.5 + REDIS-2.2.6 (Circuit Breaker + Loop Detection)
  ↓
REDIS-2.3.1 + REDIS-2.3.2 (Notifications & Alerts)
  ↓
REDIS-2.4.1 + REDIS-2.4.2 + REDIS-2.4.3 (Unit & Integration Tests)

Phase 3 (Days 8-10):
REDIS-3.1.1 (UI Component) + REDIS-3.1.2 (Status Badge) + REDIS-3.1.4 (Confirm Dialog)
  ↓
REDIS-3.2.1 (Composable) + REDIS-3.2.2 (API Service)
  ↓
REDIS-3.3.1 (WebSocket Backend) + REDIS-3.3.2 (WebSocket Frontend)
  ↓
REDIS-3.4.1 + REDIS-3.4.2 (Navigation & Dashboard Integration)
  ↓
REDIS-3.5.1 + REDIS-3.5.2 (Component & E2E Tests)

Phase 4 (Days 11-13):
REDIS-4.1.1 (RBAC) + REDIS-4.1.2 (Permission Tests)
  ↓
REDIS-4.2.1 + REDIS-4.2.2 (sudoers Configuration & Deployment)
  ↓
REDIS-4.3.1 + REDIS-4.3.2 (Enhanced Audit Logging)
  ↓
REDIS-4.4.1 + REDIS-4.4.2 (Rate Limiting & Cooldown)
  ↓
REDIS-4.4.3 (Security Audit)

Phase 5 (Days 14-15):
REDIS-5.1.1 + REDIS-5.1.2 (Performance Testing)
  ↓
REDIS-5.2.1 + REDIS-5.2.2 + REDIS-5.2.3 + REDIS-5.2.4 (Documentation)
  ↓
REDIS-5.3.1 + REDIS-5.3.2 (Deployment Preparation)
  ↓
REDIS-5.3.3 (Production Deployment)
  ↓
REDIS-5.4.1 + REDIS-5.4.2 (Final Testing)
```

---

## MVP Definition

**Minimum Viable Product (Phase 1 + Phase 2):**
- ✅ Backend service manager with start/stop/restart operations
- ✅ API endpoints for service control
- ✅ Auto-recovery system with health monitoring
- ✅ Background monitoring task
- ✅ Basic audit logging
- ✅ Unit and integration tests

**MVP+ (Phase 3):**
- ✅ Frontend UI for service control
- ✅ Real-time WebSocket updates
- ✅ User-friendly interface

**Production-Ready (Phase 4 + Phase 5):**
- ✅ RBAC and security hardening
- ✅ Comprehensive testing
- ✅ Complete documentation
- ✅ Deployment automation

---

## Implementation Priorities

**Week 1 (Days 1-7):** MVP - Core functionality
- Phase 1: Core infrastructure (P0 tasks)
- Phase 2: Auto-recovery system (P0 tasks)

**Week 2 (Days 8-10):** MVP+ - User interface
- Phase 3: Frontend integration (P0 tasks)

**Week 2-3 (Days 11-15):** Production-ready
- Phase 4: Security & audit (P1 tasks)
- Phase 5: Testing & documentation (P1 tasks)

---

## Risk Mitigation

**Identified Risks:**

1. **SSH Connection Issues:**
   - **Mitigation:** Extensive SSH connection testing in Phase 1
   - **Fallback:** Manual service management documentation

2. **Auto-Recovery Loop:**
   - **Mitigation:** Circuit breaker and loop detection (Phase 2)
   - **Monitoring:** Alert when loop detected

3. **Permission Issues on VM:**
   - **Mitigation:** Early sudoers deployment and testing (Phase 4)
   - **Validation:** Ansible playbook includes verification

4. **Performance Degradation:**
   - **Mitigation:** Performance testing in Phase 5
   - **Optimization:** Status caching, rate limiting

5. **Security Vulnerabilities:**
   - **Mitigation:** Security audit in Phase 4
   - **Review:** Penetration testing before production

---

## Success Metrics

**Technical Metrics:**
- Service start time: < 15 seconds
- Service restart time: < 20 seconds
- Auto-recovery time: < 30 seconds
- Health check response time: < 2 seconds
- API response time: < 100ms (status queries)
- Test coverage: > 80%

**User Experience Metrics:**
- UI response time: < 500ms
- Real-time update latency: < 1 second
- Zero data loss during service operations
- Clear error messages for all failure scenarios

**Operational Metrics:**
- Auto-recovery success rate: > 95%
- False positive rate: < 5%
- Zero security incidents
- Complete audit trail for all operations

---

## Implementation Notes

**Development Environment:**
- Local development on `/home/kali/Desktop/AutoBot/`
- Backend testing against Redis VM (172.16.168.23)
- Frontend testing on VM1 (172.16.168.21:5173)
- SSH key: `~/.ssh/autobot_key`

**Deployment Strategy:**
- All code changes developed locally first
- Sync to remote VMs via sync scripts or Ansible
- Never edit code directly on remote VMs
- Use `run_autobot.sh` for local backend startup
- Frontend runs on VM1 only (single frontend server)

**Testing Strategy:**
- Unit tests: Mock SSH and external dependencies
- Integration tests: Use test Redis VM or dedicated test environment
- E2E tests: Run against full distributed infrastructure
- Performance tests: Isolated test environment to avoid production impact

**Code Quality:**
- Follow existing AutoBot code patterns
- Use type hints for all Python code
- Use proper TypeScript typing for frontend
- Run pre-commit hooks (Black, flake8, isort)
- Code review by code-reviewer agent (MANDATORY)

---

## Appendix: Quick Reference

### File Locations

**Backend Files:**
- `backend/services/redis_service_manager.py` - Core service manager
- `autobot-user-backend/api/service_management.py` - API router
- `backend/models/service_management.py` - Response models
- `config/services/redis_service_management.yaml` - Configuration

**Frontend Files:**
- `autobot-user-frontend/src/components/services/RedisServiceControl.vue` - Main UI
- `autobot-user-frontend/src/composables/useServiceManagement.js` - Logic composable
- `autobot-user-frontend/src/services/RedisServiceAPI.js` - API client

**Testing Files:**
- `tests/unit/services/test_redis_service_manager.py`
- `tests/integration/test_redis_service_management_integration.py`
- `tests/e2e/service-management.spec.js`

**Documentation Files:**
- `docs/user-guides/redis-service-management-user-guide.md`
- `docs/operations/redis-service-management-runbook.md`
- `docs/developer/redis-service-management-developer-guide.md`

**Deployment Files:**
- `ansible/files/sudoers.d/autobot-redis`
- `ansible/playbooks/configure-redis-sudoers.yml`
- `ansible/playbooks/deploy-redis-service-management.yml`

### Key Commands

**Development:**
```bash
# Backend development
bash run_autobot.sh --dev

# Frontend development (runs on VM1)
./scripts/utilities/sync-frontend.sh

# Run tests
pytest tests/unit/services/test_redis_service_manager.py
pytest tests/integration/test_redis_service_management_integration.py
```

**Deployment:**
```bash
# Deploy sudoers configuration
ansible-playbook -i ansible/inventory ansible/playbooks/configure-redis-sudoers.yml

# Deploy full feature
ansible-playbook -i ansible/inventory ansible/playbooks/deploy-redis-service-management.yml

# Verify deployment
ansible redis -i ansible/inventory -m shell -a "sudo systemctl status redis-server"
```

**Testing:**
```bash
# Unit tests
pytest tests/unit/services/ -v

# Integration tests
pytest tests/integration/test_redis_service_management_integration.py -v

# E2E tests
cd autobot-vue && npm run test:e2e
```

---

## Document Metadata

**Total Tasks:** 66
- Phase 1: 13 tasks
- Phase 2: 15 tasks
- Phase 3: 14 tasks
- Phase 4: 11 tasks
- Phase 5: 13 tasks

**Total Estimated Duration:** 15 working days (3 weeks)

**Created:** 2025-10-10
**Last Updated:** 2025-10-10
**Author:** Claude (Project Task Planner Agent)
**Architecture Reference:** [`docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md`](../../docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md)

---

**END OF TASK LIST**
