# DNS Role

Ansible role for configuring DNS resolution across AutoBot fleet nodes.

## Features

- Automatic fleet DNS mapping generation from inventory
- /etc/hosts management with fleet entries
- Hostname configuration (short name or FQDN)
- DNS caching with dnsmasq or systemd-resolved
- DNS resolution testing across fleet
- Management scripts for DNS operations

## Requirements

- Ubuntu 22.04 or later
- Ansible 2.9+
- Sudo privileges on target hosts

## Role Variables

### Core Settings

```yaml
dns_domain: autobot.local      # DNS domain for fleet
dns_search_domains:            # DNS search domains
  - autobot.local
  - local
```

### /etc/hosts Management

```yaml
manage_etc_hosts: true         # Manage /etc/hosts entries
create_short_aliases: true     # Create short name aliases
custom_host_entries: []        # Additional custom entries
```

### Hostname Configuration

```yaml
set_hostname: true             # Configure system hostname
hostname_fqdn: true            # Use FQDN (e.g., redis.autobot.local)
```

### DNS Caching

```yaml
install_dnsmasq: true          # Install dnsmasq for DNS caching
dnsmasq_cache_size: 1000       # Cache size (number of entries)
dnsmasq_listen_address: 127.0.0.1
dnsmasq_port: 53

# OR use systemd-resolved
use_systemd_resolved: false    # Use systemd-resolved instead
systemd_resolved_fallback_dns:
  - 8.8.8.8
  - 1.1.1.1
```

### DNS Testing

```yaml
test_dns_resolution: true      # Test DNS after configuration
dns_test_timeout: 5            # Test timeout (seconds)
dns_test_required_nodes:       # Nodes that must be reachable
  - redis
  - slm_server
```

## Dependencies

None. This role is self-contained.

## Example Playbook

```yaml
- hosts: all
  become: yes
  roles:
    - role: dns
      vars:
        dns_domain: "production.autobot.local"
        install_dnsmasq: true
        dnsmasq_cache_size: 2000
        create_short_aliases: true
```

## Tags

- `mappings` - Generate DNS mappings
- `hostname` - Configure hostnames
- `hosts` - Manage /etc/hosts
- `dnsmasq` - Setup dnsmasq cache
- `systemd-resolved` - Configure systemd-resolved
- `test` - Test DNS resolution
- `scripts` - Deploy management scripts

## Usage Examples

```bash
# Full DNS deployment
ansible-playbook deploy-dns.yml

# Update /etc/hosts only
ansible-playbook deploy-dns.yml --tags hosts

# Setup DNS caching only
ansible-playbook deploy-dns.yml --tags dnsmasq

# Test DNS resolution
ansible-playbook deploy-dns.yml --tags test

# Deploy to specific host
ansible-playbook deploy-dns.yml --limit redis
```

## Generated Scripts

After deployment, the following scripts are available:

### Test DNS Resolution

```bash
# Test DNS resolution across all fleet nodes
/opt/autobot/scripts/dns/test-dns-resolution.sh
```

Output includes:
- Hostname resolution tests
- Connectivity tests (port 22)
- DNS cache status

### Show DNS Entries

```bash
# Display fleet DNS entries and configuration
/opt/autobot/scripts/dns/show-dns-entries.sh
```

Shows:
- /etc/hosts fleet entries
- Fleet node IP mappings
- DNS configuration
- Current DNS servers

### Refresh DNS

```bash
# Restart DNS services and flush cache
/opt/autobot/scripts/dns/refresh-dns.sh
```

Performs:
- DNS service restart (dnsmasq or systemd-resolved)
- Cache flush
- Resolution test

## Directory Structure

```
dns/
├── defaults/
│   └── main.yml              # Default variables
├── handlers/
│   └── main.yml              # Service handlers
├── tasks/
│   ├── main.yml              # Main orchestration
│   ├── generate_mappings.yml # Fleet DNS mapping generation
│   ├── hostname.yml          # Hostname configuration
│   ├── etc_hosts.yml         # /etc/hosts management
│   ├── dnsmasq.yml           # dnsmasq setup
│   ├── systemd_resolved.yml  # systemd-resolved config
│   ├── test_dns.yml          # DNS testing
│   └── scripts.yml           # Script deployment
└── templates/
    ├── dnsmasq.conf.j2       # dnsmasq configuration
    ├── resolv.conf.j2        # resolv.conf template
    ├── resolved.conf.j2      # systemd-resolved config
    ├── test-dns-resolution.sh.j2    # Test script
    ├── show-dns-entries.sh.j2       # Show entries script
    └── refresh-dns.sh.j2            # Refresh DNS script
```

## How It Works

1. **Fleet Discovery**: Generates DNS mappings from Ansible inventory
2. **Hostname Configuration**: Sets system hostname (short or FQDN)
3. **/etc/hosts Management**: Updates /etc/hosts with fleet entries
4. **DNS Caching**: Installs and configures dnsmasq or systemd-resolved
5. **DNS Testing**: Verifies resolution and connectivity
6. **Script Deployment**: Creates management scripts

## Fleet DNS Mapping

The role automatically generates DNS entries for all inventory hosts:

```
# Example generated entries
172.16.168.23    redis.autobot.local redis autobot-redis
172.16.168.22    npu-worker.autobot.local npu-worker autobot-npu-worker
172.16.168.19    slm-server.autobot.local slm-server autobot-slm-server
```

Each entry includes:
- IP address
- FQDN (hostname.domain)
- Short hostname
- Aliases (with and without autobot prefix)

## DNS Resolution Order

With dnsmasq enabled:

1. Local cache (dnsmasq)
2. /etc/hosts
3. Upstream DNS servers (8.8.8.8, 1.1.1.1)

With systemd-resolved:

1. systemd-resolved cache
2. /etc/hosts
3. Configured DNS servers
4. Fallback DNS servers

## Verification

After deployment, verify DNS configuration:

```bash
# Test resolution
/opt/autobot/scripts/dns/test-dns-resolution.sh

# Show DNS entries
/opt/autobot/scripts/dns/show-dns-entries.sh

# Check DNS service
systemctl status dnsmasq         # If using dnsmasq
systemctl status systemd-resolved  # If using systemd-resolved

# Manual resolution test
host redis.autobot.local
getent hosts redis
dig @127.0.0.1 redis.autobot.local
```

## Troubleshooting

### DNS resolution fails

Check /etc/hosts entries:
```bash
grep "AutoBot Fleet DNS" /etc/hosts
```

Verify DNS service:
```bash
systemctl status dnsmasq
systemctl status systemd-resolved
```

### DNS cache not working

Restart DNS service:
```bash
/opt/autobot/scripts/dns/refresh-dns.sh
```

Check DNS configuration:
```bash
cat /etc/resolv.conf
resolvectl status  # For systemd-resolved
```

### Hostname resolution slow

Increase dnsmasq cache size:
```yaml
dnsmasq_cache_size: 5000
```

Check for DNS timeout issues:
```bash
time host redis.autobot.local
```

## License

Copyright (c) 2025 mrveiss. All rights reserved.
