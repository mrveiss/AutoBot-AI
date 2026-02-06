# AutoBot Hyper-V Deployment Guide

## Overview

This comprehensive Ansible deployment system migrates AutoBot from 8 Docker containers to 5 optimized Hyper-V VMs, providing enhanced performance, security, and scalability.

## Architecture Migration

### From Docker (8 Containers)
```
docker-compose.yml:
├── dns-cache          → VM1 (Frontend)
├── redis              → VM3 (Database)  
├── browser-service    → VM5 (Browser)
├── frontend           → VM1 (Frontend)
├── ai-stack           → VM4 (AI/ML)
├── npu-worker         → VM4 (AI/ML)
├── models (volume)    → VM3 (Database)
└── autobot (backend)  → VM2 (Backend)
```

### To Hyper-V VMs (5 VMs)
```
VM Architecture:
├── VM1 (192.168.100.10) - Frontend
│   ├── nginx (reverse proxy)
│   ├── Vue.js frontend
│   └── DNS cache (unbound)
├── VM2 (192.168.100.20) - Backend  
│   ├── FastAPI server
│   ├── Python services
│   └── Log aggregation
├── VM3 (192.168.100.50) - Database
│   ├── Redis Stack 7.4
│   ├── Model storage
│   └── Data persistence
├── VM4 (192.168.100.30) - AI/ML
│   ├── AI Stack server
│   ├── NPU Worker
│   └── Intel OpenVINO
└── VM5 (192.168.100.40) - Browser
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
- Install Ubuntu Server 22.04 LTS on each VM
- Create `autobot` user with sudo privileges
- Configure static IP addresses as specified
- Enable SSH service

### 3. SSH Key Setup
```bash
# Generate deployment key
ssh-keygen -t rsa -b 4096 -f ~/.ssh/autobot_key -N ""

# Copy to all VMs
for ip in 192.168.100.10 192.168.100.20 192.168.100.50 192.168.100.30 192.168.100.40; do
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
Edit `ansible/inventory/production.yml` with your actual VM IP addresses:
```yaml
frontend:
  hosts:
    autobot-frontend:
      ansible_host: 192.168.100.10  # YOUR_FRONTEND_IP
backend:
  hosts:
    autobot-backend:
      ansible_host: 192.168.100.20  # YOUR_BACKEND_IP
# ... update all VM IPs
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
- Import data to appropriate VMs
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
| **Web Interface** | http://192.168.100.10 | Main AutoBot UI |
| **API Backend** | http://192.168.100.20:8001/api | REST API |
| **Database** | redis://192.168.100.50:6379 | Redis Stack |
| **RedisInsight** | http://192.168.100.50:8002 | Database management |
| **AI Stack** | http://192.168.100.30:8080 | AI inference server |
| **NPU Worker** | http://192.168.100.40:8081 | NPU acceleration |
| **Browser API** | http://192.168.100.40:3000 | Playwright automation |
| **VNC Desktop** | vnc://192.168.100.40:5901 | Remote desktop |

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
ssh autobot@192.168.100.20 "sudo journalctl -u autobot-backend -f"
ssh autobot@192.168.100.30 "sudo journalctl -u autobot-ai-stack -f"

# Health check logs
tail -f /var/log/autobot/health-check*.log
```

## Troubleshooting

### Common Issues

#### 1. VM Connectivity Problems
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
ssh autobot@192.168.100.20 "sudo journalctl -u autobot-backend --since '10 minutes ago'"

# Manual service restart
ssh autobot@192.168.100.20 "sudo systemctl restart autobot-backend"
```

#### 3. Data Migration Issues
```bash
# Verify Redis data
redis-cli -h 192.168.100.50 -p 6379 dbsize
redis-cli -h 192.168.100.50 -p 6379 info keyspace

# Check model files
ssh autobot@192.168.100.30 "find /var/lib/autobot/models -type f | wc -l"

# Validate configurations
ssh autobot@192.168.100.20 "ls -la /etc/autobot/"
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
Each VM is optimized for its specific role:

**Frontend VM (VM1)**:
- nginx worker processes: auto
- Vue.js build optimization
- DNS cache for fast resolution
- Static file compression

**Backend VM (VM2)**:
- FastAPI with 4 workers
- Connection pooling
- Log aggregation and rotation
- Memory-optimized Python settings

**Database VM (VM3)**:
- Redis maxmemory: 6GB
- Optimized persistence (RDB + AOF)
- Kernel parameters for Redis
- Automatic cleanup and maintenance

**AI/ML VM (VM4)**:
- Intel OpenVINO optimization
- NPU device access
- Model caching and optimization
- GPU passthrough (if available)

**Browser VM (VM5)**:
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
- Internal network isolation (192.168.100.0/24)
- UFW firewall on each VM
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
- **Network Performance**: VM-to-VM at memory speeds

### Scalability Enhancements
- **Independent Scaling**: Scale each service separately
- **Resource Isolation**: One service can't starve others
- **Load Distribution**: Distribute load across VMs
- **Future Migration**: Easy migration to separate physical machines

### Operational Benefits
- **Service Independence**: Service failures don't cascade
- **Easier Debugging**: Clear service boundaries
- **Simplified Monitoring**: VM-level resource monitoring
- **Backup Granularity**: Service-specific backup strategies

### Security Advantages
- **Network Isolation**: Internal network with firewall protection
- **Process Isolation**: Full VM-level isolation
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
curl http://192.168.100.10/health
redis-cli -h 192.168.100.50 ping
```

### Emergency Contacts
- Deployment logs: `/var/log/autobot/deployment/`
- Health check logs: `/var/log/autobot/health-check*.log`
- Service logs: `journalctl -u autobot-*`

---

**Deployment Status**: Ready for production use  
**Migration Path**: Docker containers → 5 Hyper-V VMs  
**Performance**: Native VM speed with dedicated resources  
**Security**: Internal network isolation with firewall protection  
**Scalability**: Independent service scaling and resource allocation
