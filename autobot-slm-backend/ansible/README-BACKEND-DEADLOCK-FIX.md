# Backend Worker Deadlock Fix - Issue #876

## Problem
The backend service was configured with 4 workers, causing a deadlock during initialization where workers try to connect to themselves.

## Solution
This playbook reconfigures the backend systemd service to use single worker mode, which is recommended for async FastAPI applications.

## Prerequisites
- Ansible installed
- SSH access to backend server (or local access for WSL)
- Sudo privileges

## Usage

### Run the fix (with sudo password prompt):
```bash
cd /home/kali/Desktop/AutoBot/autobot-slm-backend/ansible
ansible-playbook fix-backend-worker-deadlock.yml --ask-become-pass
```

### Dry run (check mode):
```bash
ansible-playbook fix-backend-worker-deadlock.yml --ask-become-pass --check
```

### Run without password prompt (if passwordless sudo configured):
```bash
ansible-playbook fix-backend-worker-deadlock.yml
```

## What the Playbook Does

1. **Backup** - Creates timestamped backup of current service file
2. **Update** - Replaces service file with single-worker configuration
3. **Restart** - Stops and starts backend service cleanly
4. **Verify** - Runs health checks and verifies no deadlock (no SYN_SENT connections)
5. **Report** - Shows service status and confirmation

## Expected Output

```
PLAY RECAP *********************************************************************
autobot-host               : ok=15   changed=5    unreachable=0    failed=0
```

## Verification

After running, verify the backend is working:

```bash
# Check service status
sudo systemctl status autobot-backend

# Check for deadlock (should return empty)
sudo lsof -i :8443 | grep SYN_SENT

# Test login page
curl -k https://172.16.168.21/
```

## Rollback

If needed, restore from backup:
```bash
sudo cp /etc/systemd/system/autobot-backend.service.backup-<timestamp> /etc/systemd/system/autobot-backend.service
sudo systemctl daemon-reload
sudo systemctl restart autobot-backend
```

## Related Issues
- Issue #876 - Backend worker deadlock
- Issue #869 - Login page delay (also fixed in this deployment)
