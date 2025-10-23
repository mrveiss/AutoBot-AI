# Service Authentication Day 2: Deployment Summary

**Date**: 2025-10-05
**Status**: ✅ Complete
**Phase**: Key Generation & Ansible Deployment Infrastructure

---

## 🎯 Objectives Achieved

### Task 3.5: Service Key Generation Script ✅

**File**: `scripts/generate_service_keys.py`

- **Purpose**: Generate 256-bit API keys for all 6 VMs and store in Redis
- **Features**:
  - Generates cryptographically secure keys using `secrets.token_bytes(32)`
  - Stores keys in Redis at `172.16.168.23:6379` with 90-day expiration
  - Creates timestamped backup YAML configuration
  - Verifies all keys are properly stored in Redis
  - Provides clear deployment instructions

**Execution Output**:
```
🔐 AutoBot Service Key Generation
============================================================
Timestamp: 2025-10-05T22:09:14.833802
Redis Host: 172.16.168.23:6379
Services: 6

✅ Generated 6 service keys
💾 Backup saved: config/service-keys/service-keys-20251005-220914.yaml

🔍 Verifying keys in Redis...
  ✅ main-backend: Key verified in Redis
  ✅ frontend: Key verified in Redis
  ✅ npu-worker: Key verified in Redis
  ✅ redis-stack: Key verified in Redis
  ✅ ai-stack: Key verified in Redis
  ✅ browser-service: Key verified in Redis
```

### Task 3.6: Ansible Deployment Playbook ✅

**File**: `ansible/playbooks/deploy-service-auth.yml`

- **Purpose**: Deploy service keys and authentication middleware to all 6 VMs
- **Deployment Architecture**:

```yaml
VM Mapping:
  main-backend  → 172.16.168.20 (WSL host)
  frontend      → 172.16.168.21
  npu-worker    → 172.16.168.22
  redis-stack   → 172.16.168.23
  ai-stack      → 172.16.168.24
  browser-service → 172.16.168.25
```

**Playbook Features**:

1. **Service Key Distribution**:
   - Creates `/etc/autobot/service-keys/` directory on all VMs (mode 0700)
   - Deploys service-specific `.env` files with keys (mode 0600)
   - Maps inventory groups to service IDs automatically
   - Verifies deployment on each VM

2. **Middleware Deployment** (Backend only):
   - Deploys `service_auth_logging.py` or `service_auth_enforcement.py`
   - Copies `service_auth.py` security module
   - Updates `app_factory.py` to load middleware
   - Restarts backend service

3. **Service Client Distribution**:
   - Deploys `service_client.py` to all VMs for authenticated requests
   - Ensures all services can make authenticated API calls

4. **Verification**:
   - Confirms key files exist on each VM
   - Provides deployment summary
   - Clear next-steps guidance

**Syntax Validation**: ✅ Passed
```bash
$ ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-service-auth.yml --syntax-check
playbook: ansible/playbooks/deploy-service-auth.yml
```

### Task 3.7: Deployment Test Script ✅

**File**: `scripts/test-service-auth-deployment.sh`

- **Purpose**: Pre-deployment validation and testing
- **Tests**:
  1. Ansible connectivity to all VMs
  2. Service keys exist in Redis
  3. Backup configuration file created

---

## 📦 Generated Service Keys

**Backup File**: `config/service-keys/service-keys-20251005-220914.yaml`

**Generated Keys** (256-bit hex):
```yaml
main-backend:
  key: ca164d91b9ae28ff...e1e641c3
  host: 172.16.168.20

frontend:
  key: d0f15188b26b624b...1fb66b12
  host: 172.16.168.21

npu-worker:
  key: 6a879ad99839b17b...1c84af69
  host: 172.16.168.22

redis-stack:
  key: 88efa3e65dac1d2e...00eeb660
  host: 172.16.168.23

ai-stack:
  key: 097dae86975597f3...a9516a52
  host: 172.16.168.24

browser-service:
  key: 7989d0efd1170415...bf493380
  host: 172.16.168.25
```

**Storage Locations**:
1. **Redis** (primary): `172.16.168.23:6379` under `service:key:{service_id}`
2. **Backup** (secure): `config/service-keys/service-keys-20251005-220914.yaml`
3. **VM Deployment** (after Ansible): `/etc/autobot/service-keys/{service_id}.env`

---

## 🔐 Security Measures Implemented

1. **Key Generation**:
   - Cryptographically secure 256-bit keys via `secrets.token_bytes(32)`
   - Unique key per service
   - 90-day expiration in Redis (auto-renewal supported)

2. **File Permissions**:
   - `/etc/autobot/service-keys/`: 0700 (owner-only access)
   - `{service_id}.env`: 0600 (read-only by autobot user)
   - Owned by `autobot:autobot` user/group

3. **Key Distribution**:
   - Each VM receives ONLY its own service key
   - Keys never stored in version control
   - Backup file flagged for secure handling/deletion

4. **Authentication Flow**:
   - HMAC-SHA256 signature verification
   - Timestamp-based replay attack prevention (5-minute window)
   - Constant-time signature comparison (timing attack prevention)

---

## 📋 Deployment Instructions

### Step 1: Generate Service Keys (✅ Complete)
```bash
python3 scripts/generate_service_keys.py
```

### Step 2: Deploy to VMs (Ready to Execute)
```bash
# Deploy in LOGGING mode (Day 2 - default)
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-service-auth.yml

# Verify deployment
ansible all -i ansible/inventory/production.yml -m shell -a 'ls -la /etc/autobot/service-keys/'
```

### Step 3: Monitor Logging Phase (24 hours)
```bash
# Monitor authentication attempts (backend VM)
tail -f /var/log/autobot/service-auth-audit.log

# Check for patterns
grep 'Auth' /var/log/autobot/*.log | grep 'service_id'
```

### Step 4: Switch to Enforcement Mode (Day 3)
```bash
ansible-playbook -i ansible/inventory/production.yml \
  ansible/playbooks/deploy-service-auth.yml \
  --extra-vars 'middleware_file=service_auth_enforcement.py'
```

---

## 🔄 Middleware Modes

### Logging Mode (Day 2 - Current)
- **File**: `backend/middleware/service_auth_logging.py`
- **Behavior**: Logs authentication attempts WITHOUT blocking
- **Purpose**: Observe traffic patterns, identify legitimate services
- **Duration**: 24 hours

### Enforcement Mode (Day 3 - Next)
- **File**: `backend/middleware/service_auth_enforcement.py`
- **Behavior**: Logs + BLOCKS unauthenticated requests
- **Purpose**: Full security enforcement
- **Trigger**: After logging analysis confirms no false positives

---

## 📊 Service-to-Service Authentication Matrix

| Source Service    | Target: Backend | Authentication Method           |
|-------------------|-----------------|----------------------------------|
| frontend          | ✅ Required     | X-Service-ID + X-Service-Signature |
| npu-worker        | ✅ Required     | X-Service-ID + X-Service-Signature |
| redis-stack       | ✅ Required     | X-Service-ID + X-Service-Signature |
| ai-stack          | ✅ Required     | X-Service-ID + X-Service-Signature |
| browser-service   | ✅ Required     | X-Service-ID + X-Service-Signature |
| main-backend      | N/A (self)      | Internal                         |

**Request Headers**:
```http
X-Service-ID: frontend
X-Service-Timestamp: 1728161354
X-Service-Signature: <HMAC-SHA256(service_key, "service_id:method:path:timestamp")>
```

---

## 🧪 Testing & Validation

### Pre-Deployment Tests
```bash
# Run test suite
bash scripts/test-service-auth-deployment.sh

# Expected output:
# 1. ✅ Ansible connectivity to all 6 VMs
# 2. ✅ Service keys verified in Redis
# 3. ✅ Backup configuration file created
```

### Post-Deployment Validation
```bash
# Verify key files on VMs
ansible all -i ansible/inventory/production.yml -m shell -a 'cat /etc/autobot/service-keys/$(hostname).env'

# Check backend middleware loaded
ansible backend -i ansible/inventory/production.yml -m shell -a 'grep "SERVICE AUTH MIDDLEWARE" /home/autobot/backend/app_factory.py'

# Test authenticated request (from frontend VM)
source /etc/autobot/service-keys/frontend.env
curl -H "X-Service-ID: $SERVICE_ID" \
     -H "X-Service-Timestamp: $(date +%s)" \
     -H "X-Service-Signature: $(generate_signature)" \
     http://172.16.168.20:8001/api/health
```

---

## 📁 Deliverables Summary

| Item | File Path | Status | Description |
|------|-----------|--------|-------------|
| Key Generation Script | `scripts/generate_service_keys.py` | ✅ | Generates & stores service keys |
| Ansible Deployment | `ansible/playbooks/deploy-service-auth.yml` | ✅ | Deploys keys + middleware |
| Test Script | `scripts/test-service-auth-deployment.sh` | ✅ | Pre-deployment validation |
| Service Keys Backup | `config/service-keys/service-keys-20251005-220914.yaml` | ✅ | Secure backup configuration |

---

## 🚀 Next Steps (Day 3)

1. **Deploy to VMs** (15 minutes):
   ```bash
   ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-service-auth.yml
   ```

2. **Monitor Logging Phase** (24 hours):
   - Review `/var/log/autobot/service-auth-audit.log`
   - Identify all legitimate service-to-service calls
   - Confirm no false positives

3. **Enable Enforcement** (5 minutes):
   ```bash
   ansible-playbook -i ansible/inventory/production.yml \
     ansible/playbooks/deploy-service-auth.yml \
     --extra-vars 'middleware_file=service_auth_enforcement.py'
   ```

4. **Final Validation**:
   - Verify authenticated services work correctly
   - Confirm unauthenticated requests are blocked (401)
   - Update documentation with enforcement status

---

## 🔒 Critical Security Notes

⚠️ **IMMEDIATE ACTIONS REQUIRED**:
1. ✅ Service keys generated and stored in Redis
2. ⏳ **PENDING**: Deploy keys to VMs via Ansible playbook
3. ⏳ **PENDING**: Secure/delete backup file after deployment verification
4. ⏳ **PENDING**: Monitor logging phase for 24 hours
5. ⏳ **PENDING**: Enable enforcement mode after validation

⚠️ **SECURITY REMINDERS**:
- Backup file contains sensitive keys - DELETE after deployment
- Keys stored in Redis have 90-day expiration - plan rotation
- `/etc/autobot/service-keys/` must remain 0700 permissions
- Monitor audit logs for anomalous authentication patterns

---

**Implementation Status**: 🟢 Day 2 Complete
**Next Phase**: Deploy to VMs & Begin 24-Hour Logging
**ETA to Enforcement**: 24-48 hours
