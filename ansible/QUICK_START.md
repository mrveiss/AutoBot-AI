# AutoBot Ansible Quick Start Guide

## 🚀 Quick Commands

### Provision New Host

```bash
# Single host
ansible-playbook ansible/playbooks/provision_host.yml -e 'target_host=autobot-frontend'

# All hosts
ansible-playbook ansible/playbooks/provision_host.yml
```

### Deploy Specific Role

```bash
# Common role (all hosts)
ansible-playbook ansible/playbooks/deploy_role.yml -e 'role_name=common target_host=all'

# Frontend role
ansible-playbook ansible/playbooks/deploy_role.yml -e 'role_name=frontend target_host=autobot-frontend'

# Redis role
ansible-playbook ansible/playbooks/deploy_role.yml -e 'role_name=redis target_host=autobot-database'
```

### Manage Services

```bash
# Start services
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=autobot-frontend action=start'

# Restart services
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=all action=restart'

# Stop services
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=autobot-database action=stop'

# Check status
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=autobot-frontend action=status'
```

### Health Check

```bash
# Single host
ansible-playbook ansible/playbooks/health-check.yml -e 'target_host=autobot-frontend'

# All hosts
ansible-playbook ansible/playbooks/health-check.yml
```

### Disaster Recovery

```bash
ansible-playbook ansible/playbooks/recover_host.yml -e 'target_host=autobot-frontend'
```

## 📋 Host → Role Mapping

| Host | IP | Role | Services |
|------|-----|------|----------|
| `autobot-frontend` | 172.16.168.21 | frontend | nginx, Vue.js dev server |
| `autobot-npu` | 172.16.168.22 | npu_worker | OpenVINO, NPU acceleration |
| `autobot-database` | 172.16.168.23 | redis | Redis Stack, RedisInsight |
| `autobot-aiml` | 172.16.168.24 | ai_stack | AI services, Ollama |
| `autobot-browser` | 172.16.168.25 | browser | Playwright, VNC, XFCE4 |

## 🔄 Typical Workflow

### 1. First-Time Setup

```bash
# Step 1: Provision host
ansible-playbook ansible/playbooks/provision_host.yml -e 'target_host=autobot-frontend'

# Step 2: Sync code
./scripts/utilities/sync-to-vm.sh frontend

# Step 3: Start services
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=autobot-frontend action=start'

# Step 4: Verify
ansible-playbook ansible/playbooks/health-check.yml -e 'target_host=autobot-frontend'
```

### 2. Update Configuration

```bash
# Step 1: Update role
ansible-playbook ansible/playbooks/deploy_role.yml -e 'role_name=redis target_host=autobot-database'

# Step 2: Restart service
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=autobot-database action=restart'
```

### 3. Deploy Code Changes

```bash
# Step 1: Sync code (LOCAL editing only!)
./scripts/utilities/sync-to-vm.sh frontend

# Step 2: Restart service
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=autobot-frontend action=restart'
```

## 🧪 Testing

### Dry Run (Check Mode)

```bash
ansible-playbook ansible/playbooks/provision_host.yml \
  -e 'target_host=autobot-frontend' \
  --check \
  --diff
```

### Verbose Output

```bash
ansible-playbook ansible/playbooks/deploy_role.yml \
  -e 'role_name=common target_host=all' \
  -vvv
```

## 📊 Dynamic Inventory

```bash
# List all hosts from Redis
python ansible/inventory/dynamic/generate_inventory.py --list

# Get specific host vars
python ansible/inventory/dynamic/generate_inventory.py --host autobot-frontend

# Use dynamic inventory
ansible-playbook -i ansible/inventory/dynamic/generate_inventory.py ansible/playbooks/health-check.yml
```

## 🔧 Available Roles

- **common**: Base system configuration (all hosts)
- **frontend**: Vue.js + nginx deployment
- **redis**: Redis Stack database
- **npu_worker**: Intel OpenVINO NPU acceleration
- **ai_stack**: AI processing services
- **browser**: Playwright + VNC + desktop

## 📚 Documentation

- **Comprehensive Guide**: `ansible/ROLE_STRUCTURE_README.md`
- **Dynamic Inventory**: `ansible/inventory/dynamic/README.md`
- **Existing Playbooks**: `ansible/playbooks/`
- **Developer Setup**: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`

## 🆘 Troubleshooting

### Check Connectivity

```bash
ansible all -m ping -i ansible/inventory/production.yml
```

### View Host Variables

```bash
ansible-inventory -i ansible/inventory/production.yml --host autobot-frontend
```

### Check Service Status

```bash
ansible autobot-frontend -m systemd -a "name=autobot-frontend state=started" -i ansible/inventory/production.yml
```

### View Service Logs

```bash
ansible autobot-frontend -m shell -a "journalctl -u autobot-frontend -n 50" -i ansible/inventory/production.yml
```

## ⚠️ Important Notes

1. **NEVER edit code on remote VMs** - Always edit locally and sync
2. **Common role first** - Apply common role before service-specific roles
3. **Code sync required** - Services need code synced before starting
4. **SSH keys** - Ensure `~/.ssh/autobot_key` is configured
5. **Redis** - Dynamic inventory requires Redis at 172.16.168.23:6379

## 🎯 Quick Reference

```bash
# Full deployment
ansible-playbook ansible/playbooks/provision_host.yml && \
./scripts/utilities/sync-to-vm.sh all && \
ansible-playbook ansible/playbooks/manage_services.yml -e 'action=start'

# Role update
ansible-playbook ansible/playbooks/deploy_role.yml -e 'role_name=<role> target_host=<host>' && \
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=<host> action=restart'

# Emergency recovery
ansible-playbook ansible/playbooks/recover_host.yml -e 'target_host=<host>' && \
./scripts/utilities/sync-to-vm.sh <service> && \
ansible-playbook ansible/playbooks/manage_services.yml -e 'target_host=<host> action=start'
```
