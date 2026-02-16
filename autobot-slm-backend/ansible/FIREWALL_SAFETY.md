# Firewall Safety Guidelines

## Critical Rule: NEVER Lock Yourself Out

When modifying firewall rules on remote machines, **ALWAYS ensure SSH access is maintained**.

## Pre-Flight Checklist

**Before ANY firewall changes:**

1. ✅ Ensure SSH service is enabled: `systemctl enable ssh`
2. ✅ Ensure SSH port 22 is allowed in firewall
3. ✅ Test SSH connection from management machine
4. ✅ Have console/direct access available as backup

## Safety Playbook

We have a dedicated playbook to ensure SSH stays accessible:

```bash
cd autobot-slm-backend/ansible
ansible-playbook -i inventory/slm-nodes.yml playbooks/ensure-ssh-access.yml
```

**Run this playbook BEFORE:**
- Modifying UFW rules
- Security hardening
- Network configuration changes
- Any change that might affect SSH access

## Safe Firewall Modification Pattern

```bash
# 1. FIRST: Ensure SSH is protected
ansible-playbook -i inventory/slm-nodes.yml playbooks/ensure-ssh-access.yml

# 2. THEN: Make your firewall changes
ansible-playbook -i inventory/slm-nodes.yml playbooks/your-firewall-changes.yml

# 3. VERIFY: Test SSH still works
ansible all -i inventory/slm-nodes.yml -m ping
```

## Recovery from Lockout

If you do get locked out:

### Option 1: Console Access (Preferred)
1. Access VM console (Hyper-V, VMware, VirtualBox, etc.)
2. Login directly on console
3. Fix firewall: `sudo ufw allow 22/tcp`
4. Enable SSH: `sudo systemctl start ssh`

### Option 2: Reboot (May work)
- Reboot the VM
- Some firewall rules reset on reboot
- SSH service starts automatically

### Option 3: Rebuild (Last resort)
- Rebuild the VM from Ansible
- Run `deploy-full.yml` playbook

## Fleet Status Check

Check SSH access across entire fleet:

```bash
# Quick ping test
ansible all -i inventory/slm-nodes.yml -m ping

# Detailed check
for ip in 172.16.168.{19..27}; do
  echo -n "$ip: "
  ssh -o ConnectTimeout=2 autobot@$ip "hostname" 2>/dev/null && echo "✓" || echo "✗"
done
```

## UFW Best Practices

### DO:
✅ Allow SSH before enabling UFW: `ufw allow 22/tcp`
✅ Enable UFW after allowing SSH: `ufw enable`
✅ Use `ufw status` to verify rules before activating
✅ Add comments to rules: `ufw allow 22/tcp comment 'SSH - DO NOT REMOVE'`

### DON'T:
❌ Enable UFW without allowing SSH first
❌ Remove port 22 rules without console access
❌ Test firewall changes in production without backup access
❌ Assume "default allow" means SSH will work

## Emergency Commands

If you're on console and locked out:

```bash
# Disable firewall temporarily
sudo ufw disable

# Allow SSH
sudo ufw allow 22/tcp

# Re-enable firewall
sudo ufw enable

# Start SSH service
sudo systemctl start ssh
sudo systemctl enable ssh

# Verify
sudo systemctl status ssh
sudo ufw status | grep 22
```

## Ansible Inventory Note

All machines in `inventory/slm-nodes.yml` should have:
- `ansible_port: 22` (default, can omit)
- `ansible_user: autobot` (standard user)
- SSH key authentication configured

## Remember

> **"Measure twice, cut once"**
>
> Always ensure SSH access BEFORE making firewall changes.
> Console access is your last resort - don't rely on it.
