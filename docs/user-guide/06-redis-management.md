# Redis Service Management User Guide

**Version:** 1.0
**Last Updated:** 2025-10-10
**Audience:** AutoBot Users, Operators, Administrators

---

## Table of Contents

1. [Introduction](#introduction)
2. [Accessing Redis Service Controls](#accessing-redis-service-controls)
3. [Service Control Operations](#service-control-operations)
4. [Monitoring Service Health](#monitoring-service-health)
5. [Auto-Recovery System](#auto-recovery-system)
6. [Role-Based Access](#role-based-access)
7. [Troubleshooting Common Issues](#troubleshooting-common-issues)
8. [Best Practices](#best-practices)

---

## Introduction

### What is Redis Service Management?

Redis Service Management provides user-friendly controls for managing the Redis service running on AutoBot's distributed infrastructure. This feature enables you to:

- **Monitor Redis health** in real-time
- **Start, stop, or restart** the Redis service
- **View service logs** for troubleshooting
- **Receive automatic recovery** from service failures
- **Track service operations** through audit logs

### Why is Redis Important?

Redis is a critical component of AutoBot that provides:
- **Session Management** - User login sessions and authentication
- **Caching** - Performance optimization for frequently accessed data
- **Real-Time Features** - WebSocket message queuing and pub/sub
- **Knowledge Base** - Vector search and embeddings storage

**Important:** Stopping Redis affects all these features. Only stop Redis when absolutely necessary and with proper planning.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend UI (VM1)                         │
│              http://172.16.168.21:5173                       │
│                                                              │
│  [Redis Service Controls]                                   │
│   - Service Status Display                                  │
│   - Start / Stop / Restart Buttons                          │
│   - Health Monitoring Dashboard                             │
│   - Service Logs Viewer                                     │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ HTTP API + WebSocket
                       ▼
┌─────────────────────────────────────────────────────────────┐
│              Backend API (Main Machine)                      │
│           https://172.16.168.20:8443                         │
│                                                              │
│  [Redis Service Manager]                                    │
│   - Service Control Logic                                   │
│   - Health Monitoring                                       │
│   - Auto-Recovery System                                    │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       │ SSH Commands (systemctl)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                Redis VM (VM3)                                │
│           172.16.168.23:6379                                │
│                                                              │
│  [Redis Service]                                            │
│   - Redis Server Process                                    │
│   - systemd Service Management                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Accessing Redis Service Controls

### Step 1: Login to AutoBot

1. Navigate to AutoBot frontend: `http://172.16.168.21:5173`
2. Login with your credentials
3. Ensure you have appropriate role permissions (see [Role-Based Access](#role-based-access))

### Step 2: Navigate to Service Management

**Option 1: Main Navigation**
1. Click **"Services"** in the main navigation menu
2. Select **"Redis Service"** from the services list

**Option 2: System Status Dashboard**
1. Click **"System Status"** or **"Health"** in navigation
2. Find the **"Redis Service"** card
3. Click **"Manage"** or **"Details"**

**Option 3: Quick Access (Admin)**
1. Look for the **"Services"** dropdown in the top toolbar
2. Select **"Redis Service Management"**

### Interface Overview

The Redis Service Management interface includes:

```
┌─────────────────────────────────────────────────────────────┐
│  Redis Service                                    [●Running] │
├─────────────────────────────────────────────────────────────┤
│  Service Details                                             │
│  • Uptime: 1d 4h 32m                                        │
│  • Memory: 128.5 MB                                         │
│  • Connections: 42                                          │
├─────────────────────────────────────────────────────────────┤
│  Actions                                                     │
│  [▶ Start]  [↻ Restart]  [■ Stop]  [↺ Refresh]            │
├─────────────────────────────────────────────────────────────┤
│  Health Status: HEALTHY                                      │
│  ✓ Connectivity: pass (2.5ms)                               │
│  ✓ Systemd: pass (50ms)                                     │
│  ✓ Performance: pass (15ms)                                 │
├─────────────────────────────────────────────────────────────┤
│  Auto-Recovery: Enabled                                      │
│  Recent Recoveries: 0                                        │
├─────────────────────────────────────────────────────────────┤
│  [Show Logs]                                                │
└─────────────────────────────────────────────────────────────┘
```

**Status Indicators:**
- **●Green (Running)** - Service is healthy and operational
- **●Yellow (Degraded)** - Service running but experiencing issues
- **●Red (Critical)** - Service stopped or failed
- **●Gray (Unknown)** - Unable to determine service status

---

## Service Control Operations

### Starting Redis Service

**When to Use:**
- Redis service is stopped or failed
- After maintenance or manual intervention
- After system reboot

**Steps:**
1. Navigate to Redis Service Management interface
2. Verify service status shows **"Stopped"** or **"Failed"**
3. Click **"Start"** button
4. Wait for confirmation message (typically 10-15 seconds)
5. Verify status changes to **"Running"**

**Expected Behavior:**
- Start button becomes disabled during operation
- Progress indicator shows operation in progress
- Success notification appears when complete
- Service status updates to "Running"
- Health checks begin automatically

**Permissions Required:** Operator or Admin role

**Screenshot Description:**
> *Interface showing "Start" button highlighted, with service status "Stopped" in red. After clicking, progress spinner appears, followed by success notification "Redis service started successfully" in green.*

---

### Restarting Redis Service

**When to Use:**
- Applying configuration changes
- Resolving performance issues
- Clearing stuck connections
- Recovery from degraded state

**Steps:**
1. Navigate to Redis Service Management interface
2. Verify service status shows **"Running"**
3. Click **"Restart"** button
4. **Confirmation dialog appears** with warning:
   ```
   Restart Redis Service

   This will temporarily interrupt Redis service.
   Active connections will be dropped.

   Are you sure you want to continue?

   [Cancel]  [Confirm Restart]
   ```
5. Click **"Confirm Restart"**
6. Wait for operation to complete (typically 15-20 seconds)
7. Verify status remains **"Running"** with new PID

**Expected Behavior:**
- Confirmation dialog prevents accidental restarts
- All active Redis connections are terminated
- Service stops gracefully, then starts immediately
- New process ID (PID) assigned
- Uptime counter resets to zero
- Previous connection count displayed in result

**Important Notes:**
- **Temporary service interruption** (15-20 seconds)
- **All cached data is preserved** (Redis persistence)
- **Active user sessions may need re-authentication**
- **WebSocket connections will reconnect automatically**

**Permissions Required:** Operator or Admin role

**Screenshot Description:**
> *Confirmation dialog with warning icon and message about connection interruption. User must explicitly click "Confirm Restart" button. Background shows main interface dimmed.*

---

### Stopping Redis Service

**When to Use:**
- **Emergency situations only**
- System maintenance requiring Redis shutdown
- Troubleshooting critical issues
- Before Redis VM shutdown

**⚠️ Warning:** Stopping Redis affects all dependent services:
- User sessions will be lost
- Real-time features will stop working
- Caching will be disabled
- Knowledge base vector search unavailable

**Steps:**
1. Navigate to Redis Service Management interface
2. Verify service status shows **"Running"**
3. Click **"Stop"** button (Red, may show warning icon)
4. **Critical confirmation dialog appears**:
   ```
   Stop Redis Service

   ⚠️ CRITICAL OPERATION ⚠️

   Stopping Redis will affect all dependent services:
   • User sessions will be terminated
   • Real-time features will stop
   • Caching will be disabled
   • Knowledge base will be unavailable

   This action requires administrator confirmation.

   Type "STOP" to confirm:
   [_________________]

   [Cancel]  [Confirm Stop]
   ```
5. Type **"STOP"** in the confirmation field
6. Click **"Confirm Stop"**
7. Wait for operation to complete (typically 8-10 seconds)
8. Verify status changes to **"Stopped"**

**Expected Behavior:**
- Multiple confirmation steps prevent accidental stops
- Service stops gracefully (allows current operations to complete)
- All connections closed properly
- Data persisted to disk before shutdown
- Dependent services enter degraded mode
- System-wide banner displays: "Redis service offline - limited functionality"

**Permissions Required:** Admin role only

**Screenshot Description:**
> *Critical confirmation dialog with red warning banner. Text input field requires typing "STOP" to enable the confirm button. Lists all affected services in red text.*

---

### Refreshing Service Status

**When to Use:**
- Checking current status manually
- After external changes to Redis
- Verifying auto-recovery results

**Steps:**
1. Click **"Refresh"** button
2. Status updates within 1-2 seconds
3. All metrics refresh simultaneously

**Expected Behavior:**
- Quick status update (no confirmation needed)
- All displayed metrics update
- No impact on Redis service

**Permissions Required:** Any role (including anonymous)

---

## Monitoring Service Health

### Health Status Overview

The health monitoring system continuously checks Redis service health across multiple layers:

#### Health Status Levels

**1. Healthy (Green)**
- All health checks passing
- Service running normally
- Response times within normal range
- Resource usage acceptable

**2. Degraded (Yellow)**
- Service running but issues detected
- High memory usage (>75%)
- Slow response times (>100ms)
- High connection count (>80% of max)
- Recommendations provided

**3. Critical (Red)**
- Service not running or not responding
- Connection failures
- Systemd reports service failed
- Auto-recovery may be in progress

**4. Unknown (Gray)**
- Unable to determine service status
- Redis VM unreachable
- SSH connection failed

### Health Check Components

The interface displays three health check categories:

#### 1. Connectivity Check
- **Purpose:** Verifies Redis responds to commands
- **Method:** Redis PING command
- **Pass Criteria:** Response received within 5 seconds
- **Display:** Response time in milliseconds

**Example Display:**
```
✓ Connectivity: pass (2.5ms)
  PING successful
```

#### 2. Systemd Status Check
- **Purpose:** Verifies systemd service state
- **Method:** Query systemctl status
- **Pass Criteria:** Service status is "active"
- **Display:** Service state and details

**Example Display:**
```
✓ Systemd: pass (50ms)
  Service active and running
```

#### 3. Performance Check
- **Purpose:** Monitors resource usage
- **Method:** Redis INFO command + system metrics
- **Pass Criteria:** All metrics within acceptable ranges
- **Display:** Current metrics vs. limits

**Example Display:**
```
✓ Performance: pass (15ms)
  All metrics within normal ranges

  Metrics:
  • Memory: 128.5 MB / 4096 MB (3.1%)
  • CPU: 5.2%
  • Connections: 42 / 10000 (0.4%)
```

### Recommendations

When health status is degraded, the system provides actionable recommendations:

**Example Recommendations:**
```
Recommendations:
• Consider increasing memory limit (usage at 85%)
• Monitor connection usage (approaching limit)
• Review slow queries (response time elevated)
• Check for memory leaks (gradual memory increase)
```

### Performance Metrics Explained

| Metric | Description | Warning Threshold | Critical Threshold |
|--------|-------------|-------------------|-------------------|
| **Memory Usage** | RAM used by Redis | 3072 MB (75%) | 4096 MB (100%) |
| **CPU Usage** | Redis process CPU | 70% | 90% |
| **Connections** | Active client connections | 8000 (80%) | 9500 (95%) |
| **Response Time** | PING command latency | 50ms | 100ms |
| **Error Rate** | Failed commands/hour | 10 | 50 |

### Real-Time Updates

Service status and health metrics update automatically:

- **Status Updates:** Every 30 seconds via WebSocket
- **Health Checks:** Every 30 seconds (background)
- **Manual Refresh:** Click "Refresh" button anytime

**Visual Indicator:**
- Pulse animation on status badge indicates live updates
- Last update timestamp shown: "Last check: 2s ago"
- Connection status: "●Connected" or "○Disconnected"

---

## Auto-Recovery System

### Overview

AutoBot includes an intelligent auto-recovery system that automatically detects and resolves Redis service failures without manual intervention.

### How Auto-Recovery Works

**Detection:**
1. Background health monitor checks Redis every 30 seconds
2. If health check fails, counter increments
3. After 3 consecutive failures, auto-recovery triggers

**Recovery Process:**
```
Failure Detected
    ↓
Determine Failure Type
    ↓
Select Recovery Strategy:
├─ Service Running but Unresponsive → Soft Recovery (reload)
├─ Service Stopped → Standard Recovery (start)
└─ Service Failed → Hard Recovery (restart)
    ↓
Execute Recovery
    ↓
Verify Success
    ↓
Success → Reset counter, log event
Failure → Try next level or alert admin
```

### Recovery Strategies

#### Level 1: Soft Recovery (5-10 seconds)
- **Scenario:** Redis process hung but systemd thinks it's running
- **Action:** Send SIGHUP signal to reload
- **Impact:** Minimal (no connection drops)
- **User Notification:** Info level

#### Level 2: Standard Recovery (10-20 seconds)
- **Scenario:** Redis service stopped
- **Action:** Execute `systemctl start redis-server`
- **Impact:** Brief startup time
- **User Notification:** Warning level

#### Level 3: Hard Recovery (20-30 seconds)
- **Scenario:** Redis service failed to start
- **Action:** Execute `systemctl restart redis-server`
- **Impact:** Moderate (connections reset)
- **User Notification:** Warning level

#### Level 4: Critical Alert (Manual Intervention)
- **Scenario:** All recovery attempts failed
- **Action:** Alert administrators, disable auto-recovery
- **Impact:** Service remains down
- **User Notification:** Critical alert

### Auto-Recovery Status Display

The interface shows auto-recovery status:

```
┌─────────────────────────────────────────────────┐
│  Auto-Recovery: Enabled                         │
│  Recent Recoveries: 0                           │
│  Last Recovery: Never                           │
│  Status: Monitoring                             │
└─────────────────────────────────────────────────┘
```

**After Recovery Attempt:**
```
┌─────────────────────────────────────────────────┐
│  Auto-Recovery: Enabled                         │
│  Recent Recoveries: 1                           │
│  Last Recovery: 2 minutes ago                   │
│  Status: Success (Standard Recovery)            │
│  Duration: 15.7 seconds                         │
└─────────────────────────────────────────────────┘
```

**Manual Intervention Required:**
```
┌─────────────────────────────────────────────────┐
│  Auto-Recovery: Disabled                        │
│  Recent Recoveries: 3                           │
│  Last Recovery: 5 minutes ago                   │
│  Status: Failed - Manual Intervention Required  │
│                                                 │
│  ⚠️ All automatic recovery attempts failed.     │
│  Please check service logs and contact admin.   │
│                                                 │
│  [View Logs]  [Contact Support]                │
└─────────────────────────────────────────────────┘
```

### Notifications

Users receive real-time notifications for auto-recovery events:

**Recovery Started:**
```
🔧 Auto-Recovery Started
Redis service failure detected. Attempting automatic recovery...
```

**Recovery Successful:**
```
✓ Auto-Recovery Successful
Redis service recovered automatically using Standard Recovery.
Service is now healthy.
```

**Recovery Failed:**
```
✗ Auto-Recovery Failed
Automatic recovery unsuccessful after 3 attempts.
Manual intervention required. Please contact administrator.
```

### Configuration

**Default Settings:**
- Auto-recovery: **Enabled**
- Max attempts: **3**
- Retry delay: **10 seconds** (exponential backoff)
- Failure threshold: **3 consecutive failures**

Administrators can configure these settings in:
`/home/kali/Desktop/AutoBot/config/services/redis_service_management.yaml`

---

## Role-Based Access

### Permission Matrix

Different user roles have different levels of access to Redis service management:

| Operation | Viewer | Operator | Admin | Anonymous |
|-----------|--------|----------|-------|-----------|
| **View Status** | ✓ | ✓ | ✓ | ✓ (limited) |
| **View Health** | ✓ | ✓ | ✓ | ✓ (limited) |
| **View Metrics** | ✓ | ✓ | ✓ | ✗ |
| **Start Service** | ✗ | ✓ | ✓ | ✗ |
| **Restart Service** | ✗ | ✓ | ✓ | ✗ |
| **Stop Service** | ✗ | ✗ | ✓ | ✗ |
| **View Logs** | ✗ | ✗ | ✓ | ✗ |
| **Configure Auto-Recovery** | ✗ | ✗ | ✓ | ✗ |

### Role Descriptions

#### Anonymous (Not Logged In)
**Access:**
- View basic service status (running/stopped)
- View limited health information
- No ability to perform operations

**Use Case:** Public status page, external monitoring

#### Viewer
**Access:**
- View detailed service status
- View complete health metrics
- View performance graphs
- Monitor service events

**Cannot:**
- Perform any service operations
- View sensitive logs
- Change configuration

**Use Case:** Read-only monitoring, dashboard viewers

#### Operator
**Access:**
- All Viewer permissions
- Start Redis service
- Restart Redis service
- Receive operation notifications

**Cannot:**
- Stop Redis service (too disruptive)
- View audit logs
- Configure auto-recovery

**Use Case:** Day-to-day operations, first-level support

#### Admin
**Access:**
- All Operator permissions
- Stop Redis service
- View complete audit logs
- Configure auto-recovery settings
- Access diagnostic tools
- Override safety confirmations

**Use Case:** System administrators, senior operations team

### Permission Denied Handling

When users attempt operations they lack permissions for:

**Example (Operator trying to stop service):**
```
┌─────────────────────────────────────────────────┐
│  ⚠️ Permission Denied                           │
│                                                 │
│  You do not have permission to stop the Redis  │
│  service. This operation requires Admin role.  │
│                                                 │
│  Your role: Operator                           │
│  Required role: Admin                          │
│                                                 │
│  If you need to stop the service, please:      │
│  • Contact a system administrator             │
│  • Submit a service request                    │
│  • Escalate to on-call admin                   │
│                                                 │
│  [Contact Admin]  [Close]                      │
└─────────────────────────────────────────────────┘
```

### Requesting Access

To request elevated permissions:

1. Click **"Contact Admin"** in permission denied dialog
2. Fill out access request form:
   - Current role
   - Requested role
   - Justification
   - Duration needed
3. Submit request
4. Wait for administrator approval

---

## Troubleshooting Common Issues

### Issue 1: Redis Service Won't Start

**Symptoms:**
- Start operation fails with error
- Service status shows "Failed"
- Error message: "Job for redis-server.service failed"

**Possible Causes & Solutions:**

**Cause 1: Port 6379 Already in Use**

Check if another process is using Redis port:

```bash
# On Redis VM (requires admin SSH access)
sudo lsof -i :6379
```

**Solution:** Stop conflicting process or reconfigure Redis port

**Cause 2: Redis Configuration Error**

Check Redis logs for configuration errors:
1. Click **"Show Logs"** in service interface
2. Look for errors like "Bad directive" or "Invalid parameter"

**Solution:** Review and fix Redis configuration file

**Cause 3: Insufficient Memory**

Check system resources:
1. View **"Performance"** health check details
2. Look for memory warnings

**Solution:** Free up system memory or increase VM resources

**Cause 4: File Permission Issues**

Check Redis data directory permissions:

```bash
# On Redis VM
ls -la /var/lib/redis/
```

**Solution:** Ensure Redis user has read/write permissions

---

### Issue 2: Service Status Shows "Unknown"

**Symptoms:**
- Status badge shows gray "Unknown"
- Message: "Unable to determine service status"
- No health check data available

**Possible Causes & Solutions:**

**Cause 1: Redis VM Unreachable**

Check VM connectivity:
1. View VM info section
2. Check "SSH Accessible" status

**Solution:**
- Verify VM is running
- Check network connectivity
- Verify SSH key authentication

**Cause 2: SSH Connection Timeout**

**Solution:**
1. Wait 30 seconds for next health check
2. Click **"Refresh"** to retry immediately
3. If persists, contact administrator

**Cause 3: Firewall Blocking Connection**

**Solution:** Verify firewall rules allow SSH from main machine to Redis VM

---

### Issue 3: Auto-Recovery Keeps Failing

**Symptoms:**
- Status shows "Manual Intervention Required"
- Multiple recent recovery attempts
- Service repeatedly fails after starting

**Possible Causes & Solutions:**

**Cause 1: Configuration Error**

Redis starts but immediately crashes due to config error

**Solution:**
1. Click **"View Logs"** (admin only)
2. Identify configuration error
3. Fix configuration file
4. Restart service manually

**Cause 2: Resource Exhaustion**

Insufficient memory or disk space

**Solution:**
1. Check performance metrics
2. Free up resources
3. Increase VM resources if needed

**Cause 3: Corrupted Data Files**

Redis data files corrupted

**Solution:**
1. Backup current data
2. Remove corrupted files
3. Restore from backup if available
4. Restart service

---

### Issue 4: Slow Performance or High Response Times

**Symptoms:**
- Health status shows "Degraded"
- Response times >50ms
- Recommendations suggest performance issues

**Possible Causes & Solutions:**

**Cause 1: High Memory Usage**

Redis using >75% of available memory

**Solution:**
1. Review memory usage metrics
2. Clear unnecessary keys
3. Implement key expiration policies
4. Increase memory limit if needed

**Cause 2: Too Many Connections**

High connection count slowing responses

**Solution:**
1. Review connection count
2. Identify and close idle connections
3. Implement connection pooling in applications
4. Increase max connections if appropriate

**Cause 3: Slow Queries**

Complex or inefficient queries

**Solution:**
1. Enable slow query logging
2. Identify problematic queries
3. Optimize query patterns
4. Add appropriate indexes

---

### Issue 5: Permission Denied Errors

**Symptoms:**
- "403 Forbidden" error
- "Insufficient permissions" message
- Operation button disabled

**Solutions:**

1. **Verify Your Role:**
   - Check your current role in profile
   - Verify role has required permissions

2. **Request Access:**
   - Use "Contact Admin" button
   - Submit access request with justification

3. **Use Appropriate Account:**
   - Switch to account with required permissions
   - Login as admin if you have admin credentials

---

### Getting Help

If issues persist after troubleshooting:

1. **View Service Logs** (Admin):
   - Click "Show Logs"
   - Look for error patterns
   - Copy relevant log entries

2. **Check System Status:**
   - Navigate to System Status dashboard
   - Verify all dependent services healthy
   - Check for system-wide issues

3. **Contact Support:**
   - Click "Contact Support" button
   - Provide:
     - Current service status
     - Error messages
     - Recent operations performed
     - Your role and permissions
   - Attach logs if available

4. **Emergency Escalation:**
   - For critical issues affecting production
   - Use emergency contact procedures
   - Alert on-call administrator

---

## Best Practices

### Daily Operations

1. **Monitor Health Regularly**
   - Check service status at start of day
   - Review health metrics for trends
   - Act on recommendations promptly

2. **Plan Maintenance Windows**
   - Schedule restarts during low-usage periods
   - Notify users before planned maintenance
   - Have rollback plan ready

3. **Document Changes**
   - Record all service operations
   - Note reasons for interventions
   - Track patterns and issues

### Service Operations

1. **Before Restarting:**
   - Check current connection count
   - Notify active users if count >100
   - Ensure no critical processes running
   - Schedule during off-peak hours

2. **Before Stopping:**
   - Create backup of Redis data
   - Notify all users well in advance
   - Ensure dependent services can handle outage
   - Have restart plan ready
   - Only stop when absolutely necessary

3. **After Operations:**
   - Verify service returned to healthy state
   - Check all health checks passing
   - Monitor for 10-15 minutes
   - Verify dependent services recovered

### Monitoring

1. **Watch for Trends:**
   - Gradually increasing memory usage
   - Slowly increasing response times
   - Growing connection counts
   - These indicate potential issues

2. **Act on Warnings:**
   - Yellow "Degraded" status requires attention
   - Follow recommendations promptly
   - Don't wait for critical status

3. **Review Auto-Recovery:**
   - Check auto-recovery history weekly
   - Investigate repeated recoveries
   - Address root causes, not symptoms

### Security

1. **Protect Admin Credentials:**
   - Never share admin login
   - Use strong passwords
   - Enable two-factor authentication
   - Rotate passwords regularly

2. **Audit Log Review:**
   - Admins should review audit logs weekly
   - Look for unauthorized access attempts
   - Verify all operations were legitimate
   - Report suspicious activity

3. **Confirmation Dialogs:**
   - Always read confirmation dialogs completely
   - Type confirmation text carefully
   - Understand impact before confirming
   - Cancel if unsure

### Communication

1. **Notify Users:**
   - Inform users before planned operations
   - Provide estimated downtime
   - Explain reason for operation
   - Update status during maintenance

2. **Document Incidents:**
   - Record unexpected failures
   - Note auto-recovery effectiveness
   - Share learnings with team
   - Update procedures as needed

---

## Quick Reference Card

### Common Operations

| Task | Steps | Time | Permission |
|------|-------|------|------------|
| Check Status | Navigate to service page | Instant | Any |
| Start Service | Click "Start" → Wait | 10-15s | Operator |
| Restart Service | Click "Restart" → Confirm → Wait | 15-20s | Operator |
| Stop Service | Click "Stop" → Type "STOP" → Confirm → Wait | 8-10s | Admin |
| View Logs | Click "Show Logs" | Instant | Admin |
| Refresh Status | Click "Refresh" | 1-2s | Any |

### Status Indicators

- **●Green** - Healthy, no action needed
- **●Yellow** - Degraded, review recommendations
- **●Red** - Critical, immediate attention required
- **●Gray** - Unknown, check connectivity

### When to Contact Admin

- Auto-recovery shows "Manual Intervention Required"
- Service won't start after multiple attempts
- Repeated failures or crashes
- Permission denied for needed operation
- Suspicious activity in audit logs

---

## Additional Resources

**Documentation:**
- [API Documentation](/home/kali/Desktop/AutoBot/docs/api/REDIS_SERVICE_MANAGEMENT_API.md)
- [Operational Runbook](/home/kali/Desktop/AutoBot/docs/operations/REDIS_SERVICE_RUNBOOK.md)
- [Architecture Document](/home/kali/Desktop/AutoBot/docs/architecture/REDIS_SERVICE_MANAGEMENT_ARCHITECTURE.md)
- [Troubleshooting Guide](/home/kali/Desktop/AutoBot/docs/troubleshooting/comprehensive_troubleshooting_guide.md)

**Support:**
- Email: support@autobot.local
- Emergency: emergency@autobot.local
- Documentation: `/home/kali/Desktop/AutoBot/docs/`

---

**Document Version:** 1.0
**Last Updated:** 2025-10-10
**Maintained By:** AutoBot Documentation Team
