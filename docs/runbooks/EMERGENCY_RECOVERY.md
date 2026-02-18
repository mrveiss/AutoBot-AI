# Runbook: Emergency Recovery (Break-Glass)

**Issue #926 Phase 7** | Last updated: 2026-02-18

---

## Overview

This runbook describes break-glass procedures for recovering access to the AutoBot fleet when
normal access methods (SSH keys, SLM UI, Ansible) have failed. These procedures are for
emergencies only and must be documented when used.

---

## Recovery Scenarios

| Scenario | Section |
|----------|---------|
| All SSH keys revoked | [SSH Key Recovery](#ssh-key-recovery) |
| SLM backend unreachable | [SLM Recovery](#slm-recovery) |
| Fleet node unreachable | [Node Recovery](#node-recovery) |
| All TLS certs expired | [Cert Recovery](#cert-recovery) |
| Admin password lost | [Admin Password Recovery](#admin-password-recovery) |

---

## SSH Key Recovery

### Scenario: All SSH keys locked out

If `autobot_ed25519` and `autobot_admin_temp_ed25519` both fail, you need console access.

**Step 1: Verify the failure scope**

```bash
# Test each key explicitly
ssh -i ~/.ssh/autobot_ed25519 -o BatchMode=yes autobot@172.16.168.19 "echo ok" 2>&1
ssh -i ~/.ssh/autobot_admin_temp_ed25519 -o BatchMode=yes autobot@172.16.168.19 "echo ok" 2>&1
```

**Step 2: Use VM console (Hyper-V / VMware / KVM)**

Access the VM hypervisor console. Log in with the OS admin credentials stored in the
break-glass key store (see [Break-Glass Key Store](#break-glass-key-store) below).

**Step 3: Restore SSH access**

```bash
# On the VM console, add a new temporary key
echo "ssh-ed25519 AAAA... recovery-key" >> /home/autobot/.ssh/authorized_keys
chmod 600 /home/autobot/.ssh/authorized_keys
```

**Step 4: Re-run Ansible to restore proper state**

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/ensure-ssh-access.yml -i inventory/slm-nodes.yml
```

**Step 5: Rotate all keys (schedule within 24 hours)**

```bash
ansible-playbook playbooks/rotate-ssh-keys.yml -i inventory/slm-nodes.yml
```

---

## SLM Recovery

### Scenario: SLM server unreachable (172.16.168.19)

**Step 1: Check SLM service status via SSH**

```bash
ssh autobot@172.16.168.19 "sudo systemctl status autobot-slm-backend"
```

**Step 2: Check logs**

```bash
ssh autobot@172.16.168.19 "sudo journalctl -u autobot-slm-backend -n 100 --no-pager"
```

**Step 3: Restart SLM services**

```bash
ssh autobot@172.16.168.19 "sudo systemctl restart autobot-slm-backend nginx"
```

**Step 4: If DB is corrupt, recover from backup**

```bash
ssh autobot@172.16.168.19 "sudo systemctl stop autobot-slm-backend"
ssh autobot@172.16.168.19 "sudo -u postgres pg_restore -d autobot_slm /opt/autobot/data/backups/latest.dump"
ssh autobot@172.16.168.19 "sudo systemctl start autobot-slm-backend"
```

**Step 5: If full redeploy needed**

```bash
# From dev machine:
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-slm-manager.yml -i inventory/slm-nodes.yml --limit 00-SLM-Manager
```

---

## Node Recovery

### Scenario: Fleet node unreachable

**Step 1: Ping check**

```bash
ping -c 3 172.16.168.<node-ip>
```

**Step 2: Check if service is running (via another reachable node)**

```bash
# From SLM server
ssh autobot@172.16.168.19 "curl -sk https://172.16.168.<node-ip>:8443/api/health"
```

**Step 3: If node OS is up but service is down**

```bash
ssh autobot@172.16.168.<node-ip> "sudo systemctl restart autobot-<role>"
```

**Step 4: Reprovision the node**

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/provision-fleet-roles.yml -i inventory/slm-nodes.yml \
  --limit <node-hostname>
```

---

## Cert Recovery

### Scenario: All TLS certs expired — services rejecting connections

Self-signed or CA-signed certs that have expired will cause nginx and uvicorn to reject
connections. Since Ansible uses SSH (not TLS), cert expiry does NOT prevent Ansible access.

**Step 1: Re-run cert rotation**

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/rotate-certs.yml -i inventory/slm-nodes.yml
```

**Step 2: Or regenerate CA-signed certs**

```bash
ansible-playbook playbooks/setup-internal-ca.yml -i inventory/slm-nodes.yml --tags force
```

**Step 3: Verify**

```bash
ansible-playbook playbooks/rotate-certs.yml --tags check
```

---

## Admin Password Recovery

### Scenario: SLM admin password is unknown

The SLM backend sets the admin password from `/etc/autobot/slm-secrets.env` on startup.

**Step 1: Read current password from secrets file**

```bash
ssh autobot@172.16.168.19 "sudo cat /etc/autobot/slm-secrets.env | grep ADMIN_PASSWORD"
```

**Step 2: If file is missing, regenerate via Ansible**

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-slm-manager.yml --tags secrets -i inventory/slm-nodes.yml \
  --limit 00-SLM-Manager
```

**Step 3: Reset password directly in DB (last resort)**

```bash
ssh autobot@172.16.168.19
# Generate hash:
python3 -c "import bcrypt; print(bcrypt.hashpw(b'NEW_PASSWORD', bcrypt.gensalt()).decode())"
# Update DB:
sudo -u postgres psql autobot_slm -c "UPDATE users SET hashed_password='<hash>' WHERE username='admin';"
```

---

## Break-Glass Key Store

Critical secrets are split across three storage locations. All three parts are required to
reconstruct the break-glass credentials.

| Part | Location | Custodian |
|------|----------|-----------|
| Part A | SLM server: `/etc/autobot/keys/break-glass-a.enc` | SLM server |
| Part B | Encrypted in project secrets manager | Project owner |
| Part C | Physical backup (USB, safe) | Infrastructure team |

**To reconstruct:**

```bash
# Fetch Part A from SLM
ssh autobot@172.16.168.19 "sudo cat /etc/autobot/keys/break-glass-a.enc"

# Decrypt using Parts B and C (GPG)
gpg --decrypt break-glass.enc
```

**Changing break-glass credentials** must be done via the `setup-passwordless-sudo.yml`
playbook and the secrets manager update procedure. Document all changes in a time-stamped
access log.

---

## Post-Recovery Checklist

After any emergency recovery action, complete within 24 hours:

- [ ] Root cause identified and documented
- [ ] Affected services fully restored
- [ ] Break-glass access removed (temp keys revoked, temp passwords changed)
- [ ] Ansible state reconciled (`ansible-playbook deploy-full.yml`)
- [ ] GitHub issue created describing the incident
- [ ] SLM audit logs reviewed for unauthorized access during outage
- [ ] Certs and keys rotated if any were exposed
- [ ] Team notified if downtime exceeded SLO threshold

---

## Related

- `docs/runbooks/ROTATE_SSH_KEYS.md` — planned SSH key rotation
- `docs/runbooks/ROTATE_CERTS.md` — planned cert rotation
- `setup-passwordless-sudo.yml` — sudo access management
- `ensure-ssh-access.yml` — SSH access verification playbook
- `deploy-slm-manager.yml` — full SLM redeploy
