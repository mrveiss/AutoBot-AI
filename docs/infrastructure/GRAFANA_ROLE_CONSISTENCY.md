# Grafana Role Consistency

**Status:** ✅ Both roles produce identical working Grafana configurations

---

## Overview

AutoBot has two Ansible roles that can deploy Grafana:

1. **`slm_manager`** - Deploys Grafana on SLM server (172.16.168.19)
2. **`monitoring`** - Deploys Grafana on any node (dedicated monitoring VMs)

Both roles now ensure **repeatable, consistent configuration** regardless of where Grafana is deployed.

---

## Configuration Consistency

### Critical Settings (Present in Both Roles)

| Setting | Value | Purpose |
|---------|-------|---------|
| `serve_from_sub_path` | `true` | Allows serving from `/grafana/` subpath |
| `allow_embedding` | `true` | Enables iframe embedding in SLM frontend |
| `cookie_samesite` | `none` | Required for cross-origin iframe embedding |
| Anonymous auth | `enabled = true` | Allows unauthenticated access for embedding |
| Anonymous role | `Viewer` | Read-only access for anonymous users |

### Dashboard Deployment

Both roles deploy the same 14 AutoBot dashboards:
- `autobot-system.json` - System overview
- `autobot-overview.json` - General metrics
- `autobot-performance.json` - Performance metrics
- `autobot-multi-machine.json` - Fleet-wide monitoring
- `autobot-redis.json` - Redis metrics
- `autobot-api-health.json` - API health
- Plus 8 additional specialized dashboards

---

## Role Comparison

### `slm_manager` Role
**Location:** `autobot-slm-backend/ansible/roles/slm_manager/`

**Approach:** Uses `lineinfile` to modify specific settings
- Conditional installation based on `grafana_mode` variable
- Supports local and external Grafana hosts
- Modifies existing `/etc/grafana/grafana.ini` in-place

**Use Case:** SLM server deployment with flexible host configuration

### `monitoring` Role
**Location:** `autobot-slm-backend/ansible/roles/monitoring/`

**Approach:** Uses template to generate complete configuration
- Deploys full `grafana.ini` from template
- Installs Prometheus, Grafana, and Node Exporter together
- General-purpose monitoring stack for any node

**Use Case:** Dedicated monitoring VMs or fleet node monitoring

---

## Deployment Scenarios

### Scenario 1: Local Grafana on SLM Server
```yaml
# Uses slm_manager role
grafana_mode: local
grafana_install: true
```
**Result:** Grafana installed and configured on 172.16.168.19

### Scenario 2: External Grafana on Dedicated VM
```yaml
# Uses monitoring role on separate host
monitoring_install_grafana: true
grafana_allow_anonymous: true
```
**Result:** Grafana installed on monitoring VM (e.g., 172.16.168.28)

### Scenario 3: Proxied External Grafana
```yaml
# slm_manager points to external host
grafana_mode: external
grafana_external_host: 172.16.168.28
grafana_enable_cors: true
```
**Result:** SLM server proxies requests to external Grafana

---

## Verification

### Test Both Roles Produce Working Config

**Test 1: slm_manager Role**
```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-slm-manager.yml -i inventory.ini \
  --tags grafana --check
```

**Test 2: monitoring Role**
```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-monitoring.yml -i inventory.ini \
  -e monitoring_install_grafana=true --check
```

### Validate Configuration
```bash
# On Grafana host
grep -E "serve_from_sub_path|allow_embedding|cookie_samesite" /etc/grafana/grafana.ini

# Expected output:
# serve_from_sub_path = true
# cookie_samesite = none
# allow_embedding = true
```

### Test Dashboard Access
```bash
# All 6 dashboard types should return HTTP 200
for dash in autobot-system autobot-overview autobot-performance \
            autobot-multi-machine autobot-redis autobot-api-health; do
  curl -k -s -o /dev/null -w "$dash: %{http_code}\n" \
    "https://172.16.168.19/grafana/d/${dash}?kiosk=tv"
done
```

---

## Maintenance

### Adding New Dashboards

**Add to both locations:**
1. `infrastructure/shared/config/grafana/dashboards/new-dashboard.json`
2. Both roles will automatically deploy it on next run

### Changing Configuration

**For settings managed by both roles:**
1. Update `slm_manager/tasks/grafana.yml` (lineinfile tasks)
2. Update `monitoring/templates/grafana.ini.j2` (template)
3. Test both roles produce identical results

### Migration Path

**If SLM server was manually configured:**
```bash
# Re-apply Ansible configuration to make it idempotent
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-slm-manager.yml -i inventory.ini --tags grafana

# Verify settings
ssh autobot@172.16.168.19 "grep -E 'serve_from_sub_path|allow_embedding' /etc/grafana/grafana.ini"
```

---

## Related Documentation

- [GRAFANA_EXTERNAL_HOST_SETUP.md](GRAFANA_EXTERNAL_HOST_SETUP.md) - Complete external host guide
- [GRAFANA_QUICK_REFERENCE.md](GRAFANA_QUICK_REFERENCE.md) - Command reference

---

**Last Updated:** 2026-02-12  
**Related Issues:** #853 (dashboard fixes), #854 (external host support)
