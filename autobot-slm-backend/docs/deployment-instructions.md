# AutoBot Hyper-V Deployment Guide

## Overview

This comprehensive Ansible deployment system migrates AutoBot from Docker containers to native,
role-based Hyper-V VMs, providing enhanced performance, security, and scalability. AutoBot has no
fixed machine count: roles can be co-located in Docker, on one VM, or split across however many
machines an operator chooses. The example below shows one reference layout with one machine per role.

## Architecture Migration

### From Docker
```
docker-compose.yml:
├── dns-cache          → Frontend role
├── redis              → Database role
├── browser-service    → Browser role
├── frontend           → Frontend role
├── ai-stack           → AI/ML role
├── npu-worker         → AI/ML role
├── models (volume)    → Database role
└── autobot (backend)  → Backend role
```

### To Hyper-V VMs (one worked example, per-role machine count is a deployment choice)
```
Role-Based Architecture:
├── Frontend role (<frontend-ip>)
│   ├── nginx (reverse proxy)
│   ├── Vue.js frontend
│   └── DNS cache (unbound)
├── Backend role (<backend-ip>)
│   ├── FastAPI server
│   ├── Python services
│   └── Log aggregation
├── Database role (<database-ip>)
│   ├── Redis Stack 7.4
│   ├── Model storage
│   └── Data persistence
├── AI/ML role (<aiml-ip>)
│   ├── AI Stack server
│   ├── NPU Worker
│   └── Intel OpenVINO
└── Browser role (<browser-ip>)
    ├── Playwright automation
    ├── VNC server
    └── Desktop environment
```

## Prerequisites

### 1. Windows Hyper-V Setup
```powershell
# Run as Administrator
.\scripts\hyperv\create-autobot-vms.ps1
.\scripts\hyperv\discover-vm-ips.ps1 -UpdateInventory
```

### 2. Ubuntu Installation
- Install Ubuntu Server 22.04 LTS on each machine
- Create `autobot` user with sudo privileges
- Configure static IP addresses as specified
- Enable SSH service

### 3. SSH Key Setup
```bash
# Generate deployment key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ""

# Copy to every deployment machine
for ip in <frontend-ip> <backend-ip> <database-ip> <aiml-ip> <browser-ip>; do
    ssh-copy-id -i ~/.ssh/autobot_key.pub autobot@$ip
done
```

### 4. Ansible Installation
```bash
pip install ansible
ansible-galaxy install -r ansible/requirements.yml
```

## Quick Start Deployment

### 1. Update Inventory
Edit `ansible/inventory/production.yml` with your actual machine IP addresses, one group per role:
```yaml
frontend:
  hosts:
    autobot-frontend:
      ansible_host: <frontend-ip>  # YOUR_FRONTEND_IP
backend:
  hosts:
    autobot-backend:
      ansible_host: <backend-ip>  # YOUR_BACKEND_IP
# ... update every role group's IP(s)
```

### 2. Test Connectivity
```bash
cd ansible
ansible all -m ping
```

### 3. Full Deployment
```bash
./deploy.sh --full
```

This will:
1. **Base System** (5 minutes) - Ubuntu updates, security, users
2. **Database** (8 minutes) - Redis Stack installation and configuration  
3. **Backend** (6 minutes) - Python environment and FastAPI setup
4. **AI/ML** (12 minutes) - AI services and Intel OpenVINO
5. **Frontend** (4 minutes) - Vue.js build and nginx configuration
6. **Browser** (7 minutes) - Desktop environment and Playwright
7. **Data Migration** (10 minutes) - Transfer data from Docker containers
8. **Service Startup** (5 minutes) - Start all services in dependency order
9. **Health Validation** (3 minutes) - Comprehensive service testing

**Total Deployment Time: ~60 minutes**

## Step-by-Step Deployment

### Phase 1: Base System
```bash
./deploy.sh --base-system
```
- Ubuntu system updates and security hardening
- User management and SSH configuration
- Firewall setup and network configuration
- System monitoring and log aggregation setup

### Phase 2: Service Installation
```bash
./deploy.sh --services
```
- Install services in dependency order:
  1. Database (Redis Stack)
  2. Backend (FastAPI, Python services)
  3. AI/ML (AI Stack, NPU Worker, OpenVINO)
  4. Frontend (Vue.js, nginx)
  5. Browser (Playwright, VNC, desktop)

### Phase 3: Data Migration
```bash
./deploy.sh --data-migration
```
- Export data from Docker containers
- Transfer Redis database, models, and configurations
- Import data to the role machines
- Validate data integrity

### Phase 4: Service Startup
```bash
./deploy.sh --start
```
- Start services in proper dependency order
- Wait for service readiness
- Configure inter-service communication

## Service Endpoints

| Service | URL | Description |
|---------|-----|-------------|
| **Web Interface** | `http://<frontend-ip>` | Main AutoBot UI |
| **API Backend** | `http://<backend-ip>:8001/api` | REST API |
| **Database** | `redis://<database-ip>:6379` | Redis Stack |
| **RedisInsight** | `http://<database-ip>:8002` | Database management |
| **AI Stack** | `http://<aiml-ip>:8080` | AI inference server |
| **NPU Worker** | `http://<npu-ip>:8081` | NPU acceleration |
| **Browser API** | `http://<browser-ip>:3000` | Playwright automation |
| **VNC Desktop** | `vnc://<browser-ip>:5901` | Remote desktop |

## Management Commands

### Health Checks
```bash
./deploy.sh --health-check          # Full health validation
./utils/health-check.sh --quick     # Quick port check
./utils/health-check.sh --full      # Comprehensive check
```

### Service Management
```bash
./deploy.sh --start                 # Start all services
./deploy.sh --stop                  # Stop all services
./deploy.sh --restart               # Restart all services
```

### Backup Operations
```bash
./utils/backup.sh --full            # Complete backup
./utils/backup.sh --full --compress # Compressed backup
./utils/backup.sh --quick           # Redis only
./utils/backup.sh --list            # List backups
./utils/backup.sh --cleanup 7       # Remove old backups
```

### Log Analysis
```bash
# System logs
sudo journalctl -u autobot-* -f

# Service-specific logs
ssh autobot@<backend-ip> "sudo journalctl -u autobot-backend -f"
ssh autobot@<aiml-ip> "sudo journalctl -u autobot-ai-stack -f"

# Health check logs
tail -f /var/log/autobot/health-check*.log
```

## Troubleshooting

### Common Issues

#### 1. Deployment Machine Connectivity Problems
```bash
# Test SSH connectivity
ansible all -m ping

# Check firewall status
ansible all -m command -a "ufw status"

# Verify network configuration
ansible all -m setup -a "filter=ansible_default_ipv4"
```

#### 2. Service Startup Failures
```bash
# Check service status
ansible all -m systemd -a "name=autobot-backend" --become

# View service logs
ssh autobot@<backend-ip> "sudo journalctl -u autobot-backend --since '10 minutes ago'"

# Manual service restart
ssh autobot@<backend-ip> "sudo systemctl restart autobot-backend"
```

#### 3. Data Migration Issues
```bash
# Verify Redis data
redis-cli -h <database-ip> -p 6379 dbsize
redis-cli -h <database-ip> -p 6379 info keyspace

# Check model files
ssh autobot@<aiml-ip> "find /var/lib/autobot/models -type f | wc -l"

# Validate configurations
ssh autobot@<backend-ip> "ls -la /etc/autobot/"
```

#### 4. Performance Issues
```bash
# Check system resources
ansible all -m shell -a "top -bn1 | head -20"
ansible all -m shell -a "free -h"
ansible all -m shell -a "df -h"

# Monitor network connectivity
ansible all -m shell -a "netstat -tuln | grep LISTEN"
```

### Recovery Procedures

#### Service Recovery
```bash
# Stop problematic services
./deploy.sh --stop

# Re-run specific deployment phase
ansible-playbook -i inventory/production.yml playbooks/deploy-backend.yml

# Start services again
./deploy.sh --start
```

#### Data Recovery
```bash
# Restore from backup
./utils/restore.sh --from-backup=/opt/autobot/backups/full-20241205-143022

# Re-run data migration
ansible-playbook -i inventory/production.yml playbooks/data-migration.yml
```

#### Complete Rollback
```bash
./deploy.sh --rollback
```

## Performance Optimization

### System Tuning
Each role is optimized for its specific responsibility, whether or not it shares a machine
with another role:

**Frontend role**:
- nginx worker processes: auto
- Vue.js build optimization
- DNS cache for fast resolution
- Static file compression

**Backend role**:
- FastAPI with 4 workers
- Connection pooling
- Log aggregation and rotation
- Memory-optimized Python settings

**Database role**:
- Redis maxmemory: 6GB
- Optimized persistence (RDB + AOF)
- Kernel parameters for Redis
- Automatic cleanup and maintenance

**AI/ML role**:
- Intel OpenVINO optimization
- NPU device access
- Model caching and optimization
- GPU passthrough (if available)

**Browser role**:
- Desktop environment optimization
- VNC compression settings
- Playwright resource limits
- Browser sandbox configuration

### Monitoring
```bash
# Real-time monitoring
watch -n 5 './utils/health-check.sh --quick'

# Performance dashboard
./utils/monitor-performance.sh --dashboard

# Resource alerts
./utils/setup-alerts.sh --cpu-threshold=80 --memory-threshold=85
```

## Security

### Network Security
- Internal network isolation (your deployment's subnet)
- UFW firewall on each role's machine
- SSH key-only authentication
- Service-specific port restrictions

### Application Security
- Service user isolation
- File permission hardening
- Log access controls
- Regular security updates

### Data Security
- Encrypted backups
- Redis data persistence
- Configuration file protection
- Secure inter-service communication
- SSO credentials encrypted at rest (AES-256-GCM via `system_secrets` table)

### SSO Secret Migration

When deploying a build that includes PR #9676 for the first time, run the SSO
secret migration to move OAuth `client_secret` and LDAP `bind_password` from
plaintext JSONB to encrypted storage:

```bash
# On the backend role's machine, before restarting the service:
source /etc/autobot/slm-secrets.env
cd /opt/autobot/autobot-slm-backend && source venv/bin/activate
python migrations/migrate_sso_secrets_to_system_secret.py
```

See [docs/sso-secret-migration.md](sso-secret-migration.md) for the full
migration guide (prerequisites, verification, rollback, Ansible automation).

## Maintenance

### Daily Tasks
```bash
# Health check
./deploy.sh --health-check

# Quick backup
./utils/backup.sh --quick
```

### Weekly Tasks
```bash
# Full backup
./utils/backup.sh --full --compress

# System updates
ansible all -m apt -a "update_cache=yes upgrade=yes" --become

# Performance review
./utils/performance-report.sh --weekly
```

### Monthly Tasks
```bash
# Security audit
ansible-playbook -i inventory/production.yml playbooks/security-audit.yml

# Cleanup old backups
./utils/backup.sh --cleanup 30

# System optimization
ansible-playbook -i inventory/production.yml playbooks/optimize-system.yml
```

## Migration Benefits

### Performance Improvements
- **Native VM Performance**: No Docker overlay overhead
- **Dedicated Resources**: Guaranteed RAM/CPU per service
- **Optimized Storage**: Direct filesystem access
- **Network Performance**: Machine-to-machine at memory speeds when co-located

### Scalability Enhancements
- **Independent Scaling**: Scale each role separately
- **Resource Isolation**: One service can't starve others
- **Load Distribution**: Distribute load across as many machines as needed
- **Future Migration**: Easy migration to separate physical machines

### Operational Benefits
- **Service Independence**: Service failures don't cascade
- **Easier Debugging**: Clear role boundaries
- **Simplified Monitoring**: Per-role resource monitoring
- **Backup Granularity**: Service-specific backup strategies

### Security Advantages
- **Network Isolation**: Internal network with firewall protection
- **Process Isolation**: Full machine-level isolation when roles are split out
- **Credential Separation**: Separate SSH keys and users
- **Attack Surface Reduction**: Minimal exposed services

## Support

### Documentation
- `ansible/README.md` - Complete deployment documentation
- `ansible/inventory/group_vars/` - Configuration reference
- `ansible/playbooks/` - Deployment playbook details
- `/var/log/autobot/` - System and application logs

### Validation
```bash
# Post-deployment validation
./deploy.sh --health-check
curl http://<frontend-ip>/health
redis-cli -h <database-ip> ping
```

### Emergency Contacts
- Deployment logs: `/var/log/autobot/deployment/`
- Health check logs: `/var/log/autobot/health-check*.log`
- Service logs: `journalctl -u autobot-*`

---

**Deployment Status**: Ready for production use  
**Migration Path**: Docker containers → role-based Hyper-V VMs (one worked example above; machine count is a deployment choice)  
**Performance**: Native VM speed with dedicated resources  
**Security**: Internal network isolation with firewall protection  
**Scalability**: Independent service scaling and resource allocation
