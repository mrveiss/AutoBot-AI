# Ansible Role Deployment Failures

**Issue Number**: #807, #837
**Date Reported**: 2026-02-08, 2026-02-11
**Severity**: High
**Component**: Infrastructure / Ansible

---

## Symptoms

- Ansible playbook fails with "role not found" error
- Duplicate role warnings during playbook execution
- Tasks skip with "no hosts matched" message
- Venv creation fails with "Python version mismatch"
- Services fail to start after deployment
- Pip fails to install packages

## Root Causes

1. **Duplicate roles**: Same role in multiple paths
2. **Missing `ansible.cfg`**: Roles not in search path
3. **Stale fact cache**: Old OS info after upgrade
4. **Venv Python mismatch**: System Python changed (3.8→3.10)
5. **Missing role defaults**: Variables undefined
6. **Internet idempotency**: Fleet VMs offline, downloads fail

## Quick Fix

```bash
# 1. Remove duplicate roles
cd autobot-slm-backend/ansible
find roles -name "duplicate_role" -type d | xargs rm -rf

# 2. Clear fact cache after OS upgrade
rm -rf /tmp/ansible_fact_cache/*

# 3. Run from ansible/ directory
cd autobot-slm-backend/ansible
ansible-playbook -i inventory.yml playbook.yml

# 4. Recreate venv if Python mismatch
ssh target-vm "rm -rf /opt/autobot/component/venv"
ansible-playbook provision.yml --tags component
```

## Resolution Steps

### Issue 1: Role Not Found

```bash
# Error: "the role 'my_role' was not found"

# Fix: Ensure ansible.cfg points to roles directory
cd autobot-slm-backend/ansible
cat ansible.cfg | grep roles_path
# Should show: roles_path = roles

# Run playbook from ansible/ directory
ansible-playbook -i inventory.yml playbook.yml
```

### Issue 2: Duplicate Roles

```bash
# Error: "WARNING: Found duplicate role 'xxx'"

# Find duplicates
find autobot-slm-backend/ansible/roles -type d -name "my_role"

# Remove duplicates, keep correct version in roles/
rm -rf ansible/roles/old_location/my_role
```

### Issue 3: Stale Fact Cache

```bash
# After OS upgrade (Ubuntu 20.04→22.04), playbook uses old facts

# Clear cache for specific host
rm /tmp/ansible_fact_cache/172.16.168.22

# Or clear all
rm -rf /tmp/ansible_fact_cache/*

# Re-run playbook to refresh facts
ansible-playbook -i inventory.yml playbook.yml
```

### Issue 4: Venv Python Mismatch

```bash
# Error: "bad interpreter: No such file or directory"
# After OS upgrade, venv has old Python

# Detect and recreate venv (in Ansible role)
- name: Check Python version mismatch
  command: "{{ venv_path }}/bin/python --version"
  register: venv_python
  failed_when: false

- name: Recreate venv if mismatch
  shell: |
    rm -rf {{ venv_path }}
    python3 -m venv {{ venv_path }}
  when: venv_python.rc != 0

# After recreating, upgrade pip
- name: Upgrade pip
  pip:
    name: pip
    state: latest
    virtualenv: "{{ venv_path }}"
```

### Issue 5: Missing Role Defaults

```bash
# Error: "undefined variable: 'some_var'"

# Add to roles/my_role/defaults/main.yml
---
some_var: "default_value"
npu_port: 8081
npu_user: autobot
```

### Issue 6: Internet Idempotency

```bash
# Fleet VMs may not have internet
# All download tasks must check if software exists

# Bad (fails offline)
- name: Install Node.js
  shell: curl -fsSL https://deb.nodesource.com/setup_20.x | bash -

# Good (idempotent)
- name: Check if Node.js installed
  command: node --version
  register: node_check
  failed_when: false

- name: Install Node.js
  shell: curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
  when: node_check.rc != 0
```

## Verification

```bash
# 1. Check role exists
ls autobot-slm-backend/ansible/roles/my_role/tasks/main.yml

# 2. Validate ansible.cfg
cd autobot-slm-backend/ansible && ansible-config dump | grep roles_path

# 3. Test role syntax
ansible-playbook playbook.yml --syntax-check

# 4. Dry run
ansible-playbook playbook.yml --check

# 5. Run with verbose logging
ansible-playbook playbook.yml -vvv
```

## Prevention

1. **Always run from `ansible/` directory**
2. **Clear fact cache after OS upgrades**
3. **Add idempotency checks**:
   - Check if venv exists before creating
   - Check if software installed before downloading
4. **Use role defaults** for all variables
5. **Test roles offline** to ensure idempotency

## References

- PR #807: Remove duplicate roles
- PR #837: Fix idempotency in 8 roles
- Issue #814: SLM manager Ansible role
