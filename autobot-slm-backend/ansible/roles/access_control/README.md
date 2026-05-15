# Access Control Role

Ansible role for deploying and managing access control policies, audit logging, and gradual rollout across AutoBot infrastructure.

## Features

- Access control policy configuration
- Audit logging with rotation
- Session ownership validation
- Gradual rollout orchestration (7 phases)
- Access monitoring with systemd timers
- Validation testing
- Rollback capabilities
- Management scripts

## Requirements

- Ubuntu 22.04 or later
- Ansible 2.9+
- Sudo privileges
- Redis accessible
- Complements existing `service_auth` role from issue #255

## Role Variables

### Core Settings

```yaml
access_control_mode: log_only  # log_only, partial, full
enable_audit_logging: true
enable_session_validation: true
```

### Policies

```yaml
access_policies:
  - name: "session_ownership"
    enabled: true
    enforcement_level: "{{ access_control_mode }}"
  - name: "resource_permissions"
    enabled: true
    enforcement_level: "{{ access_control_mode }}"
```

### Audit Logging

```yaml
audit_log_level: INFO
audit_log_rotation: 7  # days
audit_log_format: json
audit_backends:
  - file
  - redis
```

### Gradual Rollout

```yaml
rollout_phase: 0  # 0-6 (prep, backfill, audit, log_only, partial, full, validation)
auto_proceed_phases: false
```

### Monitoring

```yaml
enable_access_monitoring: true
monitoring_interval: 60  # seconds
alert_on_violations: true
alert_threshold: 10  # violations per minute
```

## Gradual Rollout Phases

0. **Prerequisites** - Check environment, backup Redis
1. **Backfill** - Populate session ownership data
2. **Audit Logging** - Enable audit logging
3. **Log Only** - Monitor without enforcement
4. **Partial Enforcement** - Gradual enforcement
5. **Full Enforcement** - Complete enforcement
6. **Validation** - Post-deployment validation

## Example Playbook

```yaml
- hosts: slm_server
  become: yes
  roles:
    - role: access_control
      vars:
        access_control_mode: "log_only"
        rollout_phase: 3
        enable_audit_logging: true
```

## Tags

- `backup` - Redis backup
- `policies` - Policy configuration
- `audit` - Audit logging
- `sessions` - Session ownership
- `rollout` - Rollout phases
- `monitoring` - Access monitoring
- `validation` - Validation tests
- `scripts` - Management scripts

## Usage Examples

```bash
# Full deployment in log-only mode
ansible-playbook deploy-access-control.yml

# Deploy policies only
ansible-playbook deploy-access-control.yml --tags policies

# Setup monitoring
ansible-playbook deploy-access-control.yml --tags monitoring

# Run validation
ansible-playbook deploy-access-control.yml --tags validation
```

## Generated Scripts

### Status Script

```bash
# Display access control status
/opt/autobot/scripts/access_control/status.sh
```

### Validation Script

```bash
# Validate configuration
/opt/autobot/scripts/access_control/validate.sh
```

### Rollback Script

```bash
# Rollback access control changes
/opt/autobot/scripts/access_control/rollback.sh
```

## Directory Structure

```
access_control/
├── defaults/
│   └── main.yml              # Default variables
├── handlers/
│   └── main.yml              # Service handlers
├── tasks/
│   ├── main.yml              # Main orchestration
│   ├── backup.yml            # Redis backup
│   ├── policies.yml          # Policy configuration
│   ├── audit_logging.yml     # Audit setup
│   ├── session_ownership.yml # Session validation
│   ├── rollout.yml           # Rollout orchestration
│   ├── monitoring.yml        # Monitoring setup
│   ├── validation.yml        # Validation tests
│   └── scripts.yml           # Script deployment
└── templates/
    ├── access_policies.yml.j2   # Policy configuration
    ├── validate.sh.j2           # Validation script
    └── status.sh.j2             # Status script
```

## Integration with service_auth Role

This role complements the existing `service_auth` role (issue #255):

- **service_auth**: Inter-service authentication keys
- **access_control**: User access policies and audit logging

Both roles work together to provide comprehensive security.

## Verification

```bash
# Check status
/opt/autobot/scripts/access_control/status.sh

# Validate configuration
/opt/autobot/scripts/access_control/validate.sh

# Check monitoring
systemctl status autobot-access-monitor.timer

# View audit logs
tail -f /var/log/autobot/audit/*.log
```

## Troubleshooting

### Validation fails

Check configuration:
```bash
cat /etc/autobot/access_control/policies.yml
```

### Monitoring not running

Restart monitoring:
```bash
systemctl restart autobot-access-monitor.timer
```

### Audit logs not created

Check permissions:
```bash
ls -la /var/log/autobot/audit/
```

## License

Copyright (c) 2025 mrveiss. All rights reserved.
