# Runbook: Assign a Role to a Node

**Issue #926 Phase 8** | Last updated: 2026-02-18

---

## Overview

This runbook describes how to assign an additional role to an existing fleet node. This is different from provisioning a new node — the node already exists and has at least `autobot-slm-agent` running.

Pre-flight coexistence checks are mandatory before assignment.

---

## Prerequisites

- Target node is in the fleet and healthy
- `autobot-slm-backend/ansible/` is the working directory
- SLM server (`.19`) is running and healthy
- You know which role to assign (see [Role Catalogue](../architecture/ROLE_ARCHITECTURE.md))

---

## Step 1: Pre-Flight Coexistence Check

Before assigning, verify the role can coexist with existing roles on the node.

```bash
# Check what roles are currently on the node
curl -sk https://172.16.168.19/api/nodes/<node-id> \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  | jq '.roles'

# Check the coexistence matrix
# See docs/architecture/COEXISTENCE_MATRIX.md
```

**Hard conflicts that SLM will block:**

| Role | Conflicts With | Reason |
|------|---------------|--------|
| `autobot-frontend` | `autobot-slm-frontend` (same nginx) | Port 443 / separate nginx instances |
| `autobot-monitoring` | `autobot-browser-worker` | Port 3000 (Grafana vs Playwright) |
| `autobot-database` | `autobot-slm-database` | Port 5432 (two PostgreSQL instances) |

If a hard conflict exists, you must either:
- Choose a different node
- Remove the conflicting role first (see `docs/runbooks/` for role removal)

---

## Step 2: Update Ansible Inventory

Edit `autobot-slm-backend/ansible/inventory/slm-nodes.yml` to add the new role:

```yaml
04-Database:
  ansible_host: 172.16.168.23
  ansible_user: autobot
  node_roles:
    - autobot-database
    - autobot-slm-agent
    - autobot-monitoring    # ← adding this
```

---

## Step 3: Update SLM Database

Register the new role assignment in SLM:

```bash
curl -sk -X POST https://172.16.168.19/api/nodes/<node-id>/roles \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"role": "autobot-monitoring"}'
```

This allows SLM to track the new role for health checking, code sync, and update policies.

---

## Step 4: Run Scoped Provisioning

Run provisioning for the new role only on the target node. This runs all 6 phases for the new role but leaves existing roles untouched.

```bash
cd autobot-slm-backend/ansible

# Provision new role on existing node
ansible-playbook playbooks/provision-fleet-roles.yml \
  -i inventory/slm-nodes.yml \
  --limit 04-Database \
  --tags monitoring
```

Phases that run:
1. **CLEAN** — remove any stale dirs for the new role
2. **DEPLOY** — rsync new role code
3. **SYSTEM DEPS** — install `prometheus`, `grafana` (if not already present)
4. **SECRETS** — render `/etc/autobot/autobot-monitoring.env` (640)
5. **SERVICES** — install + enable `autobot-monitoring.service` units
6. **VERIFY** — poll health endpoint, report to SLM

---

## Step 5: Issue TLS Certificate for New Role

If the new role uses TLS:

```bash
ansible-playbook playbooks/setup-internal-ca.yml \
  -i inventory/slm-nodes.yml \
  --limit 04-Database
```

---

## Step 6: Update Firewall Rules

Add required UFW rules for the new role's ports and its `depends_on` relationships:

```bash
ansible-playbook playbooks/provision-fleet-roles.yml \
  -i inventory/slm-nodes.yml \
  --limit 04-Database \
  --tags firewall
```

---

## Step 7: Verify

```bash
# Check new role service is running
ssh autobot@172.16.168.23 "systemctl status autobot-monitoring"

# Check health endpoint
curl -sk https://172.16.168.23/metrics    # Prometheus example

# Check SLM shows the new role
curl -sk https://172.16.168.19/api/nodes/04-Database \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  | jq '.roles'
```

---

## Removing a Role From a Node

To remove a role without decommissioning the node:

```bash
# 1. Stop the service
ansible 04-Database -i inventory/slm-nodes.yml -m shell \
  -a "systemctl disable --now autobot-monitoring" \
  --become

# 2. Remove code directory
ansible 04-Database -i inventory/slm-nodes.yml -m file \
  -a "path=/opt/autobot/autobot-monitoring state=absent" \
  --become

# 3. Remove from inventory
# Edit inventory/slm-nodes.yml: remove 'autobot-monitoring' from node_roles

# 4. Update SLM DB
curl -sk -X DELETE https://172.16.168.19/api/nodes/04-Database/roles/autobot-monitoring \
  -H "Authorization: Bearer ${SLM_TOKEN}"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| SLM blocks assignment | Port conflict detected | Check coexistence matrix, choose different node |
| Phase 3 fails | Conflicting package version | Check existing packages: `dpkg -l | grep <package>` |
| Service fails to start | Port already in use | `ss -tlnp | grep <port>` to find conflict |
| Node shows two conflicting services | Manual assignment bypassed SLM | Stop one service, update inventory, re-provision |
| Health endpoint unreachable | UFW blocking | Check `ufw status`, re-run `--tags firewall` |

---

## Related

- `docs/architecture/COEXISTENCE_MATRIX.md` — coexistence rules
- `docs/architecture/ROLE_ARCHITECTURE.md` — node assignments
- `provision-fleet-roles.yml` — role provisioning playbook
- `docs/runbooks/DEPLOY_NEW_NODE.md` — adding a brand-new node
