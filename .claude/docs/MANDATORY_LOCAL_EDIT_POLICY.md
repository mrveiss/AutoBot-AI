# 🚨 MANDATORY LOCAL-ONLY EDITING POLICY

## ⛔ ABSOLUTE PROHIBITION

**NEVER:**
- SSH into remote machines to edit files
- Use remote editors (vim/nano/emacs) on deployment machines
- Modify configs directly on servers
- Execute `ssh user@host "edit command"`
- Modify Docker containers on remote machines

## ✅ REQUIRED WORKFLOW

```
LOCAL EDIT → TEST → SYNC → DEPLOY → VERIFY
     ↓         ↓      ↓       ↓        ↓
  $HOME  local  rsync  restart  health
  /Desktop/   tests  or     service  check
  AutoBot/           ansible
```

## 🖥️ Deployment Roles

AutoBot has no fixed machine count: it runs in Docker, on one VM, or scaled out across
however many machines an operator chooses. Each role below can be co-located or split
onto its own machine; hosts are resolved via `infrastructure.hosts.<role>`, never hardcoded.

| Role | Purpose |
|----|---------|
| Frontend | Web UI (nginx / Vue.js) |
| NPU Worker | Hardware AI acceleration |
| Database | Redis |
| AI Stack | LLM serving |
| Browser | Playwright / VNC |

**Local Base:** `` — ALL edits here. NO EXCEPTIONS.

## 🔄 Approved Sync Methods

### 1. Rsync (Preferred)
```bash
rsync -avz --delete \
  -e "ssh -i ~/.ssh/autobot_key" \
  backend/ \
  autobot@<backend-host>:/opt/autobot/backend/
```

### 2. Sync Script
```bash
./scripts/utilities/sync-to-vm.sh frontend <frontend-host>
```

### 3. Ansible
```bash
ansible-playbook -i inventory/production playbooks/deploy-frontend.yml
```

## ⚠️ Violations vs Correct

### ❌ WRONG
```bash
ssh autobot@<frontend-host> "vim /opt/autobot/config.yaml"
ssh autobot@<database-host> "redis-cli CONFIG SET maxmemory 2gb"
```

### ✅ CORRECT
```bash
# Edit locally
vim config.yaml

# Sync to remote
rsync -avz config.yaml autobot@<frontend-host>:/opt/autobot/

# Or use Ansible for config changes
ansible-playbook playbooks/update-redis-config.yml
```

## 📋 Pre-Remote Checklist

- [ ] Edit made in `/opt/autobot`?
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
