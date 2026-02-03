# SSH Security Hardening Scripts
**CVE-AUTOBOT-2025-001 Remediation Toolkit**

## Overview

This directory contains scripts to fix the critical SSH man-in-the-middle vulnerability (CVE-AUTOBOT-2025-001) affecting the AutoBot distributed infrastructure. These scripts implement proper SSH host key verification across all 6 AutoBot hosts (172.16.168.20-25).

## Vulnerability Summary

**CRITICAL**: All SSH connections in AutoBot use `-o StrictHostKeyChecking=no` which completely disables host key verification, making the entire infrastructure vulnerable to man-in-the-middle attacks.

**Impact**: Attackers can intercept SSH connections, steal credentials, inject malicious AI models, compromise multi-modal data, and gain complete infrastructure control.

## Quick Start (Complete Remediation)

```bash
# 1. Configure SSH with proper host key verification
./configure-ssh.sh

# 2. Populate known_hosts with AutoBot VM host keys
./populate-known-hosts.sh

# 3. Fix all vulnerable scripts (preview first)
./fix-all-scripts.sh --dry-run

# 4. Apply fixes
./fix-all-scripts.sh

# 5. Verify security
./verify-ssh-security.sh
```

## Script Reference

### 1. configure-ssh.sh
**Purpose**: Creates secure SSH client configuration

**What it does**:
- Detects SSH version (for accept-new vs yes mode)
- Creates `~/.ssh/config` with proper host key checking
- Configures all 6 AutoBot hosts with secure settings
- Enables MITM attack detection

**Usage**:
```bash
./configure-ssh.sh
```

**Output**:
- `~/.ssh/config` - Secure SSH configuration
- Backup of existing config if present

**SSH Config Features**:
- `StrictHostKeyChecking accept-new` (SSH 7.6+) or `yes` (older)
- `UserKnownHostsFile ~/.ssh/known_hosts` (proper storage)
- Key-based authentication only
- Connection optimization

### 2. populate-known-hosts.sh
**Purpose**: Securely populates known_hosts with AutoBot VM host keys

**What it does**:
- Tests connectivity to all 6 AutoBot hosts
- Fetches host keys using `ssh-keyscan` (secure method)
- Displays host key fingerprints for verification
- Adds keys to `~/.ssh/known_hosts`
- Creates backup of existing known_hosts

**Usage**:
```bash
./populate-known-hosts.sh
```

**Output**:
- Updated `~/.ssh/known_hosts` with all AutoBot host keys
- Backup of existing known_hosts if present
- Host key fingerprints for manual verification

**Hosts Populated**:
- 172.16.168.20 - WSL Host (Backend)
- 172.16.168.21 - Frontend VM
- 172.16.168.22 - NPU Worker VM
- 172.16.168.23 - Redis/Database VM
- 172.16.168.24 - AI Stack VM
- 172.16.168.25 - Browser VM

### 3. fix-all-scripts.sh
**Purpose**: Automatically removes vulnerable SSH options from all scripts

**What it does**:
- Scans entire AutoBot codebase for vulnerable SSH usage
- Removes `-o StrictHostKeyChecking=no` from all SSH/SCP commands
- Removes `-o UserKnownHostsFile=/dev/null` options
- Fixes Ansible configurations
- Backs up all modified files
- Generates remediation report

**Usage**:
```bash
# Preview changes (recommended first)
./fix-all-scripts.sh --dry-run

# Apply fixes
./fix-all-scripts.sh
```

**Options**:
- `--dry-run` - Show what would be changed without modifying files
- `--help` - Show usage information

**Files Fixed**:
- 50+ shell scripts in `scripts/` directory
- Python modules with subprocess SSH calls
- Ansible configuration files
- Main system scripts (run_autobot.sh, etc.)

**Output**:
- Backup directory: `backups/ssh-remediation-<timestamp>/`
- Remediation report: `reports/security/ssh-remediation-report-<timestamp>.md`

### 4. verify-ssh-security.sh
**Purpose**: Validates SSH security configuration and host key verification

**What it does**:
- Verifies SSH config exists and is secure
- Checks known_hosts is populated
- Tests SSH connections to all 6 VMs with host key verification
- Scans for remaining vulnerable scripts
- Displays host key fingerprints
- Reports comprehensive security status

**Usage**:
```bash
./verify-ssh-security.sh
```

**Tests Performed**:
1. SSH config existence and validity
2. No StrictHostKeyChecking=no in config
3. known_hosts populated with >= 6 hosts
4. SSH connections work with host key verification
5. No vulnerable scripts remain
6. Host key fingerprints display
7. MITM detection capability (manual test)

**Exit Codes**:
- 0: All tests passed (secure configuration)
- 1: Some tests failed (needs remediation)

## Step-by-Step Remediation Guide

### Phase 1: Initial Setup (5 minutes)

1. **Configure SSH**:
   ```bash
   cd /home/kali/Desktop/AutoBot/scripts/security/ssh-hardening
   ./configure-ssh.sh
   ```
   
   This creates `~/.ssh/config` with secure settings for all AutoBot hosts.

2. **Populate Host Keys**:
   ```bash
   ./populate-known-hosts.sh
   ```
   
   This safely adds all 6 AutoBot VM host keys to `~/.ssh/known_hosts`.

3. **Verify Configuration**:
   ```bash
   # Test SSH connection to Frontend VM
   ssh autobot@172.16.168.21 'echo "Connection OK"'
   
   # Or using hostname alias
   ssh autobot-frontend 'echo "Connection OK"'
   ```

### Phase 2: Script Remediation (10 minutes)

4. **Preview Script Fixes** (recommended):
   ```bash
   ./fix-all-scripts.sh --dry-run
   ```
   
   Review what will be changed. This is non-destructive.

5. **Apply Script Fixes**:
   ```bash
   ./fix-all-scripts.sh
   ```
   
   This will:
   - Backup all files to `backups/ssh-remediation-<timestamp>/`
   - Remove vulnerable SSH options from 50+ scripts
   - Fix Ansible configurations
   - Generate remediation report

6. **Review Remediation Report**:
   ```bash
   cat ~/Desktop/AutoBot/reports/security/ssh-remediation-report-*.md
   ```

### Phase 3: Testing & Validation (10 minutes)

7. **Run Security Verification**:
   ```bash
   ./verify-ssh-security.sh
   ```
   
   This runs comprehensive security tests. All tests should pass.

8. **Test Critical Operations**:
   ```bash
   # Test sync script
   cd /home/kali/Desktop/AutoBot
   ./scripts/utilities/sync-to-vm.sh --test-connection all
   
   # Test frontend sync
   ./scripts/utilities/sync-frontend.sh README.md
   
   # Test Ansible
   ansible -i ansible/inventory/production.yml autobot-frontend -m ping
   ```

9. **Full System Test**:
   ```bash
   # Start AutoBot with new SSH security
   bash run_autobot.sh --dev
   ```

### Phase 4: MITM Detection Verification (Optional)

10. **Test MITM Detection** (manual verification):
    ```bash
    # Backup known_hosts
    cp ~/.ssh/known_hosts ~/.ssh/known_hosts.backup
    
    # Remove one host's key
    ssh-keygen -R 172.16.168.21
    
    # Add fake key (simulates MITM attack)
    echo "172.16.168.21 ssh-rsa AAAAB3NzaC1yc2FAKE_KEY" >> ~/.ssh/known_hosts
    
    # Try to connect - should FAIL (MITM detected)
    ssh autobot@172.16.168.21 'echo "Should fail"'
    # Expected: Host key verification failed
    
    # Restore backup
    mv ~/.ssh/known_hosts.backup ~/.ssh/known_hosts
    ```

## Rollback Procedure

If issues occur after remediation:

```bash
# Find your backup directory
ls -lt ~/Desktop/AutoBot/backups/ | head -5

# Restore all files from backup
BACKUP_DIR="~/Desktop/AutoBot/backups/ssh-remediation-<timestamp>"
cp -r $BACKUP_DIR/* ~/Desktop/AutoBot/

# Restore SSH configuration
cp ~/.ssh/config.backup-<timestamp> ~/.ssh/config
cp ~/.ssh/known_hosts.backup-<timestamp> ~/.ssh/known_hosts
```

## Security Best Practices

### DO ✅
- Use SSH config for centralized configuration
- Verify host key fingerprints on first connection
- Use `StrictHostKeyChecking accept-new` (SSH 7.6+)
- Keep known_hosts file properly maintained
- Use key-based authentication only
- Monitor for unexpected host key changes

### DON'T ❌
- Never use `-o StrictHostKeyChecking=no`
- Never use `-o UserKnownHostsFile=/dev/null`
- Never disable host key verification
- Never ignore host key change warnings
- Never use password authentication for automation

## Troubleshooting

### Issue: SSH connection fails after remediation

**Symptom**: `Host key verification failed`

**Cause**: Host key not in known_hosts or has changed

**Solution**:
```bash
# Check if host key exists
ssh-keygen -F 172.16.168.21

# If missing, re-run population script
./populate-known-hosts.sh

# If changed (legitimate change), remove old key and re-add
ssh-keygen -R 172.16.168.21
./populate-known-hosts.sh
```

### Issue: Scripts still fail with "Host key verification failed"

**Symptom**: Sync scripts fail after remediation

**Cause**: Scripts may have hardcoded SSH options

**Solution**:
```bash
# Search for remaining vulnerable usage
grep -rn "StrictHostKeyChecking=no" ~/Desktop/AutoBot/scripts/

# Fix manually or re-run
./fix-all-scripts.sh
```

### Issue: Ansible playbooks fail

**Symptom**: `UNREACHABLE! => {"changed": false, "msg": "Failed to connect"}`

**Cause**: Ansible SSH configuration not updated

**Solution**:
```bash
# Verify Ansible config
grep -n "UserKnownHostsFile" ~/Desktop/AutoBot/ansible/ansible.cfg

# Should NOT contain /dev/null
# Re-run fix script if needed
./fix-all-scripts.sh
```

## File Reference

```
scripts/security/ssh-hardening/
├── README.md                    # This file
├── configure-ssh.sh            # Creates secure SSH config
├── populate-known-hosts.sh     # Populates known_hosts
├── fix-all-scripts.sh          # Fixes vulnerable scripts
└── verify-ssh-security.sh      # Security validation tests
```

## Related Documentation

- **Security Audit Report**: `/home/kali/Desktop/AutoBot/reports/security/CVE-AUTOBOT-2025-001-SSH-MITM-VULNERABILITY.md`
- **AutoBot Documentation**: `/home/kali/Desktop/AutoBot/docs/`
- **Development Guidelines**: `/home/kali/Desktop/AutoBot/CLAUDE.md`

## Support

For issues or questions:
1. Review the security audit report for detailed vulnerability information
2. Check AutoBot documentation in `docs/` directory
3. Review remediation logs in `reports/security/`
4. Restore from backups if critical issues occur

## References

- [CWE-322: Key Exchange without Entity Authentication](https://cwe.mitre.org/data/definitions/322.html)
- [SSH Best Practices - NIST SP 800-77](https://csrc.nist.gov/publications/detail/sp/800-77/rev-1/final)
- [OpenSSH Manual - ssh_config](https://man.openbsd.org/ssh_config)
- [OWASP: Insufficient Transport Layer Protection](https://owasp.org/www-project-top-ten/)

---

**Classification**: INTERNAL USE - SECURITY SENSITIVE  
**Last Updated**: 2025-10-04  
**CVE Reference**: CVE-AUTOBOT-2025-001
