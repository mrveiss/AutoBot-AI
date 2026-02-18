# Runbook: Rotate TLS Certificates

**Issue #926 Phase 7** | Last updated: 2026-02-18

---

## Overview

This runbook describes how to rotate TLS certificates across the AutoBot fleet using the
`rotate-certs.yml` Ansible playbook. The rotation is zero-downtime for nginx nodes (graceful
reload) and causes a brief service restart on uvicorn-based nodes.

---

## Prerequisites

- Ansible control node has SSH access to all fleet VMs
- `autobot-slm-backend/ansible/` is the working directory
- Ansible inventory: `inventory/slm-nodes.yml`
- SLM server (.19) is reachable

---

## Quick Reference

```bash
# Check current cert expiry across entire fleet
cd autobot-slm-backend/ansible
ansible-playbook playbooks/rotate-certs.yml --tags check

# Rotate certs on all nodes
ansible-playbook playbooks/rotate-certs.yml -i inventory/slm-nodes.yml

# Rotate a single node only
ansible-playbook playbooks/rotate-certs.yml -i inventory/slm-nodes.yml --limit 02-Frontend
```

---

## Step-by-Step Procedure

### 1. Pre-flight: Check Current Expiry

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/rotate-certs.yml --tags check
```

This runs `openssl x509 -noout -enddate` on each node and shows the expiry date.
**No changes are made in check-only mode.**

### 2. Review the Rotation Plan

`rotate-certs.yml` rotates certificates in three sequential phases:
- **Phase 1** — SLM Server (.19): nginx + uvicorn restart
- **Phase 2** — Backend (.20, WSL): uvicorn restart only (no nginx)
- **Phase 3** — Frontend (.21): nginx graceful reload only

### 3. Execute Rotation

```bash
ansible-playbook playbooks/rotate-certs.yml -i inventory/slm-nodes.yml
```

Expected output per node:
- Old cert backed up as `server-cert.pem.bak`
- New self-signed cert generated (`openssl req -x509`)
- Nginx reloaded **or** uvicorn restarted
- New cert fingerprint displayed

### 4. Verify Rotation Succeeded

```bash
# Re-check expiry — should now show ~365 days
ansible-playbook playbooks/rotate-certs.yml --tags check

# Verify HTTPS connectivity
curl --insecure -v https://172.16.168.19/ 2>&1 | grep "expire date"
curl --insecure -v https://172.16.168.21/ 2>&1 | grep "expire date"
ssh autobot@172.16.168.19 "curl --insecure -v https://172.16.168.20:8443/api/health 2>&1 | grep 'expire date'"
```

### 5. Update SLM Cert Records (optional)

After rotation, run `setup-internal-ca.yml` with `--tags force` to regenerate CA-signed certs
AND update the SLM dashboard cert records:

```bash
ansible-playbook playbooks/setup-internal-ca.yml -i inventory/slm-nodes.yml --tags force
```

---

## Upgrading from Self-Signed to CA-Signed Certs

If you want to move from per-node self-signed certs to CA-signed certs (recommended for
production), use `setup-internal-ca.yml` instead:

```bash
ansible-playbook playbooks/setup-internal-ca.yml -i inventory/slm-nodes.yml
```

This:
1. Generates a CA key + root cert on SLM (.19) — `/etc/autobot/ca/`
2. Issues CA-signed node certs for all fleet nodes
3. Distributes the CA cert to `/etc/autobot/certs/ca-cert.pem` on all nodes
4. Adds CA cert to system trust store (`/usr/local/share/ca-certificates/`)
5. Reports cert metadata to SLM API (visible in Security > TLS Certificates)

---

## Rollback Procedure

If the new cert causes issues, restore the backup:

```bash
# On a specific node (example: SLM server)
ssh autobot@172.16.168.19 "sudo cp /etc/autobot/certs/server-cert.pem.bak /etc/autobot/certs/server-cert.pem && sudo systemctl reload nginx"
```

Or via Ansible:
```bash
ansible 00-SLM-Manager -i inventory/slm-nodes.yml -m shell \
  -a "cp /etc/autobot/certs/server-cert.pem.bak /etc/autobot/certs/server-cert.pem && systemctl reload nginx" \
  --become
```

---

## Automation: Pre-emptive Renewal

Set up a cron job on the Ansible control node to check and rotate certs before expiry:

```bash
# Check monthly; rotate if any cert expires within 30 days
0 2 1 * * cd /path/to/AutoBot/autobot-slm-backend/ansible && \
  ansible-playbook playbooks/rotate-certs.yml --tags check 2>&1 | \
  grep -q "Expiring\|expired" && \
  ansible-playbook playbooks/rotate-certs.yml
```

The SLM dashboard Security > TLS Certificates page shows days-until-expiry for all nodes.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| nginx -t fails after rotation | New cert has wrong path | Check `/etc/autobot/certs/server-cert.pem` exists |
| Backend won't start after restart | asyncpg SSL key permissions | `chmod 600 /etc/autobot/certs/server-key.pem` |
| `SSL: CERTIFICATE_VERIFY_FAILED` | Self-signed cert, client validates | Use `--insecure` in curl or distribute CA cert |
| Phase 2 (Backend) takes >2 min | Backend has long startup time | Normal — it loads GPUSemanticChunker + ChromaDB |
| Cert shows wrong CN | `_cert_subject` variable wrong | Check `vars.yml` or group_vars for node |

---

## Related

- `rotate-ssh-keys.yml` — rotate SSH keys across the fleet
- `setup-internal-ca.yml` — generate CA and issue CA-signed certs
- `docs/runbooks/EMERGENCY_RECOVERY.md` — break-glass access procedures
- SLM Dashboard: Security > TLS Certificates
