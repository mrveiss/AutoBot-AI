# Issue #722: Secure Credential Handling for GUI-Added Nodes

**Date:** 2026-01-19
**Issue:** https://github.com/mrveiss/AutoBot-AI/issues/722
**Status:** Ready for implementation

## Summary

Improve credential handling for GUI-added nodes during enrollment by:
1. Configuring passwordless sudo during enrollment
2. Verifying SSH key deployment succeeded
3. Adding GUI indicators for auth method transition

## Current State

| Component | Status |
|-----------|--------|
| SSH key auto-copied during enrollment | ✅ Already implemented |
| Host record updated to SSH key auth | ✅ Already implemented |
| Passwordless sudo configured | ❌ Not implemented |
| SSH key verification | ❌ Not implemented |
| GUI shows auth method | ❌ Not implemented |

## Design Decisions

### Password Handling in CLI Args
**Decision:** Keep current approach (`-e ansible_ssh_pass=X`)

**Rationale:** This is a one-time enrollment operation. After enrollment completes, SSH keys are deployed and passwords are cleared from the database. The brief exposure in `ps aux` during enrollment is acceptable.

## Implementation Tasks

### Task 1: Add Passwordless Sudo Configuration
**File:** `slm-server/services/deployment.py`

Add task to `_create_enrollment_playbook()` after SSH key deployment:
```yaml
- name: Configure passwordless sudo for autobot user
  copy:
    dest: /etc/sudoers.d/autobot-nopasswd
    content: "{{ slm_agent_user }} ALL=(ALL) NOPASSWD: ALL"
    mode: '0440'
    validate: '/usr/sbin/visudo -cf %s'
```

### Task 2: Add SSH Key Verification
**File:** `slm-server/services/deployment.py`

Add verification task after key deployment:
```yaml
- name: Verify SSH key deployment
  command: grep -q "SLM Server" /home/{{ slm_agent_user }}/.ssh/authorized_keys
  register: key_check
  failed_when: key_check.rc != 0
  when: slm_server_pubkey | length > 0
```

### Task 3: Add Auth Method Badge to Node Display
**File:** `slm-admin/src/components/fleet/NodeLifecyclePanel.vue`

Display `auth_method` field as a badge on node cards:
- "Password" badge (yellow/warning) for password auth
- "SSH Key" badge (green/success) for key auth

### Task 4: Show Transition Indicator During Enrollment
**File:** `slm-admin/src/components/fleet/NodeLifecyclePanel.vue`

When node status is `ENROLLING`, show message: "Transitioning to SSH key auth..."

## Acceptance Criteria Mapping

| Criteria | Implementation |
|----------|----------------|
| SSH key automatically copied during enrollment | Already done |
| Passwordless sudo configured during enrollment | Task 1 |
| Host record updated to SSH key auth after enrollment | Already done |
| Password not exposed in process arguments | Accepted as-is (one-time operation) |
| GUI shows auth method transition | Tasks 3 & 4 |

## Files Modified

- `slm-server/services/deployment.py` - Add sudo and verification tasks
- `slm-admin/src/components/fleet/NodeLifecyclePanel.vue` - Add auth method display
