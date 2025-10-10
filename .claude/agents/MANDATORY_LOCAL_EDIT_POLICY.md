# 🚨 MANDATORY LOCAL-ONLY EDITING POLICY - CRITICAL ENFORCEMENT

## ⛔ ABSOLUTE PROHIBITION: NO REMOTE EDITING

**UNDER NO CIRCUMSTANCES ARE AGENTS ALLOWED TO:**
- ❌ SSH into remote machines to edit files directly
- ❌ Use remote text editors (vim, nano, emacs) on VMs
- ❌ Modify configuration files directly on servers
- ❌ Execute code changes directly on remote hosts
- ❌ Use `ssh user@host "edit command"` patterns
- ❌ Modify Docker containers directly on remote machines

## ✅ MANDATORY WORKFLOW: LOCAL EDIT → SYNC → DEPLOY

### The ONLY Acceptable Workflow:

```
[Code example removed for token optimization (mermaid)]
```

## 📍 VM Infrastructure and Sync Requirements

### Remote VM Addresses:
- **VM1 Frontend**: `172.16.168.21` - Web interface
- **VM2 NPU Worker**: `172.16.168.22` - Hardware AI acceleration  
- **VM3 Redis**: `172.16.168.23` - Data layer
- **VM4 AI Stack**: `172.16.168.24` - AI processing
- **VM5 Browser**: `172.16.168.25` - Web automation

### Local Development Base:
- **Primary**: `/home/kali/Desktop/AutoBot/` - ALL edits happen here
- **NO EXCEPTIONS**: Every single code change must originate locally

## 🔄 Approved Sync Methods

### 1. SSH Key-Based Sync Scripts (Preferred)

```
[Code example removed for token optimization (bash)]
```

### 2. Ansible Playbooks (Infrastructure Changes)

```
[Code example removed for token optimization (bash)]
```

### 3. Rsync with SSH Keys

```
[Code example removed for token optimization (bash)]
```

### 4. Docker Build and Push (Container Updates)

```
[Code example removed for token optimization (bash)]
```

## 🛠️ Agent-Specific Enforcement Rules

### Frontend Engineer
```
[Code example removed for token optimization (markdown)]
```

### Backend Engineer
```
[Code example removed for token optimization (markdown)]
```

### DevOps Engineer
```
[Code example removed for token optimization (markdown)]
```

### Database Engineer
```
[Code example removed for token optimization (markdown)]
```

## 📝 Sync Script Templates

### Universal Sync Function
```
[Code example removed for token optimization (bash)]
```

### Service-Specific Sync Scripts

#### Frontend Sync
```
[Code example removed for token optimization (bash)]
```

#### Backend Sync
```
[Code example removed for token optimization (bash)]
```

## 🚀 Ansible Playbook Examples

### Deploy Frontend Changes
```
[Code example removed for token optimization (yaml)]
```

### Sync All VMs
```
[Code example removed for token optimization (yaml)]
```

## 🔍 Verification Commands

### Check What Will Be Synced (Dry Run)
```
[Code example removed for token optimization (bash)]
```

### Verify Remote State
```
[Code example removed for token optimization (bash)]
```

## ⚠️ Common Violations and Corrections

### ❌ VIOLATION: Direct SSH Editing
```
[Code example removed for token optimization (bash)]
```

### ✅ CORRECT: Local Edit + Sync
```
[Code example removed for token optimization (bash)]
```

### ❌ VIOLATION: Remote Configuration Change
```
[Code example removed for token optimization (bash)]
```

### ✅ CORRECT: Local Config + Ansible Deploy
```
[Code example removed for token optimization (bash)]
```

## 📋 Agent Checklist

Before ANY remote operation, agents MUST verify:

- [ ] Is the edit being made in `/home/kali/Desktop/AutoBot/`?
- [ ] Has the local change been tested?
- [ ] Is the sync script or Ansible playbook ready?
- [ ] Are SSH keys properly configured?
- [ ] Is the target VM and path correct?
- [ ] Has a dry run been performed?
- [ ] Is there a rollback plan?

## 🔒 Security Enforcement

### SSH Key Requirements
- **Location**: `~/.ssh/autobot_key` (4096-bit RSA)
- **Permissions**: 600 (read/write owner only)
- **NO PASSWORD AUTH**: Only key-based authentication allowed

### Sync Script Security
- **Always use SSH keys**: Never embed passwords
- **Verify paths**: Prevent accidental overwrites
- **Use --delete carefully**: Can remove remote files
- **Log all syncs**: Maintain audit trail

## 📢 FINAL ENFORCEMENT STATEMENT

**This policy is NON-NEGOTIABLE. Any agent attempting to edit files directly on remote servers is violating core architectural principles and creating:**

1. **Configuration drift** between environments
2. **Loss of version control** tracking
3. **Deployment inconsistencies**
4. **Security vulnerabilities**
5. **Debugging nightmares**

**REMEMBER**: The source of truth is ALWAYS local. Remote machines are deployment targets, not development environments.

---

**Policy Effective Date**: 2025-01-12  
**Enforcement Level**: MANDATORY  
**Exceptions**: NONE  
**Violations**: Will be logged and corrected immediately