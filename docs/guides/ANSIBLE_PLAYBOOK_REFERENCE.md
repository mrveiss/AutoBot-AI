# AutoBot Ansible Playbook Reference

**MANDATORY: Use Ansible for infrastructure deployment and management**

## Available Playbooks

### 1. **Full Production Deployment**
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-full.yml
```
**Purpose**: Complete 5-VM infrastructure deployment with Docker to Hyper-V migration
**Components**: Base system, database, backend, AI/ML, frontend, browser, data migration
**Timeline**: Full functional deployment with health validation

### 2. **Development Services Deployment**
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-development-services.yml
```
**Purpose**: Development environment with hot reload and development workflow
**Components**: Vite dev server on VM1 (172.16.168.21:5173) with live reload
**Use Case**: Daily development work with automatic code refresh

### 3. **Health Check and Validation**
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/health-check.yml
```
**Purpose**: Comprehensive system health validation across all 5 VMs
**Checks**: System resources, network connectivity, service health, security status
**Output**: Detailed health report with integration test results

### 4. **Infrastructure Components**

#### Base System Setup
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-base.yml
```
**Purpose**: Ubuntu base system, security, users, networking setup

#### Database Infrastructure
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-database.yml
```
**Purpose**: Redis Stack, data persistence, model storage on VM3 (172.16.168.23)

#### Data Migration
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/data-migration.yml
```
**Purpose**: Migrate data from Docker containers to VM infrastructure

#### Hybrid Docker Deployment
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-hybrid-docker.yml
```
**Purpose**: Mixed VM + Docker container deployment

#### Native Services
```bash
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/deploy-native-services.yml
```
**Purpose**: Services running directly on VMs without containers

## VM Infrastructure Mapping

| VM | IP Address | Role | Ansible Group | Primary Services |
|---|---|---|---|---|
| VM1 | 172.16.168.21 | Frontend | `frontend` | nginx, Vue.js, development server |
| VM2 | 172.16.168.22 | NPU Worker | `aiml` | NPU acceleration, Intel OpenVINO |
| VM3 | 172.16.168.23 | Database | `database` | Redis Stack, RedisInsight |
| VM4 | 172.16.168.24 | AI Stack | `aiml` | AI processing, backend ML |
| VM5 | 172.16.168.25 | Browser | `browser` | Playwright, VNC, desktop environment |

## Service-Specific Deployment Commands

### Frontend Deployment
```bash
# Production build and deployment
ansible frontend -i ansible/inventory/production.yml -m systemd -a "name=nginx state=restarted" -b

# Development server with hot reload
ansible frontend -i ansible/inventory/production.yml -m systemd -a "name=autobot-frontend-dev state=started enabled=yes" -b
```

### Backend Deployment
```bash
# Backend API service
ansible backend -i ansible/inventory/production.yml -m systemd -a "name=autobot-backend state=restarted enabled=yes" -b
```

### Database Management
```bash
# Redis Stack service
ansible database -i ansible/inventory/production.yml -m systemd -a "name=redis-stack-server state=restarted" -b

# Redis connectivity test
ansible database -i ansible/inventory/production.yml -m shell -a "redis-cli -h 127.0.0.1 -p 6379 ping"
```

### AI/ML Services
```bash
# AI Stack service
ansible aiml -i ansible/inventory/production.yml -m systemd -a "name=autobot-ai-stack state=restarted" -b

# NPU Worker service  
ansible aiml -i ansible/inventory/production.yml -m systemd -a "name=autobot-npu-worker state=restarted" -b
```

### Browser Automation
```bash
# VNC server
ansible browser -i ansible/inventory/production.yml -m systemd -a "name=autobot-vnc-server state=started" -b

# Playwright service
ansible browser -i ansible/inventory/production.yml -m systemd -a "name=autobot-playwright state=restarted" -b
```

## Environment-Specific Configurations

### Development Environment
- **Frontend**: Hot reload via Vite dev server (port 5173)
- **Backend**: Development mode with debugging enabled
- **Environment file**: `/opt/autobot/config/frontend-dev.env`
- **Service**: `autobot-frontend-dev.service`

### Production Environment  
- **Frontend**: Static build served by nginx
- **Backend**: Production FastAPI with optimizations
- **Environment file**: `/opt/autobot/config/production.env`
- **Services**: Standard systemd services

## Health Monitoring Commands

```bash
# Quick health check on all VMs
ansible all -i ansible/inventory/production.yml -m shell -a "systemctl is-active autobot-* | grep -v inactive || echo 'No active services'"

# System resource check
ansible all -i ansible/inventory/production.yml -m shell -a "uptime && free -h | grep Mem && df -h / | tail -1"

# Service status check
ansible all -i ansible/inventory/production.yml -m shell -a "systemctl status autobot-* --no-pager -l"

# Network connectivity test
ansible all -i ansible/inventory/production.yml -m shell -a "ping -c 3 172.16.168.20 && curl -s https://172.16.168.20:8443/api/health || echo 'Connection failed'"
```

## Troubleshooting Commands

```bash
# View service logs
ansible <group> -i ansible/inventory/production.yml -m shell -a "journalctl -u autobot-* --since '1 hour ago' --no-pager"

# Check firewall status
ansible all -i ansible/inventory/production.yml -m shell -a "ufw status"

# Check port availability
ansible <group> -i ansible/inventory/production.yml -m wait_for -a "host=127.0.0.1 port=<port> timeout=5"

# Process monitoring
ansible all -i ansible/inventory/production.yml -m shell -a "ps aux --sort=-%cpu | head -10"
```

## Inventory Management

### Main Inventory File
- **Location**: `ansible/inventory/production.yml`
- **Groups**: `frontend`, `backend`, `database`, `aiml`, `browser`

### Group Variables
- **Global**: `ansible/inventory/group_vars/all.yml`
- **Frontend**: `ansible/inventory/group_vars/frontend.yml`
- **Backend**: `ansible/inventory/group_vars/backend.yml`
- **Database**: `ansible/inventory/group_vars/database.yml`
- **AI/ML**: `ansible/inventory/group_vars/aiml.yml`
- **Browser**: `ansible/inventory/group_vars/browser.yml`

## Security and Access

### SSH Key Requirements
- **Key Location**: `~/.ssh/autobot_key`
- **Authentication**: Key-based only (no passwords)
- **User**: `autobot` on all VMs

### Firewall Configuration
```bash
# Configure firewall rules
ansible all -i ansible/inventory/production.yml -m ufw -a "rule=allow port=<port> proto=tcp" -b
```

## Integration with run_autobot.sh

The main startup script integrates with Ansible:

```bash
# Development mode with Ansible-managed frontend
bash run_autobot.sh --dev

# Production deployment
bash run_autobot.sh --prod

# Health check via Ansible
bash run_autobot.sh --health-check
```

## Best Practices

1. **Always use inventory file**: `-i ansible/inventory/production.yml`
2. **Use become flag for system operations**: `-b`
3. **Test with dry run first**: `--check --diff`
4. **Monitor deployment logs**: Check systemd journals after deployment
5. **Validate with health check**: Run health-check.yml after major changes
6. **Use tags for selective deployment**: `--tags frontend,backend`

## Emergency Recovery

```bash
# Emergency stop all services
ansible all -i ansible/inventory/production.yml -m systemd -a "name=autobot-* state=stopped" -b

# Emergency restart specific VM services  
ansible <group> -i ansible/inventory/production.yml -m systemd -a "name=autobot-* state=restarted" -b

# Emergency health validation
ansible-playbook -i ansible/inventory/production.yml ansible/playbooks/health-check.yml --tags=critical
```

---

**CRITICAL**: Always prefer Ansible automation over manual SSH commands. This ensures consistency, logging, and proper infrastructure management across all 5 VMs.
