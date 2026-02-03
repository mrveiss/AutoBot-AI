# 🚨 MANDATORY LOCAL-ONLY EDITING POLICY

## ⛔ ABSOLUTE PROHIBITION

**NEVER:**
- SSH into remote machines to edit files
- Use remote editors (vim/nano/emacs) on VMs
- Modify configs directly on servers
- Execute `ssh user@host "edit command"`
- Modify Docker containers on remote machines

## ✅ REQUIRED WORKFLOW

```
LOCAL EDIT → TEST → SYNC → DEPLOY → VERIFY
     ↓         ↓      ↓       ↓        ↓
  /home/kali  local  rsync  restart  health
  /Desktop/   tests  or     service  check
  AutoBot/           ansible
```

## 🖥️ VM Infrastructure

| VM | IP | Purpose |
|----|-----|---------|
| VM1 | 172.16.168.21 | Frontend |
| VM2 | 172.16.168.22 | NPU Worker |
| VM3 | 172.16.168.23 | Redis |
| VM4 | 172.16.168.24 | AI Stack |
| VM5 | 172.16.168.25 | Browser |

**Local Base:** `/home/kali/Desktop/AutoBot/` — ALL edits here. NO EXCEPTIONS.

## 🔄 Approved Sync Methods

### 1. Rsync (Preferred)
```bash
rsync -avz --delete \
  -e "ssh -i ~/.ssh/autobot_key" \
  /home/kali/Desktop/AutoBot/backend/ \
  autobot@172.16.168.21:/opt/autobot/backend/
```

### 2. Sync Script
```bash
./scripts/utilities/sync-to-vm.sh frontend 172.16.168.21
```

### 3. Ansible
```bash
ansible-playbook -i inventory/production playbooks/deploy-frontend.yml
```

## ⚠️ Violations vs Correct

### ❌ WRONG
```bash
ssh autobot@172.16.168.21 "vim /opt/autobot/config.yaml"
ssh autobot@172.16.168.23 "redis-cli CONFIG SET maxmemory 2gb"
```

### ✅ CORRECT
```bash
# Edit locally
vim /home/kali/Desktop/AutoBot/config.yaml

# Sync to remote
rsync -avz config.yaml autobot@172.16.168.21:/opt/autobot/

# Or use Ansible for config changes
ansible-playbook playbooks/update-redis-config.yml
```

## 📋 Pre-Remote Checklist

- [ ] Edit made in `/home/kali/Desktop/AutoBot/`?
- [ ] Local change tested?
- [ ] Sync script/playbook ready?
- [ ] SSH keys configured?
- [ ] Dry run performed?
- [ ] Rollback plan exists?

## 🔒 SSH Requirements

- **Key:** `~/.ssh/autobot_key` (4096-bit RSA)
- **Permissions:** 600
- **Auth:** Key-based only (NO passwords)

## 📢 Why This Matters

Violations create:
1. Configuration drift between environments
2. Loss of version control tracking
3. Deployment inconsistencies
4. Security vulnerabilities
5. Debugging nightmares

**Source of truth = LOCAL. Remote = deployment target only.**

---
**Enforcement:** MANDATORY | **Exceptions:** NONE
