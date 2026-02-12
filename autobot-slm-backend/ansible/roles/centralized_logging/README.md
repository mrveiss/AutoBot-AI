# Centralized Logging Role

Ansible role for deploying Loki + Promtail centralized logging infrastructure across AutoBot fleet.

## Features

- Loki log aggregation server installation
- Promtail log shipper deployment
- Multi-target log collection (systemd, files, journal)
- Automatic log rotation with configurable retention
- Systemd service integration
- Log labeling with hostname, service, environment

## Requirements

- Ubuntu 22.04 or later
- Ansible 2.9+
- Sudo privileges
- Network connectivity to Loki server

## Role Variables

### Loki Server Settings

```yaml
loki_version: "2.9.3"
loki_http_port: 3100
loki_grpc_port: 9095
loki_data_dir: "/var/lib/loki"
loki_retention_period: "720h"  # 30 days
loki_log_level: "info"
```

### Promtail Settings

```yaml
promtail_version: "2.9.3"
promtail_http_port: 9080
promtail_positions_file: "/var/lib/promtail/positions.yaml"
```

### Log Collection

```yaml
log_targets:
  - name: "systemd-journal"
    enabled: true
    job_name: "systemd"
    source: "journal"

  - name: "application-logs"
    enabled: true
    job_name: "apps"
    source: "file"
    paths:
      - "/var/log/autobot/*.log"
      - "/var/log/autobot/**/*.log"
```

### Log Rotation

```yaml
log_rotation_enabled: true
log_rotation_days: 14
log_rotation_size: "100M"
log_rotation_compress: true
```

## Example Playbook

```yaml
- hosts: autobot
  become: yes
  roles:
    - role: centralized_logging
      vars:
        loki_retention_period: "720h"
        log_targets:
          - name: "systemd-journal"
            enabled: true
            job_name: "systemd"
            source: "journal"
```

## Tags

- `loki` - Loki server installation
- `promtail` - Promtail agent installation
- `config` - Configuration deployment
- `service` - Service management
- `rotation` - Log rotation setup

## Usage Examples

```bash
# Full deployment
ansible-playbook deploy-centralized-logging.yml

# Deploy Loki server only
ansible-playbook deploy-centralized-logging.yml --tags loki

# Deploy Promtail agents only
ansible-playbook deploy-centralized-logging.yml --tags promtail

# Update configuration only
ansible-playbook deploy-centralized-logging.yml --tags config
```

## Architecture

```
┌─────────────────┐
│   Loki Server   │ :3100 (HTTP), :9095 (gRPC)
│  (Log Storage)  │
└────────┬────────┘
         │
         ├─────────┐
         │         │
    ┌────▼────┐ ┌─▼──────┐
    │Promtail │ │Promtail│
    │ Agent 1 │ │ Agent 2│
    └────┬────┘ └─┬──────┘
         │        │
    ┌────▼────────▼─────┐
    │   Application      │
    │   Logs             │
    └────────────────────┘
```

## Log Query Examples

```bash
# Query logs from specific service
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="systemd",unit="autobot-backend.service"}' \
  --data-urlencode 'limit=100'

# Query error logs
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={level="error"}' \
  --data-urlencode 'limit=100'
```

## Files Created

- `/etc/loki/loki-config.yml` - Loki server configuration
- `/etc/systemd/system/loki.service` - Loki systemd service
- `/etc/promtail/promtail-config.yml` - Promtail configuration
- `/etc/systemd/system/promtail.service` - Promtail systemd service
- `/etc/logrotate.d/autobot-logs` - Log rotation configuration

## Verification

```bash
# Check Loki service
systemctl status loki

# Check Promtail service
systemctl status promtail

# Test Loki API
curl http://localhost:3100/ready

# Check Promtail targets
curl http://localhost:9080/targets

# Query recent logs
curl -G -s "http://localhost:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="systemd"}' \
  --data-urlencode 'limit=10'
```

## Troubleshooting

### Loki not starting

Check permissions:
```bash
ls -la /var/lib/loki
chown -R loki:loki /var/lib/loki
```

### Promtail not collecting logs

Check configuration:
```bash
journalctl -u promtail -n 50
cat /var/lib/promtail/positions.yaml
```

### No logs appearing in Loki

Verify network connectivity:
```bash
curl http://<loki-server>:3100/ready
netstat -tlnp | grep 3100
```

## Performance Tuning

For high-volume logging (>1GB/day):

```yaml
loki_ingestion_rate_mb: 100
loki_ingestion_burst_size_mb: 200
loki_max_chunk_age: "2h"
loki_chunk_idle_period: "30m"
```

## Security Considerations

- Loki runs as dedicated `loki` user (non-root)
- Promtail runs with minimal permissions
- Log retention configured to prevent disk exhaustion
- Systemd security hardening applied
- Consider enabling authentication for production use

## License

Copyright (c) 2025 mrveiss. All rights reserved.
