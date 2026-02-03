# AutoBot Ansible Role Structure

## Overview

AutoBot uses a role-based Infrastructure-as-Code approach for managing its distributed VM infrastructure. This document describes the role structure, usage patterns, and deployment workflows.

## Role Structure

```
ansible/
├── inventory/
│   ├── dynamic/              # Dynamic inventory from Redis
│   │   ├── generate_inventory.py
│   │   └── README.md
│   ├── production.yml        # Static inventory (5 VMs + WSL host)
│   └── group_vars/           # Group-specific variables
├── roles/
│   ├── common/               # Base configuration (all hosts)
│   ├── frontend/             # Vue.js + nginx (VM 172.16.168.21)
│   ├── redis/                # Redis Stack (VM 172.16.168.23)
│   ├── npu_worker/           # NPU acceleration (VM 172.16.168.22)
│   ├── ai_stack/             # AI services (VM 172.16.168.24)
│   └── browser/              # Playwright + VNC (VM 172.16.168.25)
└── playbooks/
    ├── provision_host.yml    # Initial host setup
    ├── deploy_role.yml       # Deploy specific role
    ├── manage_services.yml   # Service management
    └── recover_host.yml      # Disaster recovery
```

## Roles

### Common Role

**Applied to**: All hosts

**Purpose**: Base system configuration

**Includes**:
- System packages (python3, git, curl, etc.)
- AutoBot user and directory structure
- SSH key authentication
- Firewall configuration (UFW)
- DNS configuration
- Logging setup

**Usage**:
```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=common target_host=all'
```

### Frontend Role

**Applied to**: `autobot-frontend` (172.16.168.21)

**Purpose**: Vue.js frontend deployment

**Includes**:
- Node.js 20 installation
- npm package management
- nginx reverse proxy
- systemd service for Vue.js dev server
- Firewall rules (HTTP, HTTPS, dev server)

**Usage**:
```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=frontend target_host=autobot-frontend'
```

### Redis Role

**Applied to**: `autobot-database` (172.16.168.23)

**Purpose**: Redis Stack deployment

**Includes**:
- Redis Stack server installation
- Persistence configuration
- Memory management (6GB default)
- Backup script (daily at 2:00 AM)
- RedisInsight web interface
- systemd service configuration

**Usage**:
```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=redis target_host=autobot-database'
```

### NPU Worker Role

**Applied to**: `autobot-npu` (172.16.168.22)

**Purpose**: Intel OpenVINO NPU acceleration

**Includes**:
- OpenVINO installation (via pip)
- NPU device configuration
- GPU fallback support
- systemd service for worker process
- Hardware acceleration setup

**Usage**:
```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=npu_worker target_host=autobot-npu'
```

### AI Stack Role

**Applied to**: `autobot-aiml` (172.16.168.24)

**Purpose**: AI processing services

**Includes**:
- Ollama installation and configuration
- Model storage directory
- systemd services (AI stack, Ollama)
- Model cache management

**Usage**:
```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=ai_stack target_host=autobot-aiml'
```

### Browser Role

**Applied to**: `autobot-browser` (172.16.168.25)

**Purpose**: Browser automation and VNC access

**Includes**:
- XFCE4 desktop environment
- VNC server configuration
- Playwright installation (Chromium, Firefox)
- systemd services (VNC, Playwright API)

**Usage**:
```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=browser target_host=autobot-browser'
```

## Master Playbooks

### provision_host.yml

**Purpose**: Initial setup of a new host

**Features**:
- Applies common role to all hosts
- Applies service-specific role based on host group
- Creates base configuration
- Prepares host for code deployment

**Usage**:
```bash
# Provision specific host
ansible-playbook playbooks/provision_host.yml -e 'target_host=autobot-frontend'

# Provision all hosts
ansible-playbook playbooks/provision_host.yml
```

### deploy_role.yml

**Purpose**: Deploy or update a specific role

**Features**:
- Dynamic role selection via parameter
- Can target specific host or group
- Applies only the specified role

**Usage**:
```bash
# Deploy role to specific host
ansible-playbook playbooks/deploy_role.yml -e 'role_name=frontend target_host=autobot-frontend'

# Deploy role to all hosts in group
ansible-playbook playbooks/deploy_role.yml -e 'role_name=common target_host=all'
```

### manage_services.yml

**Purpose**: Start, stop, restart, or check AutoBot services

**Features**:
- Service lifecycle management
- Supports all AutoBot services
- Status checking

**Usage**:
```bash
# Start services
ansible-playbook playbooks/manage_services.yml -e 'target_host=autobot-frontend action=start'

# Restart services
ansible-playbook playbooks/manage_services.yml -e 'target_host=all action=restart'

# Check status
ansible-playbook playbooks/manage_services.yml -e 'target_host=autobot-frontend action=status'
```

### recover_host.yml

**Purpose**: Disaster recovery - reinstall and reconfigure host

**Features**:
- Backs up existing configuration
- Stops all services
- Cleans existing installation
- Reapplies all roles

**Usage**:
```bash
ansible-playbook playbooks/recover_host.yml -e 'target_host=autobot-frontend'
```

**⚠️ WARNING**: This is destructive. Configuration is backed up to `/var/backups/autobot-recovery/`

## Dynamic Inventory

The dynamic inventory generator reads host information from the Redis service registry.

**Location**: `inventory/dynamic/generate_inventory.py`

**Usage**:
```bash
# List all hosts
python inventory/dynamic/generate_inventory.py --list

# Get host variables
python inventory/dynamic/generate_inventory.py --host autobot-frontend

# Use with Ansible
ansible-playbook -i inventory/dynamic/generate_inventory.py playbook.yml
```

**Configuration**:
```bash
export REDIS_HOST=172.16.168.23
export REDIS_PORT=6379
```

See `inventory/dynamic/README.md` for detailed documentation.

## Deployment Workflow

### 1. Initial Host Provisioning

```bash
# Step 1: Provision host with roles
ansible-playbook playbooks/provision_host.yml -e 'target_host=autobot-frontend'

# Step 2: Sync application code
./scripts/utilities/sync-to-vm.sh frontend

# Step 3: Start services
ansible-playbook playbooks/manage_services.yml -e 'target_host=autobot-frontend action=start'

# Step 4: Verify health
ansible-playbook playbooks/health-check.yml -e 'target_host=autobot-frontend'
```

### 2. Update Specific Role

```bash
# Step 1: Deploy role update
ansible-playbook playbooks/deploy_role.yml -e 'role_name=redis target_host=autobot-database'

# Step 2: Restart affected services
ansible-playbook playbooks/manage_services.yml -e 'target_host=autobot-database action=restart'
```

### 3. Full Infrastructure Deployment

```bash
# Deploy all roles to all hosts
ansible-playbook playbooks/provision_host.yml

# Start all services
ansible-playbook playbooks/manage_services.yml -e 'target_host=all action=start'
```

## Role Development

### Creating a New Role

```bash
# Create role structure
mkdir -p ansible/roles/my_role/{tasks,handlers,templates,files,vars,defaults,meta}

# Create main task file
touch ansible/roles/my_role/tasks/main.yml
```

### Role Structure

```
my_role/
├── tasks/         # Main task list
│   └── main.yml
├── handlers/      # Event handlers
│   └── main.yml
├── templates/     # Jinja2 templates (.j2)
├── files/         # Static files
├── vars/          # Role variables (high precedence)
│   └── main.yml
├── defaults/      # Default variables (low precedence)
│   └── main.yml
└── meta/          # Role metadata and dependencies
    └── main.yml
```

### Best Practices

1. **Use tags**: Tag tasks for selective execution
2. **Use handlers**: For service restarts and reloads
3. **Use templates**: For configuration files with variables
4. **Use vars**: For role-specific configuration
5. **Use defaults**: For overridable default values
6. **Use meta**: For role dependencies

## Testing

### Test Role on Single Host

```bash
ansible-playbook playbooks/deploy_role.yml \
  -e 'role_name=frontend target_host=autobot-frontend' \
  --check \
  --diff
```

### Dry Run (Check Mode)

```bash
ansible-playbook playbooks/provision_host.yml \
  -e 'target_host=autobot-frontend' \
  --check
```

### Verbose Output

```bash
ansible-playbook playbooks/deploy_role.yml \
  -e 'role_name=common target_host=all' \
  -vvv
```

## Troubleshooting

### Check Ansible Connectivity

```bash
ansible all -m ping -i inventory/production.yml
```

### Check Host Variables

```bash
ansible-inventory -i inventory/production.yml --host autobot-frontend
```

### Check Group Membership

```bash
ansible-inventory -i inventory/production.yml --list
```

### View Playbook Tasks

```bash
ansible-playbook playbooks/provision_host.yml --list-tasks
```

### View Role Tasks

```bash
ansible-playbook playbooks/deploy_role.yml -e 'role_name=frontend' --list-tasks
```

## Integration with AutoBot

The Ansible role structure integrates with AutoBot's deployment workflows:

1. **setup.sh**: Installs Ansible and dependencies
2. **run_autobot.sh**: Can trigger Ansible deployments
3. **sync-to-vm.sh**: Syncs code after role deployment
4. **Service Registry**: Feeds dynamic inventory

## Environment Variables

```bash
# Ansible configuration
export ANSIBLE_CONFIG=ansible/ansible.cfg
export ANSIBLE_INVENTORY=ansible/inventory/production.yml

# Redis connection (for dynamic inventory)
export REDIS_HOST=172.16.168.23
export REDIS_PORT=6379

# SSH key
export ANSIBLE_PRIVATE_KEY_FILE=~/.ssh/autobot_key
```

## Additional Resources

- **Ansible Documentation**: https://docs.ansible.com/
- **AutoBot Setup Guide**: `docs/developer/PHASE_5_DEVELOPER_SETUP.md`
- **API Documentation**: `docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`
- **System State**: `docs/system-state.md`

## Support

For issues or questions:
1. Check `docs/troubleshooting/`
2. Review Ansible logs: `ansible-playbook ... -vvv`
3. Check service logs: `journalctl -u autobot-*`
