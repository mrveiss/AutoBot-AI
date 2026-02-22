# Redis Service Management Operational Runbook

**Version:** 1.0
**Last Updated:** 2025-10-10
**Audience:** System Administrators, DevOps Engineers, Operations Team

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Service Overview](#service-overview)
3. [Health Monitoring](#health-monitoring)
4. [Auto-Recovery Operations](#auto-recovery-operations)
5. [Manual Intervention Procedures](#manual-intervention-procedures)
6. [Audit Log Review](#audit-log-review)
7. [Security Considerations](#security-considerations)
8. [Disaster Recovery](#disaster-recovery)
9. [Maintenance Procedures](#maintenance-procedures)
10. [Incident Response](#incident-response)
11. [Troubleshooting Decision Trees](#troubleshooting-decision-trees)
12. [Escalation Procedures](#escalation-procedures)

---

## Executive Summary

### Purpose

This runbook provides operational procedures for managing the Redis service within AutoBot's distributed infrastructure. It covers:
- Routine monitoring and health checks
- Auto-recovery system operation
- Manual intervention procedures
- Incident response protocols
- Disaster recovery procedures

### Critical Information

**Service Details:**
- **Service Name:** redis-server
- **Host:** VM3 (172.16.168.23)
- **Port:** 6379
- **systemd Unit:** redis-server.service
- **User:** redis
- **SSH User:** autobot (for management operations)

**Key Contacts:**
- **Primary Admin:** admin@autobot.local
- **Operations Team:** ops@autobot.local
- **Emergency:** emergency@autobot.local
- **On-Call Rotation:** See PagerDuty/on-call schedule

**Dependencies:**
- **Depends on:** Network connectivity, VM3 availability, SSH access
- **Depended by:** Backend API, Session Management, Cache System, Knowledge Base, Real-Time Features

**SLA Targets:**
- **Availability:** 99.9% uptime
- **Response Time:** <5ms (PING command)
- **Recovery Time:** <30 seconds (auto-recovery)
- **Manual Recovery:** <5 minutes (admin intervention)

---

## Service Overview

### Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Main Machine (WSL)                     │
│              172.16.168.20:8443                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │  RedisServiceManager                            │  │
│  │  • Service control operations                   │  │
│  │  • Health monitoring (every 30s)                │  │
│  │  • Auto-recovery orchestration                  │  │
│  │  • Audit logging                                │  │
│  └─────────────┬───────────────────────────────────┘  │
│                │ SSH (systemctl commands)             │
└────────────────┼─────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│                 Redis VM (VM3)                           │
│              172.16.168.23:6379                         │
│                                                         │
│  ┌─────────────────────────────────────────────────┐  │
│  │  systemd (redis-server.service)                 │  │
│  │  • Process management                           │  │
│  │  • Automatic restart on crash (disabled)        │  │
│  │  • Resource limits                              │  │
│  └─────────────┬───────────────────────────────────┘  │
│                │                                        │
│                ▼                                        │
│  ┌─────────────────────────────────────────────────┐  │
│  │  Redis Server Process                           │  │
│  │  • Port: 6379                                   │  │
│  │  • Config: /etc/redis/redis.conf               │  │
│  │  • Data: /var/lib/redis/                       │  │
│  │  • Logs: /var/log/redis/redis-server.log       │  │
│  └─────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### Service Characteristics

**Resource Requirements:**
- **Memory:** 128-4096 MB (dynamic, depends on data size)
- **CPU:** 1-2 cores (single-threaded operation)
- **Disk:** 10-50 GB (persistence files)
- **Network:** 6379/tcp (Redis protocol)

**Performance Baselines:**
- **Startup Time:** 8-15 seconds
- **Shutdown Time:** 5-10 seconds (graceful)
- **PING Response:** <5ms (healthy)
- **Connections:** 10-100 typical, 10000 max

**Data Persistence:**
- **RDB Snapshots:** Every 15 minutes (if data changed)
- **AOF:** Append-only file (optional, configured)
- **Location:** `/var/lib/redis/dump.rdb`

---

## Health Monitoring

### Monitoring Layers

#### Layer 1: Connectivity Health

**Check:** Redis PING command
**Frequency:** Every 30 seconds
**Timeout:** 5 seconds
**Failure Threshold:** 3 consecutive failures

**Command:**
```bash
redis-cli -h 172.16.168.23 -p 6379 PING
```

**Expected Response:** `PONG`

**Failure Indicators:**
- Connection refused
- Connection timeout
- No response within 5 seconds

**Actions on Failure:**
1. Increment failure counter
2. Log failure event
3. If threshold reached → Trigger auto-recovery

---

#### Layer 2: Systemd Health

**Check:** systemd service status
**Frequency:** Every 60 seconds
**Timeout:** 10 seconds

**Command:**
```bash
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "systemctl is-active redis-server"
```

**Expected Response:** `active`

**Possible States:**
- `active` - Service running normally (PASS)
- `inactive` - Service stopped (FAIL)
- `failed` - Service crashed or failed to start (FAIL)
- `activating` - Service starting (WAIT)
- `deactivating` - Service stopping (WAIT)

**Actions Based on State:**
- `active` → Continue monitoring
- `inactive` → Trigger standard recovery (start)
- `failed` → Trigger hard recovery (restart)
- `activating/deactivating` → Wait and recheck

---

#### Layer 3: Performance Health

**Check:** Resource metrics and performance indicators
**Frequency:** Every 120 seconds
**Timeout:** 15 seconds

**Metrics Collected:**

1. **Memory Usage:**
   ```bash
   redis-cli -h 172.16.168.23 INFO memory | grep used_memory_human
   ```
   - **Normal:** <3072 MB
   - **Warning:** 3072-4000 MB
   - **Critical:** >4000 MB

2. **Connection Count:**
   ```bash
   redis-cli -h 172.16.168.23 INFO clients | grep connected_clients
   ```
   - **Normal:** <8000
   - **Warning:** 8000-9500
   - **Critical:** >9500

3. **Commands Per Second:**
   ```bash
   redis-cli -h 172.16.168.23 INFO stats | grep instantaneous_ops_per_sec
   ```
   - **Normal:** <10000
   - **Warning:** 10000-50000
   - **Critical:** >50000 (may indicate attack)

4. **Response Time:**
   - Measure PING command latency
   - **Normal:** <5ms
   - **Warning:** 5-50ms
   - **Critical:** >50ms

**Actions Based on Metrics:**
- **Warning:** Log event, add recommendation
- **Critical:** Log event, send alert, consider manual intervention

---

### Health Check Dashboard

Operators can view health status in multiple places:

1. **Web Interface:**
   - URL: `http://172.16.168.21:5173/services/redis`
   - Real-time updates via WebSocket
   - Visual health indicators

2. **API Endpoint:**
   ```bash
   curl https://172.16.168.20:8443/api/services/redis/health
   ```

3. **Command Line:**
   ```bash
   # SSH to main machine
   cd /home/kali/Desktop/AutoBot
   python -m scripts.check_redis_health
   ```

---

## Auto-Recovery Operations

### Auto-Recovery System Overview

**Purpose:** Automatically detect and resolve Redis service failures without manual intervention

**Key Principles:**
- **Non-Invasive:** Minimal impact recovery attempts first
- **Progressive:** Escalate through recovery levels
- **Bounded:** Maximum 3 attempts before manual intervention
- **Logged:** All recovery actions fully audited

### Recovery Decision Logic

```
┌─────────────────────────────────────────────────────┐
│  Health Check Fails (3 consecutive failures)        │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│  Check systemd service status                       │
└─────────────────┬───────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
┌──────────────┐    ┌──────────────┐
│ Status:      │    │ Status:      │
│ active       │    │ inactive     │
│              │    │ or failed    │
└──────┬───────┘    └──────┬───────┘
       │                   │
       ▼                   ▼
┌──────────────┐    ┌──────────────┐
│ Soft         │    │ Standard     │
│ Recovery     │    │ Recovery     │
│ (reload)     │    │ (start)      │
└──────┬───────┘    └──────┬───────┘
       │                   │
       └─────────┬─────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────┐
│  Verify service healthy                             │
└─────────────────┬───────────────────────────────────┘
                  │
        ┌─────────┴─────────┐
        │                   │
        ▼                   ▼
┌──────────────┐    ┌──────────────┐
│ Success      │    │ Failure      │
│ Reset counter│    │ Try next     │
│ Log success  │    │ level        │
└──────────────┘    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Hard         │
                    │ Recovery     │
                    │ (restart)    │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Max attempts │
                    │ reached?     │
                    └──────┬───────┘
                           │
                 ┌─────────┴─────────┐
                 │                   │
                 ▼                   ▼
          ┌──────────┐        ┌──────────┐
          │ Success  │        │ Alert    │
          │          │        │ Admin    │
          └──────────┘        └──────────┘
```

### Recovery Levels Detailed

#### Level 1: Soft Recovery

**When Used:**
- Service status: `active`
- Connectivity: Failed
- Interpretation: Redis process hung/unresponsive

**Actions:**
```bash
# Send SIGHUP to reload configuration
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
  "sudo systemctl reload redis-server"
```

**Expected Duration:** 5-10 seconds

**Impact:**
- No connection drops
- Configuration reloaded
- Minimal disruption

**Success Criteria:**
- PING responds within 5 seconds
- Service status remains `active`

**If Fails:** Escalate to Standard Recovery

---

#### Level 2: Standard Recovery

**When Used:**
- Service status: `inactive`
- Service stopped normally

**Actions:**
```bash
# Start the service
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
  "sudo systemctl start redis-server"
```

**Expected Duration:** 10-20 seconds

**Impact:**
- Service starts fresh
- Previous connections lost (if any)
- Data loaded from persistence files

**Success Criteria:**
- Service status becomes `active`
- PING responds successfully
- Health checks pass

**If Fails:** Escalate to Hard Recovery

---

#### Level 3: Hard Recovery

**When Used:**
- Service status: `failed`
- Standard recovery failed
- Service won't start

**Actions:**
```bash
# Force restart the service
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
  "sudo systemctl restart redis-server"
```

**Expected Duration:** 20-30 seconds

**Impact:**
- Service forcefully restarted
- All connections terminated
- Memory cleared
- Data reloaded from disk

**Success Criteria:**
- Service status becomes `active`
- All health checks pass
- Stable for 60 seconds

**If Fails:** Manual intervention required

---

### Recovery Loop Prevention

**Circuit Breaker:**
- Tracks recovery attempts
- If 3 recoveries within 5 minutes → Disable auto-recovery
- Prevents infinite recovery loops
- Requires manual reset

**Manual Reset Procedure:**
```bash
# After fixing root cause, reset circuit breaker
curl -X POST https://172.16.168.20:8443/api/services/redis/reset-circuit-breaker \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

### Monitoring Auto-Recovery

**Audit Logs:**
```bash
# View recent auto-recovery attempts
tail -f /home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log | grep auto_recovery
```

**Recovery Metrics:**
- Total recoveries (last 24 hours)
- Success rate
- Average recovery time
- Most common recovery level

**Alerting:**
- Email on recovery failure
- Slack/Teams notification on critical alerts
- PagerDuty escalation if manual intervention required

---

## Manual Intervention Procedures

### When Manual Intervention is Required

1. **Auto-recovery disabled** (circuit breaker open)
2. **All recovery attempts failed**
3. **Root cause requires configuration changes**
4. **Security incident detected**
5. **Planned maintenance**

### Pre-Intervention Checklist

Before performing manual operations:

- [ ] Verify you have admin SSH access to Redis VM
- [ ] Check current service status and logs
- [ ] Review recent auto-recovery attempts
- [ ] Notify users of potential disruption
- [ ] Backup current configuration
- [ ] Document reason for intervention

### Standard Manual Procedures

#### Procedure 1: Manual Service Start

**When to Use:** Service stopped and won't auto-start

**Steps:**

1. **SSH to Redis VM:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23
   ```

2. **Check service status:**
   ```bash
   sudo systemctl status redis-server
   ```

3. **Review logs for errors:**
   ```bash
   sudo journalctl -u redis-server -n 50 --no-pager
   ```

4. **Identify and fix root cause** (see troubleshooting section)

5. **Start service:**
   ```bash
   sudo systemctl start redis-server
   ```

6. **Verify service started:**
   ```bash
   sudo systemctl status redis-server
   redis-cli PING
   ```

7. **Monitor for 5 minutes:**
   ```bash
   watch -n 10 'redis-cli INFO | grep -E "uptime_in_seconds|connected_clients"'
   ```

8. **Document intervention:**
   - Add entry to runbook history
   - Update incident ticket
   - Log root cause and resolution

---

#### Procedure 2: Manual Service Restart

**When to Use:** Service running but behaving abnormally

**Steps:**

1. **Check current state:**
   ```bash
   redis-cli -h 172.16.168.23 INFO | grep -E "uptime|memory|clients"
   ```

2. **Notify users** (if connection count >50):
   - Send notification via AutoBot UI
   - Post in team chat
   - Provide 5-minute warning

3. **Graceful restart:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo systemctl restart redis-server"
   ```

4. **Monitor startup:**
   ```bash
   # Watch service come back online
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo journalctl -u redis-server -f"
   ```
   - Wait for "Ready to accept connections" message
   - Verify no error messages

5. **Verify health:**
   ```bash
   curl https://172.16.168.20:8443/api/services/redis/health
   ```

6. **Confirm dependent services recovered:**
   - Check backend API health
   - Verify user sessions work
   - Test knowledge base search

---

#### Procedure 3: Configuration Change

**When to Use:** Modifying Redis configuration

**Steps:**

1. **Backup current configuration:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.backup.$(date +%Y%m%d_%H%M%S)"
   ```

2. **Edit configuration:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23
   sudo vim /etc/redis/redis.conf
   ```

3. **Validate configuration:**
   ```bash
   redis-server /etc/redis/redis.conf --test-memory 1
   ```

4. **Apply changes** (choose one):

   **Option A: Without restart (limited changes):**
   ```bash
   redis-cli CONFIG SET maxmemory 4gb
   redis-cli CONFIG REWRITE
   ```

   **Option B: With restart (major changes):**
   ```bash
   sudo systemctl restart redis-server
   ```

5. **Verify changes applied:**
   ```bash
   redis-cli CONFIG GET maxmemory
   ```

6. **Monitor for issues:**
   - Watch logs for 10 minutes
   - Verify all health checks passing
   - Test dependent services

7. **Document changes:**
   - Update configuration management
   - Add entry to change log
   - Update documentation if needed

---

#### Procedure 4: Emergency Stop

**When to Use:**
- Security incident
- Resource exhaustion threatening VM
- Corruption detected

**⚠️ Warning:** This will impact all AutoBot functionality

**Steps:**

1. **Verify necessity:**
   - Is this truly an emergency?
   - Can issue be resolved another way?
   - Have stakeholders been notified?

2. **Notify immediately:**
   ```bash
   # Send emergency notification
   curl -X POST https://172.16.168.20:8443/api/notifications/emergency \
     -H "Authorization: Bearer $ADMIN_TOKEN" \
     -d '{"message": "Redis emergency stop initiated", "reason": "..."}'
   ```

3. **Stop service:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo systemctl stop redis-server"
   ```

4. **Verify stopped:**
   ```bash
   sudo systemctl status redis-server
   ps aux | grep redis
   ```

5. **Address emergency:**
   - Investigate root cause
   - Fix security issue
   - Free up resources
   - Repair corruption

6. **Plan recovery:**
   - Determine if data recovery needed
   - Prepare rollback plan
   - Schedule restart

7. **Restart when safe:**
   ```bash
   sudo systemctl start redis-server
   ```

8. **Full verification:**
   - All health checks passing
   - Dependent services recovered
   - Performance normal
   - Monitor closely for 30 minutes

---

## Audit Log Review

### Audit Log Location

**Primary Log:**
```
/home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log
```

**Systemd Journal:**
```bash
sudo journalctl -u redis-server --since "1 hour ago"
```

### Audit Log Format

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

### Routine Audit Tasks

#### Daily Review (5 minutes)

```bash
# Review all operations in last 24 hours
grep -A 5 "service_operation" \
  /home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log \
  | tail -50
```

**Check for:**
- Any failed operations
- Operations by unexpected users
- Operations at unusual times
- Multiple operations in short period

#### Weekly Review (15 minutes)

1. **Operation Summary:**
   ```bash
   # Count operations by type
   grep "service_operation" \
     /home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log \
     | jq -r '.operation' | sort | uniq -c
   ```

2. **User Activity:**
   ```bash
   # List all users who performed operations
   grep "service_operation" \
     /home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log \
     | jq -r '.user.email' | sort | uniq -c
   ```

3. **Failure Analysis:**
   ```bash
   # Show all failed operations
   grep '"success": false' \
     /home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log
   ```

4. **Auto-Recovery Summary:**
   ```bash
   # Count auto-recovery attempts
   grep "auto_recovery" \
     /home/kali/Desktop/AutoBot/logs/audit/redis_service_management.log \
     | jq -r '.recovery_level' | sort | uniq -c
   ```

#### Monthly Review (30 minutes)

1. **Trends Analysis:**
   - Plot operations over time
   - Identify usage patterns
   - Detect anomalies

2. **Performance Review:**
   - Average operation duration
   - Success rate trends
   - Auto-recovery effectiveness

3. **Security Audit:**
   - Review all admin operations
   - Verify proper authorization
   - Check for policy violations

4. **Recommendations:**
   - Identify areas for improvement
   - Update procedures if needed
   - Adjust monitoring thresholds

### Audit Alert Conditions

**Immediate Alert:**
- Failed operation by admin
- 3+ operations within 1 minute
- Operation from unexpected IP
- Security validation failure

**Daily Summary:**
- Any auto-recovery attempts
- Multiple failed operations
- Operations outside business hours

### Audit Log Rotation

**Configuration:**
```yaml
# /home/kali/Desktop/AutoBot/config/logging.yaml
redis_service_audit:
  file: logs/audit/redis_service_management.log
  max_size: 100MB
  backup_count: 10
  rotate_on: size
  compression: gzip
```

**Manual Rotation:**
```bash
# Force log rotation
logrotate -f /etc/logrotate.d/autobot-redis-audit
```

---

## Security Considerations

### SSH Key Management

**Key Location:**
```
~/.ssh/autobot_key (4096-bit RSA)
```

**Key Permissions:**
```bash
# Verify correct permissions
ls -l ~/.ssh/autobot_key
# Should show: -rw------- (600)

# Fix if needed
chmod 600 ~/.ssh/autobot_key
```

**Key Rotation Procedure:**

1. **Generate new key:**
   ```bash
   ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key_new -C "autobot-redis-$(date +%Y%m%d)"
   ```

2. **Deploy new key to Redis VM:**
   ```bash
   ssh-copy-id -i ~/.ssh/autobot_key_new autobot@172.16.168.23
   ```

3. **Test new key:**
   ```bash
   ssh -i ~/.ssh/autobot_key_new autobot@172.16.168.23 "echo 'Key works'"
   ```

4. **Update AutoBot configuration:**
   ```bash
   # Update key reference in config
   vim /home/kali/Desktop/AutoBot/config/ssh.yaml
   ```

5. **Rotate keys:**
   ```bash
   mv ~/.ssh/autobot_key ~/.ssh/autobot_key_old
   mv ~/.ssh/autobot_key_new ~/.ssh/autobot_key
   ```

6. **Remove old key from VM after 24 hours:**
   ```bash
   ssh autobot@172.16.168.23 "sed -i '/old_key_fingerprint/d' ~/.ssh/authorized_keys"
   ```

### Sudo Permissions

**Configuration File:**
```
/etc/sudoers.d/autobot-redis (on Redis VM)
```

**Content:**
```bash
# Allow autobot user to manage Redis service
autobot ALL=(ALL) NOPASSWD: /bin/systemctl start redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl stop redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl restart redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl reload redis-server
autobot ALL=(ALL) NOPASSWD: /bin/systemctl status redis-server
autobot ALL=(ALL) NOPASSWD: /bin/journalctl -u redis-server *
```

**Verify Permissions:**
```bash
# Test sudo access
ssh autobot@172.16.168.23 "sudo -l"
```

### Command Validation

**Whitelist Enforcement:**

Only these commands are allowed:
- `sudo systemctl start redis-server`
- `sudo systemctl stop redis-server`
- `sudo systemctl restart redis-server`
- `sudo systemctl reload redis-server`
- `systemctl status redis-server`
- `systemctl is-active redis-server`
- `journalctl -u redis-server -n {lines}`

**No arbitrary commands permitted.**

### Security Monitoring

**Watch for:**
- Repeated failed operations
- Operations from unexpected IPs
- After-hours admin operations
- Permission escalation attempts
- SSH brute force attempts
- Unauthorized configuration changes

**Response:**
1. Alert security team
2. Review audit logs
3. Disable affected accounts
4. Investigate root cause
5. Update security policies

---

## Disaster Recovery

### Backup Procedures

#### Daily Automated Backup

**Backup Script Location:**
```bash
/home/kali/Desktop/AutoBot/scripts/backup_redis.sh
```

**Backup Content:**
- Redis data (`dump.rdb`)
- AOF file (if enabled)
- Configuration file
- Service state

**Backup Location:**
```
/home/kali/Desktop/AutoBot/backups/redis/daily/
```

**Verification:**
```bash
# Check latest backup
ls -lh /home/kali/Desktop/AutoBot/backups/redis/daily/ | tail -5

# Verify backup integrity
redis-check-rdb /home/kali/Desktop/AutoBot/backups/redis/daily/latest/dump.rdb
```

#### Manual Backup Procedure

```bash
# Create on-demand backup
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 << 'EOF'
  # Trigger save
  redis-cli BGSAVE

  # Wait for save to complete
  while redis-cli LASTSAVE | grep -q "$(date +%s)"; do
    sleep 1
  done

  # Copy backup
  sudo cp /var/lib/redis/dump.rdb "/tmp/dump-$(date +%Y%m%d_%H%M%S).rdb"
EOF

# Download backup
scp -i ~/.ssh/autobot_key \
  autobot@172.16.168.23:/tmp/dump-*.rdb \
  /home/kali/Desktop/AutoBot/backups/redis/manual/
```

### Recovery Procedures

#### Scenario 1: Data Corruption

**Symptoms:**
- Redis starts but crashes immediately
- Error: "Invalid RDB format"
- Auto-recovery fails repeatedly

**Recovery Steps:**

1. **Stop Redis service:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo systemctl stop redis-server"
   ```

2. **Backup corrupted data:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo cp /var/lib/redis/dump.rdb /var/lib/redis/dump.rdb.corrupted"
   ```

3. **Restore from backup:**
   ```bash
   # Copy backup to Redis VM
   scp -i ~/.ssh/autobot_key \
     /home/kali/Desktop/AutoBot/backups/redis/daily/latest/dump.rdb \
     autobot@172.16.168.23:/tmp/

   # Replace corrupted file
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 << 'EOF'
     sudo mv /tmp/dump.rdb /var/lib/redis/dump.rdb
     sudo chown redis:redis /var/lib/redis/dump.rdb
     sudo chmod 640 /var/lib/redis/dump.rdb
   EOF
   ```

4. **Start Redis:**
   ```bash
   ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 \
     "sudo systemctl start redis-server"
   ```

5. **Verify data integrity:**
   ```bash
   redis-cli -h 172.16.168.23 DBSIZE
   redis-cli -h 172.16.168.23 INFO persistence
   ```

6. **Test functionality:**
   - Verify user sessions work
   - Test cache operations
   - Check knowledge base

**Data Loss:** Up to 24 hours (last daily backup)

#### Scenario 2: VM Failure

**Symptoms:**
- VM3 completely unavailable
- Cannot SSH to Redis VM
- Network unreachable

**Recovery Steps:**

1. **Assess VM status:**
   - Check hypervisor
   - Verify VM powered on
   - Check network connectivity

2. **Attempt VM recovery:**
   ```bash
   # If VM is stopped, start it
   # Method depends on hypervisor (VirtualBox, VMware, etc.)
   ```

3. **If VM unrecoverable, rebuild:**

   **Option A: Restore VM from snapshot**
   - Restore latest VM snapshot
   - Verify Redis service starts
   - Restore latest data backup

   **Option B: Deploy new Redis VM**
   - Provision new VM at 172.16.168.23
   - Install Redis
   - Configure service
   - Restore data from backup
   - Update SSH keys
   - Test connectivity

4. **Verify full system recovery:**
   ```bash
   # Test all health checks
   curl https://172.16.168.20:8443/api/services/redis/health

   # Test from backend
   redis-cli -h 172.16.168.23 PING
   ```

**RTO (Recovery Time Objective):** 30 minutes (VM restore) or 2 hours (new VM)

**RPO (Recovery Point Objective):** 24 hours (daily backups)

#### Scenario 3: Complete System Failure

**Recovery Steps:**

1. **Restore from full system backup**
2. **Follow standard deployment procedure**
3. **Restore Redis data from backup**
4. **Verify all services**

**Refer to:**
- [Comprehensive Deployment Guide](/home/kali/Desktop/AutoBot/docs/deployment/comprehensive_deployment_guide.md)
- [Disaster Recovery Plan](/home/kali/Desktop/AutoBot/docs/operations/disaster_recovery.md)

---

## Maintenance Procedures

### Routine Maintenance Schedule

| Task | Frequency | Duration | Downtime |
|------|-----------|----------|----------|
| Restart service | Monthly | 15-20s | Yes (brief) |
| Update Redis | Quarterly | 10-30 min | Yes |
| Configuration review | Monthly | 30 min | No |
| Security audit | Monthly | 1 hour | No |
| Backup verification | Weekly | 15 min | No |
| Log rotation | Automated | N/A | No |
| Performance tuning | As needed | 1-2 hours | Possibly |

### Planned Maintenance Windows

**Standard Windows:**
- **Weekly:** Sunday 02:00-04:00 UTC (minimal activity)
- **Monthly:** First Sunday 01:00-05:00 UTC (major maintenance)

**Notification Requirements:**
- Announce 48 hours in advance
- Send reminder 24 hours before
- Post in team chat 1 hour before
- Display banner in UI during maintenance

### Maintenance Procedure Template

1. **Pre-Maintenance:**
   - [ ] Schedule maintenance window
   - [ ] Notify users
   - [ ] Create backup
   - [ ] Review change plan
   - [ ] Prepare rollback procedure
   - [ ] Verify access and credentials

2. **During Maintenance:**
   - [ ] Execute change (documented steps)
   - [ ] Monitor for issues
   - [ ] Document any deviations
   - [ ] Capture logs

3. **Post-Maintenance:**
   - [ ] Verify service healthy
   - [ ] Run smoke tests
   - [ ] Monitor for 30 minutes
   - [ ] Update documentation
   - [ ] Send completion notice
   - [ ] Post-mortem (if issues)

### Redis Version Update Procedure

**Preparation:**

1. **Check release notes:**
   - Review changes in new version
   - Identify breaking changes
   - Check compatibility with current config

2. **Test in non-production:**
   - Deploy to test environment
   - Run test suite
   - Performance benchmarks

3. **Plan rollback:**
   - Backup current version
   - Document rollback steps
   - Test rollback procedure

**Execution:**

1. **Backup everything:**
   ```bash
   # Data backup
   ssh autobot@172.16.168.23 "redis-cli BGSAVE"

   # Config backup
   ssh autobot@172.16.168.23 \
     "sudo cp /etc/redis/redis.conf /etc/redis/redis.conf.pre-upgrade"
   ```

2. **Update Redis:**
   ```bash
   ssh autobot@172.16.168.23 << 'EOF'
     # Stop service
     sudo systemctl stop redis-server

     # Update package
     sudo apt update
     sudo apt install --only-upgrade redis-server

     # Verify installation
     redis-server --version

     # Start service
     sudo systemctl start redis-server
   EOF
   ```

3. **Verify update:**
   ```bash
   # Check version
   redis-cli -h 172.16.168.23 INFO server | grep redis_version

   # Run health checks
   curl https://172.16.168.20:8443/api/services/redis/health

   # Test functionality
   redis-cli -h 172.16.168.23 SET test "upgrade-success"
   redis-cli -h 172.16.168.23 GET test
   ```

4. **Monitor post-upgrade:**
   - Watch logs for errors
   - Monitor performance metrics
   - Verify dependent services

**Rollback (if needed):**

```bash
ssh autobot@172.16.168.23 << 'EOF'
  # Stop current version
  sudo systemctl stop redis-server

  # Downgrade package
  sudo apt install redis-server=<previous_version>

  # Restore config
  sudo cp /etc/redis/redis.conf.pre-upgrade /etc/redis/redis.conf

  # Restore data (if needed)
  sudo cp /var/lib/redis/dump.rdb.pre-upgrade /var/lib/redis/dump.rdb

  # Start service
  sudo systemctl start redis-server
EOF
```

---

## Incident Response

### Incident Severity Levels

#### Severity 1: Critical (P1)

**Definition:**
- Redis completely unavailable
- All dependent services failing
- User impact: 100% of users affected
- Business impact: Critical functionality down

**Response Time:** Immediate
**Notification:** All stakeholders + emergency escalation
**Resolution Target:** <1 hour

**Actions:**
1. Page on-call admin immediately
2. Initiate emergency response
3. Start war room/incident channel
4. Execute emergency recovery procedures
5. Provide status updates every 15 minutes

#### Severity 2: High (P2)

**Definition:**
- Redis degraded but available
- Intermittent failures
- User impact: 50%+ users affected
- Business impact: Major functionality impaired

**Response Time:** <15 minutes
**Notification:** Operations team + management
**Resolution Target:** <4 hours

**Actions:**
1. Alert operations team
2. Investigate root cause
3. Implement mitigation
4. Monitor closely
5. Status updates every 30 minutes

#### Severity 3: Medium (P3)

**Definition:**
- Redis performance issues
- Non-critical features affected
- User impact: <50% users affected
- Business impact: Minor functionality impaired

**Response Time:** <1 hour
**Notification:** Operations team
**Resolution Target:** <24 hours

**Actions:**
1. Create incident ticket
2. Investigate during business hours
3. Plan fix
4. Implement fix during maintenance window

#### Severity 4: Low (P4)

**Definition:**
- Cosmetic issues
- No user impact
- No business impact

**Response Time:** Best effort
**Notification:** Internal only
**Resolution Target:** <1 week

### Incident Response Workflow

```
┌─────────────────────────────────────────────────┐
│  Incident Detected                              │
│  (Alert, user report, monitoring)               │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Assess Severity (P1/P2/P3/P4)                  │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Notify Appropriate Team                        │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Incident Response Actions:                     │
│  • Assign incident commander                    │
│  • Open incident channel                        │
│  • Begin investigation                          │
│  • Document findings                            │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Implement Fix                                  │
│  • Apply mitigation                             │
│  • Verify resolution                            │
│  • Monitor stability                            │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│  Post-Incident Activities:                      │
│  • Document timeline                            │
│  • Root cause analysis                          │
│  • Lessons learned                              │
│  • Preventive measures                          │
└─────────────────────────────────────────────────┘
```

### Incident Communication Template

**Initial Notification:**
```
INCIDENT ALERT - Redis Service [P1/P2/P3/P4]

Severity: [P1/P2/P3/P4]
Service: Redis
Status: Investigating
Detected: [timestamp]
Impact: [description]

Current Status:
[What's happening]

Actions Taken:
[What we're doing]

Next Update: [time]

Incident Commander: [name]
```

**Status Update:**
```
INCIDENT UPDATE - Redis Service [P1/P2/P3/P4]

Incident: [ID]
Time: [timestamp]
Status: [Investigating/Mitigated/Resolved]

Progress:
[What's been done]

Current Work:
[What we're working on]

ETA: [estimated resolution time]

Next Update: [time]
```

**Resolution Notice:**
```
INCIDENT RESOLVED - Redis Service

Incident: [ID]
Duration: [time from start to resolution]
Resolution: [timestamp]

Summary:
[What happened]

Root Cause:
[Why it happened]

Resolution:
[How it was fixed]

Preventive Measures:
[What we're doing to prevent recurrence]

Post-Mortem: [link to detailed analysis]
```

---

## Troubleshooting Decision Trees

### Decision Tree 1: Service Won't Start

```
Service won't start
    │
    ├─ Check: systemctl status
    │   ├─ "Address already in use" → Port conflict
    │   │   └─ ACTION: Identify and stop conflicting process
    │   │
    │   ├─ "Permission denied" → Permission issue
    │   │   └─ ACTION: Check file permissions and ownership
    │   │
    │   ├─ "Configuration error" → Config problem
    │   │   └─ ACTION: Validate and fix configuration
    │   │
    │   └─ "Out of memory" → Resource issue
    │       └─ ACTION: Free memory or increase limits
    │
    └─ Check: Redis logs
        ├─ "Can't open config file" → Config missing/unreadable
        │   └─ ACTION: Restore config from backup
        │
        ├─ "Can't write to log file" → Log permissions
        │   └─ ACTION: Fix log directory permissions
        │
        └─ "Disk full" → Disk space issue
            └─ ACTION: Free disk space
```

### Decision Tree 2: Performance Degradation

```
Slow response times
    │
    ├─ Check: Memory usage
    │   ├─ High (>75%) → Memory pressure
    │   │   ├─ ACTION: Identify large keys
    │   │   ├─ ACTION: Implement key expiration
    │   │   └─ ACTION: Consider increasing memory
    │   │
    │   └─ Normal → Not memory issue
    │
    ├─ Check: Connection count
    │   ├─ High (>80%) → Connection pressure
    │   │   ├─ ACTION: Identify connection sources
    │   │   ├─ ACTION: Implement connection pooling
    │   │   └─ ACTION: Increase max connections
    │   │
    │   └─ Normal → Not connection issue
    │
    ├─ Check: CPU usage
    │   ├─ High (>70%) → CPU bottleneck
    │   │   ├─ ACTION: Identify expensive commands
    │   │   ├─ ACTION: Optimize queries
    │   │   └─ ACTION: Consider vertical scaling
    │   │
    │   └─ Normal → Not CPU issue
    │
    └─ Check: Network latency
        ├─ High (>10ms) → Network issue
        │   ├─ ACTION: Check network connectivity
        │   ├─ ACTION: Verify no packet loss
        │   └─ ACTION: Check firewall rules
        │
        └─ Normal → Check application queries
```

### Decision Tree 3: Auto-Recovery Failing

```
Auto-recovery fails
    │
    ├─ Check: Recovery attempts
    │   ├─ Max attempts reached → Circuit breaker open
    │   │   └─ ACTION: Investigate root cause, manual intervention
    │   │
    │   └─ Still attempting → In progress
    │
    ├─ Check: systemd status
    │   ├─ "failed" → Service crashed
    │   │   ├─ Check logs for crash reason
    │   │   └─ ACTION: Fix root cause, manual restart
    │   │
    │   ├─ "activating" → Service starting slowly
    │   │   └─ ACTION: Wait, check for startup issues
    │   │
    │   └─ "inactive" → Service stopped cleanly
    │       └─ ACTION: Investigate why stopped
    │
    └─ Check: SSH connectivity
        ├─ SSH fails → Cannot execute commands
        │   └─ ACTION: Fix network/SSH issues
        │
        └─ SSH works → Command execution issue
            └─ ACTION: Check sudo permissions
```

---

## Escalation Procedures

### Escalation Matrix

| Level | Contact | When to Escalate | Response Time |
|-------|---------|------------------|---------------|
| **L1** | Operations Team | Initial response | Immediate |
| **L2** | Senior Admin | L1 cannot resolve in 30 min | <15 min |
| **L3** | Engineering Team | Requires code changes | <1 hour |
| **L4** | CTO/VP Engineering | Business-critical incident | Immediate |

### Escalation Triggers

**Escalate from L1 to L2 when:**
- Incident unresolved after 30 minutes
- Root cause unclear
- Multiple systems affected
- P1 incident

**Escalate from L2 to L3 when:**
- Code changes required
- Architecture changes needed
- Incident unresolved after 2 hours
- Recurring incidents

**Escalate from L3 to L4 when:**
- Extended outage (>4 hours)
- Data loss risk
- Security breach
- Customer-facing impact

### Contact Information

**Operations Team:**
- Email: ops@autobot.local
- Slack: #ops-redis
- Phone: +1-XXX-XXX-XXXX

**Senior Admin:**
- Email: admin@autobot.local
- Slack: @senior-admin
- Phone: +1-XXX-XXX-XXXX

**Engineering Team:**
- Email: engineering@autobot.local
- Slack: #engineering-escalation
- On-Call: PagerDuty rotation

**Executive:**
- Email: cto@autobot.local
- Phone: +1-XXX-XXX-XXXX (emergencies only)

---

## Appendix A: Quick Reference Commands

### Health Checks

```bash
# Quick health check
redis-cli -h 172.16.168.23 PING

# Service status
ssh autobot@172.16.168.23 "systemctl status redis-server"

# Full health via API
curl https://172.16.168.20:8443/api/services/redis/health

# Memory usage
redis-cli -h 172.16.168.23 INFO memory | grep used_memory_human

# Connection count
redis-cli -h 172.16.168.23 INFO clients | grep connected_clients
```

### Service Control

```bash
# Start
ssh autobot@172.16.168.23 "sudo systemctl start redis-server"

# Stop
ssh autobot@172.16.168.23 "sudo systemctl stop redis-server"

# Restart
ssh autobot@172.16.168.23 "sudo systemctl restart redis-server"

# Reload config
ssh autobot@172.16.168.23 "sudo systemctl reload redis-server"
```

### Logs

```bash
# Recent logs
ssh autobot@172.16.168.23 "sudo journalctl -u redis-server -n 50"

# Follow logs
ssh autobot@172.16.168.23 "sudo journalctl -u redis-server -f"

# Errors only
ssh autobot@172.16.168.23 "sudo journalctl -u redis-server -p err"
```

### Performance

```bash
# Full INFO
redis-cli -h 172.16.168.23 INFO

# Slow queries
redis-cli -h 172.16.168.23 SLOWLOG GET 10

# Key statistics
redis-cli -h 172.16.168.23 --bigkeys
```

---

## Appendix B: Configuration Files

### Redis Configuration

**Location:** `/etc/redis/redis.conf` (on Redis VM)

**Key Settings:**
```ini
# Network
bind 0.0.0.0
port 6379
protected-mode yes

# Memory
maxmemory 4gb
maxmemory-policy allkeys-lru

# Persistence
save 900 1
save 300 10
save 60 10000
dir /var/lib/redis/

# Logging
loglevel notice
logfile /var/log/redis/redis-server.log

# Clients
maxclients 10000
```

### AutoBot Service Management Config

**Location:** `/home/kali/Desktop/AutoBot/config/services/redis_service_management.yaml`

**Key Settings:**
```yaml
health_check:
  interval_seconds: 30
  failure_threshold: 3

auto_recovery:
  enabled: true
  max_attempts: 3
  retry_delay_seconds: 10

permissions:
  start: [admin, operator]
  stop: [admin]
  restart: [admin, operator]
```

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-10 | AutoBot Ops Team | Initial operational runbook |

---

**Document Version:** 1.0
**Last Updated:** 2025-10-10
**Maintained By:** AutoBot Operations Team
**Review Schedule:** Quarterly

**For questions or updates, contact:** ops@autobot.local
