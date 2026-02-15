# AutoBot Infrastructure

Development and operations tooling - not deployed as application code.

## Directory Structure

The infrastructure folder uses a **per-role organization** where each deployable component has its own infrastructure subdirectory.

```text
infrastructure/
├── autobot-user-backend/       # User backend infrastructure
│   ├── docker/                 # Docker configurations
│   ├── tests/                  # Component-specific tests
│   ├── config/                 # Configuration files
│   ├── scripts/                # Deployment scripts
│   └── templates/              # Service templates
│
├── autobot-user-frontend/      # User frontend infrastructure
│   ├── docker/
│   ├── tests/
│   ├── config/
│   ├── scripts/
│   └── templates/
│
├── autobot-slm-backend/        # SLM backend infrastructure
│   ├── docker/
│   ├── tests/
│   ├── config/
│   ├── scripts/
│   │   └── bootstrap-slm.sh    # SLM deployment script
│   └── templates/
│       ├── autobot-slm-backend.service
│       ├── backend-start.sh
│       ├── backend-stop.sh
│       └── backend-status.sh
│
├── autobot-slm-frontend/       # SLM frontend infrastructure
│   ├── docker/
│   ├── tests/
│   ├── config/
│   ├── scripts/
│   └── templates/
│       ├── autobot-slm.conf    # nginx configuration
│       ├── frontend-start.sh
│       ├── frontend-stop.sh
│       └── frontend-status.sh
│
├── autobot-npu-worker/         # NPU worker infrastructure
│   ├── docker/
│   ├── tests/
│   ├── config/
│   ├── scripts/
│   └── templates/
│
├── autobot-browser-worker/     # Browser worker infrastructure
│   ├── docker/
│   ├── tests/
│   ├── config/
│   ├── scripts/
│   └── templates/
│
└── shared/                     # Shared infrastructure resources
    ├── scripts/                # Common utility scripts
    │   └── sync-to-vm.sh       # Sync code to VMs
    ├── certs/                  # Certificate management
    ├── config/                 # Shared configurations
    ├── docker/                 # Shared docker resources
    ├── mcp/                    # MCP servers and tools
    ├── novnc/                  # VNC server
    ├── tools/                  # Development tools
    ├── tests/                  # Shared test utilities
    └── analysis/               # Code analysis tools
```

## Component-Specific Infrastructure

Each `autobot-*` directory contains infrastructure specific to that component:

| Directory | Component | Deploys To |
|-----------|-----------|------------|
| `autobot-user-backend/` | Main backend | 172.16.168.20 |
| `autobot-user-frontend/` | Main frontend | 172.16.168.20 |
| `autobot-slm-backend/` | SLM backend | 172.16.168.19 |
| `autobot-slm-frontend/` | SLM frontend | 172.16.168.21 |
| `autobot-npu-worker/` | NPU worker | 172.16.168.22 |
| `autobot-browser-worker/` | Browser worker | 172.16.168.25 |

## Shared Resources

The `shared/` directory contains resources used across multiple components:

| Directory | Purpose |
|-----------|---------|
| `scripts/` | Common utility and sync scripts |
| `certs/` | SSL certificates and CA management |
| `config/` | Shared environment configurations |
| `docker/` | Shared Docker resources |
| `mcp/` | MCP servers and tools |
| `novnc/` | VNC server configuration |
| `tools/` | Development and IDE tools |
| `tests/` | Shared test utilities |
| `analysis/` | Code analysis tools and reports |

## Deployment Methods

### Ansible (Recommended for Production)

```bash
cd autobot-slm-backend/ansible

# Full fleet deployment
ansible-playbook playbooks/deploy-full.yml

# Service control (start/stop/restart)
ansible-playbook playbooks/slm-service-control.yml -e "service=autobot-backend action=restart"

# Deploy specific roles
ansible-playbook playbooks/deploy-full.yml --tags frontend,backend
```

**Available Ansible Roles:** 23 roles covering all infrastructure needs (centralized_logging, agent_config, distributed_setup, dns, monitoring, etc.)

### Shell Scripts (Development/Manual Operations)

**Sync to VMs:**

```bash
# Sync component to its target VM
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/
./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-backend/
./infrastructure/shared/scripts/sync-to-vm.sh npu autobot-npu-worker/
./infrastructure/shared/scripts/sync-to-vm.sh browser autobot-browser-worker/
```

**SLM Bootstrap:**

```bash
# Deploy complete SLM stack to target node
./infrastructure/autobot-slm-backend/scripts/bootstrap-slm.sh -u root -h 172.16.168.19
```

## Usage Pattern

1. Component code lives in `autobot-*/` directories at repo root
2. Infrastructure for each component lives in `infrastructure/autobot-*/`
3. Shared tools and scripts live in `infrastructure/shared/`
4. Deploy using sync scripts or component-specific deployment scripts
