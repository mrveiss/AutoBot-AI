# Redis Directory Ownership Conflict - Comprehensive Research Report

**Research Date**: 2025-10-05
**Researcher**: DevOps Engineer (Claude)
**Priority**: CRITICAL - Production Data Persistence Failure
**Status**: Root Cause Identified

---

## Executive Summary

A three-way configuration conflict has been identified in the Redis Stack deployment causing **ACTIVE PRODUCTION FAILURES**. Redis background saves are failing with "Permission denied" errors, compromising data persistence and creating data loss risk.

**Root Cause**: Missing Ansible template file `redis-stack-server.service.j2` combined with conflicting ownership schemes across three configuration sources.

**Impact**: Redis cannot save RDB snapshots to disk. Data persistence is broken.

**Recommended Action**: Standardize on `redis:redis` ownership (matches Redis package standard) and create missing systemd service template.

---

## Current State Analysis

### Configuration Source Comparison

| Configuration Source | User | Group | Status | Authority |
|---------------------|------|-------|--------|-----------|
| **Systemd Service (VM)** | `autobot` | `autobot` | ACTIVE | What's actually running |
| **Ansible Playbook** | `redis-stack` | `redis-stack` | INTENDED | What deployment expects |
| **Start Script** | `redis` | `redis` | EXECUTED | What manual script sets |

### User/Group Existence on Redis VM (172.16.168.23)

```bash
# Users that EXIST:
redis:x:998:998::/var/lib/redis:/bin/false        # System user (package default)
autobot:x:1000:1000:autobot:/home/autobot:/bin/bash  # Normal user

# Users that DO NOT EXIST:
redis-stack                                        # Ansible tries to create this
```

### Directory and File Ownership (Current State)

```bash
/var/lib/redis-stack/
├── [drwxr-xr-x redis   redis   ] .                    # Directory owned by redis
├── [-rw-r--r-- autobot autobot ] dump.rdb             # File owned by autobot (MISMATCH!)
└── [-rwxr-xr-x autobot autobot ] temp-17297.rdb       # Temp owned by autobot (MISMATCH!)

/var/log/redis-stack/
└── [drwxr-xr-x redis   redis   ] .                    # Directory owned by redis
```

**Problem**: Service runs as `autobot:autobot` but directories are owned by `redis:redis`. When Redis tries to write files, it gets permission denied.

---

## Root Cause Analysis

### Primary Issue: Missing Ansible Template

**File Referenced**: `ansible/playbooks/deploy-database.yml` lines 154-160

```yaml
- name: Create Redis Stack systemd service
  template:
    src: redis-stack-server.service.j2      # THIS FILE DOES NOT EXIST
    dest: /etc/systemd/system/redis-stack-server.service
    mode: '0644'
  notify:
    - reload systemd
    - restart redis-stack
```

**Impact**:
- Template file `ansible/templates/systemd/redis-stack-server.service.j2` is missing
- Ansible task fails or skips silently
- Package-installed default service file is used instead
- Default service has been manually edited to use `User=autobot` (incorrect)

### Secondary Issue: Non-Existent User in Ansible Configuration

**File**: `ansible/playbooks/deploy-database.yml` lines 12-13

```yaml
vars:
  redis_user: "redis-stack"     # This user doesn't exist!
  redis_group: "redis-stack"    # This group doesn't exist!
```

**File**: `ansible/inventory/group_vars/database.yml` lines 243-244

```yaml
systemd_services:
  - name: "redis-stack-server"
    user: "redis-stack"          # Non-existent user
    group: "redis-stack"         # Non-existent group
```

**Impact**:
- Ansible playbook tries to create a non-standard user `redis-stack:redis-stack`
- This conflicts with the standard Redis package which creates `redis:redis`
- Creates unnecessary complexity and deviates from Redis ecosystem standards

### Tertiary Issue: Start Script Ownership Conflict

**File**: `scripts/vm-management/start-redis.sh` line 78

```bash
sudo chown redis:redis /var/lib/redis-stack /var/log/redis-stack
```

**Impact**:
- Start script sets ownership to `redis:redis` (correct, matches package standard)
- But systemd service runs as `autobot:autobot` (incorrect)
- Creates permission mismatch when service tries to write files

---

## Production Impact Assessment

### Active Failures (Happening Now)

**Error Logs** (from `journalctl -u redis-stack-server`):

```
Oct 05 09:51:44 autobot-database redis-stack-server[27746]: 27746:C 05 Oct 2025 09:51:44.042 # Failed opening the temp RDB file temp-27746.rdb (in server root dir /var/lib/redis-stack) for saving: Permission denied
Oct 05 09:51:44 autobot-database redis-stack-server[24864]: 24864:M 05 Oct 2025 09:51:44.143 # Background saving error
```

**Frequency**: Every RDB save interval (configured: 900s/1 change, 300s/10 changes, 60s/10000 changes)

### Data Persistence Risks

1. **RDB Snapshots Failing**: Cannot write point-in-time snapshots to disk
2. **AOF Potentially Affected**: If AOF writes also have permission issues
3. **Data Loss Risk**: Server restart will lose all data since last successful save
4. **Backup Failures**: Automated backup system cannot access current data files

### Service Health

- **Service Status**: Running (but degraded)
- **Redis Connectivity**: Working (in-memory operations functional)
- **Write Operations**: Working (in-memory)
- **Persistence**: BROKEN (disk writes failing)

---

## Redis Best Practices Research

### Official Redis Documentation (via Context7)

**Systemd Service Configuration** (from redis.io):

```ini
[Service]
User=redis-user      # Placeholder - should be actual system user
Group=redis-group    # Placeholder - should be actual system group
```

**Redis Enterprise Standard**:
- Uses dedicated system user: `redislabs:redislabs`
- System user with no login shell: `/bin/false`
- Dedicated user for security isolation

**Standard Redis Package Behavior**:
- Creates system user: `redis:redis` (uid=998, gid=998)
- Shell: `/bin/false` (no login)
- Home: `/var/lib/redis`
- This is the standard across Debian/Ubuntu/RHEL distributions

### Security Best Practices

1. **Dedicated System User**: Database services should run as dedicated system users
2. **No Login Shell**: System users should have `/bin/false` or `/usr/sbin/nologin`
3. **Principle of Least Privilege**: Service user should only have access to required directories
4. **Consistency**: Use standard package-created users when available

---

## Recommended Solution

### Primary Recommendation: Standardize on `redis:redis`

**Rationale**:
1. Matches Redis package standard (ecosystem compatibility)
2. User already exists (no additional user creation needed)
3. Properly configured as system user (uid=998, shell=/bin/false)
4. Follows Redis community best practices
5. Simplifies maintenance and troubleshooting

**Implementation**: Use `redis:redis` for all Redis-related ownership

### Alternative Solutions (Not Recommended)

#### Option 2: Use `redis-stack:redis-stack`
**Pros**: Separates Redis Stack from standard Redis
**Cons**:
- Non-standard, creates maintenance burden
- Requires manual user creation
- Deviates from package standards
- No ecosystem support

#### Option 3: Use `autobot:autobot`
**Pros**: Consistent with other AutoBot services
**Cons**:
- Normal user, not system user (security risk)
- Has login shell (violates security best practice)
- Wrong security model for database service
- Already causing production failures

---

## Files Requiring Updates

### 1. Create Missing Systemd Template

**File to Create**: `/home/kali/Desktop/AutoBot/ansible/templates/systemd/redis-stack-server.service.j2`

**Content**:
```jinja2
[Unit]
Description=Redis Stack Server for AutoBot
Documentation=https://redis.io/
After=network-online.target
Wants=network-online.target
Requires=network-online.target

[Service]
Type=notify
User={{ redis_user }}
Group={{ redis_group }}
ExecStart=/opt/redis-stack/bin/redis-stack-server {{ redis_config_dir }}/redis-stack.conf
WorkingDirectory={{ redis_home }}
Restart=always
RestartSec=5
TimeoutStopSec=10
KillMode=mixed
KillSignal=SIGTERM
SendSIGKILL=yes

# Resource limits
LimitNOFILE={{ systemd_services[0].limit_nofile | default(65536) }}
LimitMEMLOCK={{ systemd_services[0].limit_memlock | default('infinity') }}

# Security settings
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 2. Update Ansible Playbook Variables

**File**: `/home/kali/Desktop/AutoBot/ansible/playbooks/deploy-database.yml`

**Change lines 12-13**:
```yaml
# BEFORE (incorrect):
redis_user: "redis-stack"
redis_group: "redis-stack"

# AFTER (correct):
redis_user: "redis"
redis_group: "redis"
```

### 3. Update Ansible Group Variables

**File**: `/home/kali/Desktop/AutoBot/ansible/inventory/group_vars/database.yml`

**Change lines 243-244**:
```yaml
# BEFORE (incorrect):
user: "redis-stack"
group: "redis-stack"

# AFTER (correct):
user: "redis"
group: "redis"
```

**Change lines 400-403**:
```yaml
# BEFORE (incorrect):
redis_data_permissions:
  owner: "redis-stack"
  group: "redis-stack"

# AFTER (correct):
redis_data_permissions:
  owner: "redis"
  group: "redis"
```

### 4. Verify Start Script (No Changes Needed)

**File**: `/home/kali/Desktop/AutoBot/scripts/vm-management/start-redis.sh`

**Line 78** (already correct):
```bash
sudo chown redis:redis /var/lib/redis-stack /var/log/redis-stack
```

This is already correct and matches the recommended solution.

### 5. Update Systemd Service on Redis VM (172.16.168.23)

**File on VM**: `/etc/systemd/system/redis-stack-server.service`

**Current (incorrect)**:
```ini
User=autobot
Group=autobot
```

**Should be (will be deployed by fixed Ansible)**:
```ini
User=redis
Group=redis
```

---

## Implementation Checklist

### Phase 1: Create Missing Template (Local)
- [ ] Create `ansible/templates/systemd/redis-stack-server.service.j2`
- [ ] Review template for completeness
- [ ] Commit template to version control

### Phase 2: Update Ansible Configuration (Local)
- [ ] Update `ansible/playbooks/deploy-database.yml` (redis_user, redis_group)
- [ ] Update `ansible/inventory/group_vars/database.yml` (systemd_services user/group)
- [ ] Update `ansible/inventory/group_vars/database.yml` (redis_data_permissions)
- [ ] Review all Ansible files for additional `redis-stack` user references
- [ ] Commit all configuration changes

### Phase 3: Fix Directory Ownership (Redis VM)
- [ ] SSH to Redis VM: `ssh -i ~/.ssh/autobot_key autobot@172.16.168.23`
- [ ] Stop Redis service: `sudo systemctl stop redis-stack-server`
- [ ] Fix directory ownership: `sudo chown -R redis:redis /var/lib/redis-stack`
- [ ] Fix log ownership: `sudo chown -R redis:redis /var/log/redis-stack`
- [ ] Verify ownership: `ls -la /var/lib/redis-stack /var/log/redis-stack`

### Phase 4: Deploy Updated Configuration (Ansible)
- [ ] Deploy systemd service: `ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-database.yml --tags systemd`
- [ ] Verify service file deployed: `ssh autobot@172.16.168.23 "cat /etc/systemd/system/redis-stack-server.service | grep User="`
- [ ] Reload systemd: `ssh autobot@172.16.168.23 "sudo systemctl daemon-reload"`

### Phase 5: Restart and Verify
- [ ] Start Redis service: `ssh autobot@172.16.168.23 "sudo systemctl start redis-stack-server"`
- [ ] Check service status: `ssh autobot@172.16.168.23 "sudo systemctl status redis-stack-server"`
- [ ] Verify no permission errors: `ssh autobot@172.16.168.23 "sudo journalctl -u redis-stack-server -n 50 --no-pager | grep -i permission"`
- [ ] Test Redis connectivity: `redis-cli -h 172.16.168.23 ping`
- [ ] Verify RDB save works: `redis-cli -h 172.16.168.23 BGSAVE` (wait 10s) `redis-cli -h 172.16.168.23 LASTSAVE`
- [ ] Check file ownership after save: `ssh autobot@172.16.168.23 "ls -la /var/lib/redis-stack/dump.rdb"`

### Phase 6: Monitor and Validate
- [ ] Monitor logs for 1 hour: `ssh autobot@172.16.168.23 "sudo journalctl -u redis-stack-server -f"`
- [ ] Verify RDB saves succeed at scheduled intervals
- [ ] Confirm no permission denied errors
- [ ] Validate backup system can access data files

---

## Risk Assessment and Mitigation

### Risks During Implementation

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Service downtime during fix | High | Medium | Schedule during maintenance window, brief outage only |
| Data loss if service crashes | Low | High | Current data is in memory, complete fix before allowing restart |
| Ansible deployment failure | Low | Low | Manual deployment fallback available |
| Ownership change breaks other components | Very Low | Medium | Only affects Redis service, isolated component |

### Rollback Plan

If issues occur after implementation:

1. **Immediate**: Manually revert systemd service file on VM
2. **Short-term**: Revert Ansible changes from git
3. **Restore ownership**: `sudo chown -R autobot:autobot /var/lib/redis-stack` (restores current broken state)
4. **Service restart**: `sudo systemctl restart redis-stack-server`

**Note**: Current state is already broken (data persistence failing), so rollback returns to broken state. Fix should proceed.

---

## Lessons Learned

### What Went Wrong

1. **Incomplete Ansible Deployment**: Missing critical systemd service template
2. **Silent Failures**: Ansible task failures not caught during deployment
3. **Configuration Drift**: Manual edits (autobot user) diverged from intended config
4. **Lack of Monitoring**: Permission errors not detected until research
5. **Non-Standard Users**: Attempted to create `redis-stack` instead of using package standard `redis`

### Prevention Measures

1. **Template Validation**: Pre-deployment check for all referenced templates
2. **Ansible Error Handling**: Fail deployments on template errors, don't continue silently
3. **Configuration Testing**: Automated tests for service functionality after deployment
4. **Permission Monitoring**: Alerts for permission denied errors in service logs
5. **Standard Conformance**: Prefer package-created users over custom users

---

## References

### Documentation Reviewed

- Redis Official Documentation (via Context7 /websites/redis_io)
- Redis systemd service configuration best practices
- Redis Enterprise user/group standards
- Debian/Ubuntu package management standards
- AutoBot Ansible playbook structure

### Related Files

- `/home/kali/Desktop/AutoBot/ansible/playbooks/deploy-database.yml`
- `/home/kali/Desktop/AutoBot/ansible/inventory/group_vars/database.yml`
- `/home/kali/Desktop/AutoBot/scripts/vm-management/start-redis.sh`
- `/etc/systemd/system/redis-stack-server.service` (on Redis VM)

### Commands Used for Research

```bash
# Check systemd service configuration
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "cat /etc/systemd/system/redis-stack-server.service"

# Check directory ownership
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "ls -la /var/lib/redis-stack/"

# Check user existence
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "getent passwd redis; getent passwd redis-stack; getent passwd autobot"

# Check service status and errors
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "systemctl status redis-stack-server"
ssh -i ~/.ssh/autobot_key autobot@172.16.168.23 "journalctl -u redis-stack-server | grep -i permission"
```

---

## Conclusion

The Redis directory ownership conflict is a **critical production issue** requiring immediate resolution. The root cause is a missing Ansible template file combined with conflicting ownership schemes across three configuration sources.

**Recommended Solution**: Standardize on `redis:redis` ownership (matches Redis package standard and ecosystem best practices).

**Implementation Priority**: HIGH - Data persistence is currently broken, creating data loss risk.

**Estimated Fix Time**: 30 minutes (template creation + Ansible update + deployment + verification)

**Success Criteria**:
- Redis background saves complete without permission errors
- RDB snapshots successfully written to disk
- All files in `/var/lib/redis-stack/` owned by `redis:redis`
- Service runs as `redis:redis` per systemd configuration

---

**Report Compiled**: 2025-10-05
**Next Steps**: Proceed to Planning phase for implementation
