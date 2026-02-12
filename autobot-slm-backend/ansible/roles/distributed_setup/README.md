# Distributed Setup Role

Ansible role for configuring AutoBot's distributed architecture across multiple VMs.

## Features

- Fleet node discovery and inventory
- Connectivity testing across all nodes
- Redis CLI tools installation
- SSH key distribution for inter-node communication
- Distributed configuration deployment
- Service management scripts generation
- Health monitoring with systemd timers
- Automated backup collection from all nodes
- Comprehensive verification

## Requirements

- Ubuntu 22.04 or later
- Ansible 2.9+
- Sudo privileges on target hosts
- Network connectivity between all fleet nodes

## Role Variables

### Core Settings

```yaml
service_user: autobot          # Service account
service_group: autobot         # Service group
project_root: /opt/autobot     # Installation directory
distributed_mode: true         # Enable distributed mode
coordinator_host: "{{ ansible_default_ipv4.address }}"  # Coordinator IP
```

### Fleet Configuration

```yaml
fleet_nodes: []                # Auto-discovered from slm_nodes group
connectivity_timeout: 5        # Connection timeout in seconds
connectivity_retries: 3        # Number of retry attempts
```

### Redis CLI

```yaml
redis_cli_install: true        # Install Redis CLI tools
redis_cli_version: "7.4.0"     # Redis version for build
redis_cli_build_from_source: false  # Build if no package manager access
```

### SSH Configuration

```yaml
ssh_key_path: ~/.ssh/autobot_fleet  # SSH key location
ssh_key_type: rsa              # Key type
ssh_key_bits: 4096             # Key size
ssh_setup_required: true       # Deploy SSH keys
```

### Health Monitoring

```yaml
health_check_enabled: true     # Enable health monitoring
health_check_interval: 60      # Check interval (seconds)
health_check_endpoints:        # Endpoints to monitor
  - name: "Backend API"
    url: "http://{{ coordinator_host }}:8001/api/health"
```

### Backup Configuration

```yaml
backup_enabled: true           # Enable automated backups
backup_schedule: "0 2 * * *"   # Cron schedule (daily 2 AM)
backup_retention_days: 7       # Backup retention period
```

## Dependencies

- `community.crypto` collection (for SSH key generation)

Install dependencies:
```bash
ansible-galaxy collection install community.crypto
```

## Example Playbook

```yaml
- hosts: slm_server
  become: yes
  roles:
    - role: distributed_setup
      vars:
        coordinator_host: "172.16.168.19"
        health_check_interval: 30
        backup_schedule: "0 3 * * *"
```

## Tags

- `discovery` - Fleet node discovery
- `connectivity` - Connectivity testing
- `redis` - Redis CLI installation
- `ssh` - SSH key setup
- `config` - Configuration deployment
- `scripts` - Service management scripts
- `monitoring` - Health monitoring
- `backup` - Backup setup
- `verify` - Verification tasks

## Usage Examples

```bash
# Full distributed setup
ansible-playbook deploy-distributed-setup.yml

# Setup SSH keys only
ansible-playbook deploy-distributed-setup.yml --tags ssh

# Update configuration only
ansible-playbook deploy-distributed-setup.yml --tags config

# Setup monitoring only
ansible-playbook deploy-distributed-setup.yml --tags monitoring

# Verify setup without changes
ansible-playbook deploy-distributed-setup.yml --tags verify --check
```

## Generated Scripts

After deployment, the following scripts are available:

### Health Management

```bash
# Check health of all distributed services
/opt/autobot/scripts/distributed/check-health.sh

# Display distributed status and URLs
/opt/autobot/scripts/distributed/distributed-status.sh

# View health monitoring results
/opt/autobot/scripts/distributed/view-health-status.sh
```

### Service Management

```bash
# Start coordinator service
systemctl start autobot-coordinator

# Start/stop health monitoring
systemctl start autobot-health-monitor.timer
systemctl stop autobot-health-monitor.timer

# View health monitor logs
journalctl -u autobot-health-monitor -f
```

### Backup Management

```bash
# Collect backups from all nodes
/opt/autobot/scripts/distributed/collect-backups.sh

# Cleanup old backups
/opt/autobot/scripts/distributed/cleanup-backups.sh

# View backup logs
tail -f /var/log/autobot/backup.log
```

## Directory Structure

```
distributed_setup/
├── defaults/
│   └── main.yml              # Default variables
├── handlers/
│   └── main.yml              # Service handlers
├── tasks/
│   ├── main.yml              # Main orchestration
│   ├── fleet_discovery.yml   # Node discovery
│   ├── connectivity.yml      # Connectivity testing
│   ├── redis_cli.yml         # Redis CLI setup
│   ├── ssh_setup.yml         # SSH configuration
│   ├── config.yml            # Configuration deployment
│   ├── service_scripts.yml   # Script generation
│   ├── health_monitoring.yml # Health monitoring
│   ├── backup_setup.yml      # Backup configuration
│   └── verify.yml            # Verification
└── templates/
    ├── fleet_registry.json.j2        # Fleet inventory
    ├── distributed.env.j2            # Environment variables
    ├── fleet_topology.yml.j2         # Topology configuration
    ├── ssh_config.j2                 # SSH client config
    ├── check-health.sh.j2            # Health check script
    ├── collect-backups.sh.j2         # Backup collection
    ├── autobot-coordinator.service.j2  # Coordinator service
    └── autobot-health-monitor.*.j2   # Monitoring service/timer
```

## Verification

After deployment, verify the setup:

```bash
# Check coordinator service
systemctl status autobot-coordinator

# Verify fleet discovery
cat /etc/autobot/fleet_registry.json

# Test connectivity to all nodes
/opt/autobot/scripts/distributed/check-health.sh

# Verify SSH access
ssh autobot@<node-ip> 'echo SSH access verified'

# Check health monitoring
systemctl status autobot-health-monitor.timer

# View generated configuration
ls -l /etc/autobot/distributed/
```

## Troubleshooting

### SSH key authentication fails

Check key permissions and deployment:
```bash
ls -la ~/.ssh/autobot_fleet*
ssh -vvv autobot@<node-ip>
```

### Health checks fail

Verify service endpoints and connectivity:
```bash
curl http://<coordinator>:8001/api/health
nc -zv <node-ip> <node-port>
```

### Redis CLI not found

If building from source, check compilation:
```bash
ls -la ~/.local/bin/redis-cli
export PATH="$HOME/.local/bin:$PATH"
```

### Fleet discovery returns no nodes

Verify Ansible inventory:
```bash
ansible-inventory --list
ansible slm_nodes --list-hosts
```

## License

Copyright (c) 2025 mrveiss. All rights reserved.
