# Ansible Credential Security Guide

> **Issue Reference:** [#700](https://github.com/mrveiss/AutoBot-AI/issues/700) - Security: Migrate Ansible inventory credentials to Ansible Vault

## Overview

This guide documents the secure credential management strategy for AutoBot's Ansible infrastructure. We use a combination of **SSH key authentication** and **passwordless sudo** to eliminate plaintext credentials from inventory files.

## Authentication Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    AutoBot Authentication                        │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     SSH Key Auth     ┌──────────────────┐    │
│  │ Control Host │ ──────────────────── │ Target VMs       │    │
│  │ (WSL)        │   ~/.ssh/autobot_key │ (autobot user)   │    │
│  └──────────────┘                       └──────────────────┘    │
│                                                 │               │
│                                         Passwordless Sudo       │
│                                                 │               │
│                                         ┌──────────────────┐    │
│                                         │ Root Privileges  │    │
│                                         │ (via sudoers.d)  │    │
│                                         └──────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Quick Setup

### 1. Verify SSH Key Authentication

SSH key authentication should already be configured. Verify with:

```bash
# Test SSH connection to a VM
ssh -i ~/.ssh/autobot_key autobot@172.16.168.21

# Test Ansible connectivity
cd /home/kali/Desktop/AutoBot/ansible
ansible all -i inventory/production.yml -m ping
```

### 2. Configure Passwordless Sudo (Recommended)

Run the one-time setup to enable passwordless sudo on all VMs:

```bash
cd /home/kali/Desktop/AutoBot/ansible

# This will prompt for the become (sudo) password once
./deploy.sh --setup-sudo
```

After this, all future Ansible operations will work without password prompts.

### 3. Encrypt the Vault File (Optional)

For additional security, encrypt the vault file containing fallback credentials:

```bash
# Encrypt the vault file
ansible-vault encrypt inventory/group_vars/vault.yml

# You'll be prompted to create a vault password
```

## File Locations

| File | Purpose |
|------|---------|
| `~/.ssh/autobot_key` | SSH private key for authentication |
| `~/.ssh/config` | SSH client configuration (disables password auth) |
| `inventory/production.yml` | Main inventory (no plaintext passwords) |
| `inventory/group_vars/vault.yml` | Encrypted vault for fallback credentials |
| `playbooks/setup-passwordless-sudo.yml` | Playbook to configure sudoers |

## Configuration Details

### SSH Key Authentication

The SSH configuration in `~/.ssh/config` enforces key-based authentication:

```ssh-config
Host *
    IdentitiesOnly yes
    PubkeyAuthentication yes
    PasswordAuthentication no

Host autobot-frontend 172.16.168.21
    HostName 172.16.168.21
    User autobot
    IdentityFile ~/.ssh/autobot_key
```

### Inventory Configuration

The `production.yml` inventory uses SSH key authentication:

```yaml
all:
  vars:
    ansible_user: autobot
    ansible_ssh_private_key_file: ~/.ssh/autobot_key
    ansible_become: yes
    # No ansible_password or ansible_become_password
```

### Passwordless Sudo

The `setup-passwordless-sudo.yml` playbook creates `/etc/sudoers.d/autobot-nopasswd`:

```
autobot ALL=(ALL) NOPASSWD: ALL
```

## Usage Scenarios

### Standard Deployment (After Setup)

```bash
# No password prompts required
./deploy.sh --full
./deploy.sh --services
./deploy.sh --health-check
```

### First-Time Setup

```bash
# Configure passwordless sudo (one-time)
./deploy.sh --setup-sudo
# You'll be prompted for the sudo password
```

### Using Vault Credentials

If passwordless sudo isn't configured, use vault:

```bash
# With interactive vault password prompt
./deploy.sh --use-vault --services

# With vault password file
./deploy.sh --vault-file ~/.vault_pass --services

# With become password prompt
./deploy.sh --ask-become-pass --services
```

### Managing the Vault

```bash
# Edit encrypted vault
ansible-vault edit inventory/group_vars/vault.yml

# View encrypted vault
ansible-vault view inventory/group_vars/vault.yml

# Rekey (change password)
ansible-vault rekey inventory/group_vars/vault.yml
```

## Security Considerations

### What's Protected

1. **No SSH passwords** - SSH key authentication only
2. **No plaintext sudo passwords** - Either passwordless sudo or vault-encrypted
3. **Host key verification** - `StrictHostKeyChecking=accept-new`

### Best Practices

1. **Protect the SSH private key**: `chmod 600 ~/.ssh/autobot_key`
2. **Use a strong vault password**: Store in a password manager
3. **Don't commit vault password files**: Add to `.gitignore`
4. **Limit network access**: AutoBot VMs are on an isolated network

### Network Security

The passwordless sudo configuration is secure because:

- VMs are on an isolated internal network (172.16.168.0/24)
- SSH is the only remote access method
- SSH only accepts key-based authentication
- Firewall rules restrict access to the internal network

## Emergency Recovery (Lockout Prevention)

### Recovery Methods

If SSH key authentication fails, you have these fallback options:

#### 1. Password Authentication (Recommended)

Force password auth from the client:

```bash
# Emergency SSH with password
ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no autobot@172.16.168.21

# For Ansible operations
ansible all -i inventory/production.yml -m ping \
  -e "ansible_ssh_pass=autobot" \
  -e "ansible_ssh_private_key_file="
```

#### 2. Hyper-V Console Access

If network access is completely lost:

1. Open Hyper-V Manager
2. Connect to VM console
3. Login as `autobot` with password
4. Fix SSH keys: `cat ~/.ssh/authorized_keys`

#### 3. Re-deploy SSH Key

```bash
# From WSL, re-copy the SSH key
ssh-copy-id -i ~/.ssh/autobot_key.pub -o PreferredAuthentications=password autobot@172.16.168.21
```

### Preventing Lockouts

1. **Never disable password auth on VM sshd** - Keep as fallback
2. **Backup SSH keys** - Copy `~/.ssh/autobot_key*` to secure location
3. **Test recovery** - Periodically verify password login works
4. **Document passwords** - Keep in vault.yml (encrypted)

### Key Recovery Commands

```bash
# Check if key exists
ls -la ~/.ssh/autobot_key

# Verify key permissions (should be 600)
chmod 600 ~/.ssh/autobot_key

# Test key authentication
ssh -v autobot@172.16.168.21

# Regenerate key if corrupted
ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ''
ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@172.16.168.21
```

## Troubleshooting

### SSH Connection Fails

```bash
# Verify key permissions
ls -la ~/.ssh/autobot_key
# Should be: -rw------- (600)

# Test SSH manually
ssh -vvv -i ~/.ssh/autobot_key autobot@172.16.168.21
```

### Permission Denied (sudo)

```bash
# Run setup-sudo playbook again
./deploy.sh --setup-sudo

# Or use become password prompt
./deploy.sh --ask-become-pass --services
```

### Vault Password Issues

```bash
# Decrypt vault for editing
ansible-vault decrypt inventory/group_vars/vault.yml

# Re-encrypt after editing
ansible-vault encrypt inventory/group_vars/vault.yml
```

## Migration Notes

### Before (Insecure)

```yaml
# OLD - DO NOT USE
ansible_password: autobot
ansible_become_password: autobot
```

### After (Secure)

```yaml
# NEW - Secure configuration
ansible_ssh_private_key_file: ~/.ssh/autobot_key
# No plaintext passwords
```

## Related Documentation

- [Infrastructure Deployment Guide](INFRASTRUCTURE_DEPLOYMENT.md)
- [SSH Configuration](../../ansible/docs/SSH_CONFIG.md)
- [Ansible Best Practices](https://docs.ansible.com/ansible/latest/user_guide/playbooks_best_practices.html)
