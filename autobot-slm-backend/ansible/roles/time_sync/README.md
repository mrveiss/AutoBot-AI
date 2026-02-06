# AutoBot Time Synchronization Role

This Ansible role ensures all VMs in the AutoBot distributed infrastructure use the same timezone and NTP time synchronization as the main machine.

## Overview

The main machine uses `Europe/Riga` timezone (EEST, +0300), and all VMs must be synchronized to this timezone with proper NTP configuration to ensure:

- Consistent timestamps across all logs and databases
- Proper coordination between distributed services
- Accurate analytics and monitoring data
- Synchronized backup and maintenance schedules

## Features

- **Timezone Synchronization**: Sets all VMs to `Europe/Riga` timezone
- **NTP Configuration**: Uses regional Latvian NTP servers with global fallbacks
- **Service Choice**: Supports both `systemd-timesyncd` (default) and `chrony`
- **Hardware Clock Sync**: Maintains hardware clock in UTC with system clock sync
- **Monitoring**: 15-minute automated health checks with logging
- **Validation**: Comprehensive time drift and sync status validation
- **Fallback Servers**: Multiple NTP server tiers for reliability

## Configuration

### Default Variables (`defaults/main.yml`)

```yaml
time_sync:
  timezone: "Europe/Riga"  # Main machine timezone
  ntp:
    enabled: true
    servers:
      - "0.lv.pool.ntp.org"
      - "1.lv.pool.ntp.org"
      - "2.lv.pool.ntp.org"
      - "3.lv.pool.ntp.org"
    use_chrony: false  # Use systemd-timesyncd by default
  validation:
    max_drift_seconds: 60
    sync_retries: 3
    retry_delay: 10
  logging:
    enable_detailed_logs: true
    log_file: "/var/log/autobot/time-sync.log"
```

### Global Configuration (`inventory/group_vars/all.yml`)

```yaml
system:
  time_sync:
    enabled: true
    timezone: "Europe/Riga"
    ntp_servers:
      - "0.lv.pool.ntp.org"
      - "1.lv.pool.ntp.org"
      - "2.lv.pool.ntp.org"
      - "3.lv.pool.ntp.org"
    fallback_servers:
      - "time.google.com"
      - "time.cloudflare.com"
      - "pool.ntp.org"
    monitoring_enabled: true
    force_sync_on_deploy: true
```

## Usage

### Deploy via Main Site Playbook

The `time_sync` role is included in the main `site.yml`:

```bash
cd ansible
ansible-playbook site.yml --tags time_sync
```

### Deploy via Dedicated Playbook

Use the specialized time synchronization playbook:

```bash
cd ansible
ansible-playbook playbooks/deploy-time-sync.yml
```

### Quick Check and Fix

Use the utility script to check and fix time sync issues:

```bash
# Check all VMs
./scripts/utilities/check-time-sync.sh

# Check main machine only
./scripts/utilities/check-time-sync.sh main

# Force synchronization
./scripts/utilities/check-time-sync.sh force

# Deploy via Ansible
./scripts/utilities/check-time-sync.sh deploy
```

## Files and Templates

### Main Task File (`tasks/main.yml`)
- Timezone configuration
- NTP service setup (systemd-timesyncd or chrony)
- Force immediate synchronization
- Validation and monitoring setup
- Hardware clock synchronization

### Configuration Templates
- `templates/timesyncd.conf.j2` - systemd-timesyncd configuration
- `templates/chrony.conf.j2` - Chrony configuration (alternative)
- `templates/check-time-sync.sh.j2` - Monitoring script template
- `templates/time-sync-logrotate.j2` - Log rotation configuration

### Handlers (`handlers/main.yml`)
- Service restart handlers for time sync services
- System service restart handlers (rsyslog, cron)

## Monitoring and Validation

### Automated Monitoring
- **Frequency**: Every 15 minutes via cron
- **Log Location**: `/var/log/autobot/time-sync.log`
- **Script**: `/usr/local/bin/check-time-sync.sh`

### Manual Validation Commands

```bash
# Check time sync status
timedatectl status

# Check NTP service (systemd-timesyncd)
systemctl status systemd-timesyncd
timedatectl timesync-status

# Check NTP service (chrony alternative)
systemctl status chrony
chronyc sources -v
chronyc tracking

# Run health check
/usr/local/bin/check-time-sync.sh status

# Force synchronization
/usr/local/bin/check-time-sync.sh force-sync

# View logs
tail -f /var/log/autobot/time-sync.log
```

### Expected Output

After successful deployment, `timedatectl status` should show:

```
               Local time: Thu 2025-09-18 12:45:00 EEST
           Universal time: Thu 2025-09-18 09:45:00 UTC
                 RTC time: Thu 2025-09-18 09:45:00
                Time zone: Europe/Riga (EEST, +0300)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```

## Troubleshooting

### Common Issues

1. **Time not synchronized**
   ```bash
   sudo systemctl restart systemd-timesyncd
   sudo /usr/local/bin/check-time-sync.sh force-sync
   ```

2. **Wrong timezone**
   ```bash
   sudo timedatectl set-timezone Europe/Riga
   ```

3. **NTP servers unreachable**
   - Check network connectivity
   - Verify firewall rules (NTP uses port 123/UDP)
   - Try fallback servers

4. **Service conflicts**
   ```bash
   # If both chrony and systemd-timesyncd are running
   sudo systemctl stop chrony
   sudo systemctl disable chrony
   sudo systemctl start systemd-timesyncd
   ```

### Log Analysis

```bash
# Check time sync logs
grep "time sync" /var/log/autobot/time-sync.log

# Check system time logs
journalctl -u systemd-timesyncd

# Check for errors
grep ERROR /var/log/autobot/time-sync.log
```

## Integration with AutoBot

### Service Dependencies
Time synchronization is applied early in the deployment process before other services to ensure:
- Database timestamps are consistent
- Log aggregation works properly
- Monitoring and analytics have accurate timestamps
- Backup schedules are coordinated

### Network Requirements
- **Outbound UDP 123**: For NTP server communication
- **Regional NTP Access**: Latvian NTP pool servers
- **Fallback Connectivity**: Google, Cloudflare time servers

### Security Considerations
- NTP traffic is secured through firewall rules
- Time sync validation prevents time-based security issues
- Hardware clock sync prevents time drift on reboot
- Monitoring detects time manipulation attempts

## Regional Adaptations

To adapt for different geographic regions, update the NTP servers:

```yaml
# For United States
ntp_servers:
  - "0.us.pool.ntp.org"
  - "1.us.pool.ntp.org"
  - "2.us.pool.ntp.org"
  - "3.us.pool.ntp.org"

# For United Kingdom
ntp_servers:
  - "0.uk.pool.ntp.org"
  - "1.uk.pool.ntp.org"
  - "2.uk.pool.ntp.org"
  - "3.uk.pool.ntp.org"
```

## Contributing

When modifying this role:

1. Update version in `defaults/main.yml`
2. Test with both systemd-timesyncd and chrony
3. Verify monitoring scripts work correctly
4. Update documentation and examples
5. Test timezone changes and NTP server failures

## Support

For issues with time synchronization:

1. Check logs: `/var/log/autobot/time-sync.log`
2. Run validation: `./scripts/utilities/check-time-sync.sh`
3. Force resync: `./scripts/utilities/check-time-sync.sh force`
4. Redeploy: `ansible-playbook playbooks/deploy-time-sync.yml`
