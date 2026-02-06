# AutoBot Infrastructure

Development and operations tooling - not deployed as application code.

## Contents

| Directory | Purpose |
|-----------|---------|
| `docker/` | Dockerfiles and compose files |
| `scripts/` | Utility and deployment scripts |
| `config/` | Environment configurations |
| `certs/` | SSL certificates |
| `tests/` | Test suites |
| `mcp/` | MCP servers and tools |
| `novnc/` | VNC server |
| `analysis/` | Code analysis tools and reports |

## Key Scripts

- `scripts/utilities/sync-to-vm.sh` - Sync code to VMs
- `scripts/startup/` - Service startup scripts
- `scripts/deployment/` - Deployment automation
