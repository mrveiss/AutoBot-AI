# Runbook: Deploy a New Fleet Node

**Issue #926 Phase 8** | Last updated: 2026-02-18

---

## Overview

This runbook describes how to bring a new Ubuntu 22.04 VM into the AutoBot fleet and assign it one or more roles. The process covers: SSH access setup, inventory registration, SLM fleet registration, and Ansible provisioning.

---

## Prerequisites

- Ubuntu 22.04 VM with network access to `172.16.168.0/24`
- VM is reachable from dev machine via SSH (password or initial key)
- `autobot-slm-backend/ansible/` is the working directory
- SLM server (`.19`) is running and healthy

---

## Step 1: Assign IP Address

Pick the next available IP from the fleet subnet. Currently assigned:

| IP | Role |
|----|------|
| `172.16.168.19` | SLM Server |
| `172.16.168.20` | Backend |
| `172.16.168.21` | Frontend |
| `172.16.168.22` | NPU |
| `172.16.168.23` | Database |
| `172.16.168.24` | AI Stack |
| `172.16.168.25` | Browser |
| `172.16.168.26` | Reserved |
| `172.16.168.27` | Reserved |

Configure static IP on the new VM (via `/etc/netplan/` or your hypervisor's DHCP reservation).

---

## Step 2: Create `autobot` User + Deploy SSH Key

```bash
# From dev machine, SSH in with password or initial key
ssh root@<new-vm-ip>

# Create autobot user
adduser --disabled-password --gecos "" autobot
usermod -aG sudo autobot
echo "autobot ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/autobot
chmod 440 /etc/sudoers.d/autobot

# Deploy SSH key
mkdir -p /home/autobot/.ssh
chmod 700 /home/autobot/.ssh
cat ~/.ssh/autobot_ed25519.pub >> /home/autobot/.ssh/authorized_keys
chmod 600 /home/autobot/.ssh/authorized_keys
chown -R autobot:autobot /home/autobot/.ssh
```

Verify SSH access:

```bash
ssh -i ~/.ssh/autobot_ed25519 autobot@<new-vm-ip> "echo ok"
```

---

## Step 3: Add to Ansible Inventory

Edit `autobot-slm-backend/ansible/inventory/slm-nodes.yml`:

```yaml
all:
  children:
    slm_nodes:
      hosts:
        # ... existing nodes ...
        08-NewRole:                           # Choose a node ID (00-07 used)
          ansible_host: 172.16.168.XX
          ansible_user: autobot
          ansible_ssh_private_key_file: ~/.ssh/autobot_ed25519
          node_roles:
            - autobot-<role>
            - autobot-slm-agent
```

Verify Ansible can reach the new node:

```bash
cd autobot-slm-backend/ansible
ansible 08-NewRole -i inventory/slm-nodes.yml -m ping
```

---

## Step 4: Register Node in SLM

Add the node to the SLM database. Either via SLM API or seed script:

```bash
# Via API
curl -sk -X POST https://172.16.168.19/api/nodes \
  -H "Authorization: Bearer ${SLM_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "08-NewRole",
    "hostname": "new-vm-hostname",
    "ip_address": "172.16.168.XX",
    "role": "autobot-<role>",
    "os": "ubuntu-22.04"
  }'
```

Or add to `autobot-slm-backend/ansible/playbooks/seed-fleet-nodes.yml` and re-run:

```bash
ansible-playbook playbooks/seed-fleet-nodes.yml -i inventory/slm-nodes.yml
```

---

## Step 5: Run Role Provisioning

```bash
cd autobot-slm-backend/ansible

# Provision the new node only (runs all 6 phases)
ansible-playbook playbooks/provision-fleet-roles.yml \
  -i inventory/slm-nodes.yml \
  --limit 08-NewRole
```

Expected output: 6 phases complete, node status = `UP_TO_DATE`.

---

## Step 6: Issue TLS Certificate

```bash
ansible-playbook playbooks/setup-internal-ca.yml \
  -i inventory/slm-nodes.yml \
  --limit 08-NewRole
```

This generates a CA-signed cert and reports it to SLM's `security/certificates` endpoint.

---

## Step 7: Verify

```bash
# Check node appears in SLM dashboard
curl -sk https://172.16.168.19/api/nodes | jq '.[] | select(.node_id=="08-NewRole")'

# Test role health endpoint
curl -sk https://172.16.168.XX:<port>/health

# Test Ansible connectivity
ansible 08-NewRole -i inventory/slm-nodes.yml -m ping

# Check SLM agent is running
ssh autobot@172.16.168.XX "systemctl status autobot-slm-agent"
```

---

## Step 8: Configure Firewall Rules

```bash
# Apply UFW rules for this node (generated from manifest depends_on)
ansible-playbook playbooks/provision-fleet-roles.yml \
  -i inventory/slm-nodes.yml \
  --limit 08-NewRole \
  --tags firewall
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `Permission denied (publickey)` | SSH key not deployed | Re-run Step 2 |
| `UNREACHABLE` in Ansible | Wrong IP or SSH port | Check inventory IP, test `ssh autobot@IP` |
| Phase 3 fails (apt) | Node has no internet | Run apt-get with proxy, or pre-cache packages |
| Node stays OUTDATED | SLM notify not triggered | Run `POST /api/code-source/notify` manually |
| TLS cert issuing fails | CA key not on .19 | Run `setup-internal-ca.yml --tags ca` on .19 first |
| Service fails to start | Missing .env file | Re-run `provision-fleet-roles.yml --tags secrets` |

---

## Related

- `provision-fleet-roles.yml` — full 6-phase provisioning
- `setup-internal-ca.yml` — TLS cert issuance
- `docs/runbooks/ASSIGN_ROLE.md` — adding a role to an existing node
- `docs/architecture/ROLE_ARCHITECTURE.md` — role definitions
