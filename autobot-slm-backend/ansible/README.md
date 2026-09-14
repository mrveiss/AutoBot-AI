# AutoBot Hyper-V Deployment System

## Overview

This Ansible deployment system migrates AutoBot from Docker containers to native, role-based Hyper-V VMs for enhanced performance, security, and scalability. AutoBot has no fixed machine count: roles can be co-located in Docker, on one VM, or split across however many machines an operator chooses. The example below shows one reference layout with one machine per role.

## Architecture

### Example Role Distribution

**From Docker Containers:**
```
Containers → Roles (one worked example, machine count is a deployment choice)
├── dns-cache          → Frontend role - DNS cache service
├── redis              → Database role - Redis Stack
├── browser-service    → Browser role - Playwright automation
├── frontend           → Frontend role - Vue.js application
├── ai-stack           → AI/ML role - AI inference server
├── npu-worker         → AI/ML role - NPU acceleration
├── models             → Database role - Model storage
└── autobot (backend)  → Backend role - FastAPI server
```

**To Role-Based Architecture:**
```
Frontend role     - Ubuntu Server 22.04 LTS
├── nginx (reverse proxy & static files)
├── Node.js 20+ (Vue.js frontend)
├── DNS cache (unbound)
└── Frontend assets & builds

Backend role      - Ubuntu Server 22.04 LTS
├── Python 3.14+ (FastAPI server)
├── Backend APIs & services
├── Log aggregation (rsyslog)
└── Application state management

Database role     - Ubuntu Server 22.04 LTS
├── Redis Stack 7.4+ (primary database)
├── Model storage & versioning
├── Data persistence & backups
└── Database monitoring

AI/ML role        - Ubuntu Server 22.04 LTS
├── AI Stack (LLM inference)
├── NPU Worker (hardware acceleration)
├── Intel OpenVINO & drivers
└── Model serving & optimization

Browser role      - Ubuntu Desktop 22.04 LTS
├── Playwright automation
├── Chrome/Firefox browsers
├── VNC server (remote access)
└── Desktop automation services
```

Each role above may run on its own machine, be co-located with others, or run more than one
instance — there is no fixed count.

## Quick Start

### 1. Prepare VM Infrastructure

```bash
# On Windows host - create VMs with PowerShell
.\scripts\hyperv\create-autobot-vms.ps1

# Discover VM IPs after Ubuntu installation
.\scripts\hyperv\discover-vm-ips.ps1 -UpdateInventory
```

### 2. Update Inventory

Edit `inventory/production.yml` with your machines' IP addresses, one group per role:

```yaml
all:
  vars:
    ansible_user: autobot
    ansible_ssh_private_key_file: ~/.ssh/autobot_key
  children:
    frontend:
      hosts:
        autobot-frontend:
          ansible_host: <frontend-ip>  # Update with your IP
    backend:
      hosts:
        autobot-backend:
          ansible_host: <backend-ip>  # Update with your IP
    # ... etc for every role group; co-locate groups on one host or split
    # them across as many machines as the deployment needs
```

### 3. Test Connectivity

```bash
ansible all -m ping
```

### 4. Deploy AutoBot

```bash
# Full deployment (recommended for first run)
./deploy.sh --full

# Or step-by-step deployment
./deploy.sh --base-system    # Install base system
./deploy.sh --services       # Install services
./deploy.sh --data-migration # Migrate data
./deploy.sh --start          # Start services
```

## Deployment Scripts

### Main Deployment Script

```bash
./deploy.sh [OPTIONS]

Options:
  --full             Complete deployment (base + services + data + start)
  --base-system      Install base system only (Ubuntu updates, users, security)
  --services         Install AutoBot services only
  --data-migration   Migrate data from Docker/existing system
  --start            Start AutoBot services
  --stop             Stop AutoBot services
  --restart          Restart AutoBot services
  --health-check     Validate all services are healthy
  --rollback         Rollback to previous version
  --help             Show this help message
```

### Service-Specific Deployments

```bash
# Deploy specific VM type
ansible-playbook -i inventory/production.yml playbooks/deploy-frontend.yml
ansible-playbook -i inventory/production.yml playbooks/deploy-backend.yml
ansible-playbook -i inventory/production.yml playbooks/deploy-database.yml
ansible-playbook -i inventory/production.yml playbooks/deploy-aiml.yml
ansible-playbook -i inventory/production.yml playbooks/deploy-browser.yml
```

## File Structure

```
ansible/
├── README.md                 # This file
├── deploy.sh                 # Main deployment script
├── ansible.cfg              # Ansible configuration
├── requirements.yml         # Ansible collections/roles
├── inventory/
│   ├── production.yml       # Production VM inventory (template)
│   ├── development.yml      # Development inventory
│   └── group_vars/
│       ├── all.yml          # Global variables
│       ├── frontend.yml     # Frontend VM variables
│       ├── backend.yml      # Backend VM variables
│       ├── database.yml     # Database VM variables
│       ├── aiml.yml         # AI/ML VM variables
│       └── browser.yml      # Browser VM variables
├── playbooks/
│   ├── deploy-full.yml      # Complete deployment orchestration
│   ├── deploy-base.yml      # Base system setup
│   ├── deploy-frontend.yml  # Frontend VM deployment
│   ├── deploy-backend.yml   # Backend VM deployment
│   ├── deploy-database.yml  # Database VM deployment
│   ├── deploy-aiml.yml      # AI/ML VM deployment
│   ├── deploy-browser.yml   # Browser VM deployment
│   ├── data-migration.yml   # Data migration from Docker
│   ├── health-check.yml     # Service health validation
│   └── rollback.yml         # Rollback procedures
├── roles/
│   ├── base-system/         # Ubuntu base system setup
│   ├── autobot-frontend/    # Frontend service role
│   ├── autobot-backend/     # Backend service role
│   ├── autobot-database/    # Database service role
│   ├── autobot-aiml/        # AI/ML service role
│   ├── autobot-browser/     # Browser service role
│   ├── data-migration/      # Data migration utilities
│   └── monitoring/          # System monitoring setup
├── templates/
│   ├── nginx/               # Nginx configuration templates
│   ├── systemd/             # Systemd service files
│   ├── environment/         # Environment variable files
│   └── config/              # Application configuration
├── files/
│   ├── keys/                # SSH keys and certificates
│   ├── scripts/             # Utility scripts
│   └── configs/             # Static configuration files
└── utils/
    ├── backup.sh            # Backup utilities
    ├── restore.sh           # Restore utilities
    ├── health-check.sh      # Health checking script
    └── migration-helper.sh  # Data migration helper
```

## Configuration

### Network Settings

The system uses your internal network configuration (subnet and gateway are set during
install and are never hardcoded):
- **Network**: your deployment's internal subnet
- **Gateway**: your Hyper-V host
- **DNS**: 8.8.8.8, 1.1.1.1

### Service Ports

| Service | Role | Internal Port | External Port | Description |
|---------|-------|---------------|---------------|-------------|
| Vue.js Frontend | Frontend | 5173 | 80 (nginx) | Web interface |
| FastAPI Backend | Backend | 8001 | 8001 | API server |
| Redis Stack | Database | 6379 | 6379 | Database |
| Redis Insight | Database | 8001 | 8002 | DB management |
| AI Stack | AI/ML | 8080 | 8080 | AI inference |
| NPU Worker | AI/ML | 8081 | 8081 | NPU acceleration |
| Playwright | Browser | 3000 | 3000 | Browser automation |
| VNC Server | Browser | 5901 | 6080 | Remote desktop |

## Data Migration

### Automated Migration Process

1. **Export from Docker**:
   ```bash
   # Redis data export
   docker exec autobot-redis redis-cli BGSAVE
   docker cp autobot-redis:/data/dump.rdb ./backup/

   # Model files export
   docker cp autobot-ai-stack:/app/models ./backup/

   # Configuration export
   docker cp autobot-backend:/app/config ./backup/
   ```

2. **Transfer to VMs**:
   ```bash
   # Automated by Ansible data-migration playbook
   ansible-playbook -i inventory/production.yml playbooks/data-migration.yml
   ```

3. **Import to the role machines**:
   ```bash
   # Redis data import
   scp backup/dump.rdb autobot@<database-ip>:/var/lib/redis/
   ssh autobot@<database-ip> sudo systemctl restart redis-stack-server

   # Model files sync
   rsync -av backup/models/ autobot@<aiml-ip>:/opt/autobot/models/
   ```

## Service Management

### SystemD Service Files

All services are managed via systemd with proper dependencies:

```bash
# Check service status
systemctl status autobot-backend
systemctl status autobot-frontend
systemctl status autobot-ai-stack
systemctl status autobot-npu-worker
systemctl status redis-stack-server

# Service logs
journalctl -u autobot-backend -f
journalctl -u autobot-frontend -f
```

### Service Dependencies

```
Redis (Database) → Backend → AI/ML → Frontend → Browser
     ↑                                                ↓
     └─────────────── Model Storage ← ─────────────────┘
```

## Monitoring & Health Checks

### Built-in Health Checks

```bash
# Run comprehensive health check
./utils/health-check.sh

# Individual service health
curl http://<frontend-ip>/health  # Frontend
curl http://<backend-ip>:8001/api/health  # Backend
curl http://<aiml-ip>:8080/health  # AI Stack
curl http://<npu-ip>:8081/health  # NPU Worker
redis-cli -h <database-ip> ping  # Redis
```

### Log Aggregation

All logs are centralized on the backend role's machine:
- **Location**: `/var/log/autobot/`
- **Retention**: 30 days, 100MB max per service
- **Format**: JSON structured logs

## Backup & Recovery

### Automated Backups

```bash
# Full system backup
./utils/backup.sh --full

# Service-specific backups
./utils/backup.sh --redis
./utils/backup.sh --models
./utils/backup.sh --configs
```

### Recovery Procedures

```bash
# Full system restore
./utils/restore.sh --full --from-backup=/path/to/backup

# Service-specific restore
./utils/restore.sh --redis --from-backup=/path/to/redis-backup
```

## Troubleshooting

### Common Issues

1. **Deployment Machine Connectivity**:
   ```bash
   # Test network connectivity
   ansible all -m ping

   # Check firewall rules
   ansible all -m command -a "ufw status"
   ```

2. **Service Dependencies**:
   ```bash
   # Check service dependency tree
   systemctl list-dependencies autobot-backend
   ```

3. **Performance Issues**:
   ```bash
   # Monitor resource usage
   ansible all -m command -a "htop -n 1"
   ansible all -m command -a "free -h"
   ```

### Log Analysis

```bash
# Search logs across all deployment machines
./utils/search-logs.sh "error" --last-24h

# Performance monitoring
./utils/monitor-performance.sh --duration=1h
```

## Security

### Network Security
- Internal network isolation (your deployment's subnet)
- Windows Firewall protection
- No direct internet exposure

### Machine Security
- UFW firewall on each role's machine
- SSH key-based authentication
- Regular security updates via Ansible

### Application Security
- Service-specific user accounts
- File permission restrictions
- Encrypted inter-service communication

## Maintenance

### Regular Updates

```bash
# System package updates
ansible all -m apt -a "upgrade=yes update_cache=yes" --become

# AutoBot application updates
./deploy.sh --services --skip-data
```

### Performance Tuning

```bash
# Optimize database performance
ansible database -m command -a "redis-cli CONFIG SET save '60 1000'"

# Adjust service resource limits
# Edit the unit templates and redeploy. The backend unit's single source of
# truth is roles/backend/templates/autobot-backend.service.j2 (#10005);
# other units live in templates/systemd/ and roles/*/templates/.
```

## Migration Timeline

1. **Phase 1** (30 minutes): Machine preparation and base system setup
2. **Phase 2** (45 minutes): Service installation and configuration
3. **Phase 3** (20 minutes): Data migration from Docker
4. **Phase 4** (15 minutes): Service startup and health checks
5. **Phase 5** (10 minutes): Validation and testing

**Total Deployment Time**: ~2 hours for complete migration

## Support & Documentation

- **Playbook Documentation**: See individual role README files
- **Configuration Reference**: Check `group_vars/` files for all options
- **Troubleshooting Guide**: See `docs/troubleshooting.md`
- **Performance Tuning**: See `docs/performance.md`

---

**Next Steps After Deployment:**

1. Verify all services are healthy
2. Update DNS entries if needed
3. Configure backup schedule
4. Set up monitoring dashboards
5. Run load testing to validate performance
