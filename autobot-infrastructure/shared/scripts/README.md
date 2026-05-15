# AutoBot Scripts Organization

## Directory Structure

```
scripts/
├── analysis/         # Test scripts and analysis tools (moved from root)
├── archive/          # Obsolete startup scripts (deprecated, see SERVICE_MANAGEMENT.md)
├── cache/            # Cache management utilities
├── native-vm/        # Native VM deployment scripts
├── network/          # Network configuration and testing
├── setup/            # All setup scripts organized by category
│   ├── analytics/    # Seq analytics setup
│   ├── docker/       # Docker configuration setup
│   ├── environment/  # Environment setup
│   ├── knowledge/    # Knowledge base setup
│   ├── models/       # Model sharing setup
│   └── system/       # System deployment and configuration
├── testing/          # Test scripts and demos
└── utilities/        # General utility scripts
```

## Main Scripts (Root Directory)

### Essential Scripts
- **`setup.sh`** - Unified setup script (handles all setup tasks)
- **`scripts/start-services.sh`** - CLI service wrapper (start/stop/restart)

## Script Categories

### Archive (Obsolete - Do not use)
- `run_autobot.sh` - Deprecated (Issue #863), moved to `legacy/`
- `run_agent.sh` - Old Docker-based startup
- `run_agent_unified.sh` - Old unified startup
- `run_agent_native.sh` - Old native VM startup
- `run-autodetect.sh` - Old auto-detection startup
- `run-docker-desktop.sh` - Old Docker Desktop specific
- `run-wsl-docker.sh` - Old WSL Docker specific

### Cache Management
- `clear-all-caches.sh` - Clear all system caches
- `clear-backend-cache.sh` - Clear backend cache only
- `clear-system-cache.sh` - Clear system cache

### Native VM Scripts
- `start_autobot_native.sh` - Start native VM deployment
- `stop_autobot_native.sh` - Stop native VM deployment
- `status_autobot_native.sh` - Check status of VMs
- `validate_native_deployment.sh` - Validate deployment health

### Network Scripts
- `bidirectional-dns-setup.sh` - DNS configuration
- `docker-network-dns.sh` - Docker network DNS
- `network-health-monitor.sh` - Monitor network health
- `test-dns-resolution.sh` - Test DNS resolution
- And more...

### Testing Scripts
- `debug_demo.sh` - Debug demonstration
- `test_desktop_setup.sh` - Test desktop configuration
- `test_heroicons_comprehensive.sh` - Test heroicons

### Utilities
- `build-frontend-host.sh` - Build frontend on host
- `detect-environment.sh` - Environment detection
- `start-isolated-vnc.sh` - Start VNC in isolation
- And more...

## Usage Examples

### Starting Services (Recommended)
```bash
# Production (systemd)
sudo systemctl start autobot-backend

# CLI wrapper
scripts/start-services.sh start

# Docker
docker compose up -d
```

### Setup Commands
```bash
# Complete initial setup (all components)
./setup.sh

# Setup specific components
./setup.sh knowledge      # Knowledge base only
./setup.sh docker         # Docker configuration
./setup.sh agent          # Agent environment only
./setup.sh system         # System configuration

# Setup with options
./setup.sh initial --native-vm  # Native VM deployment (default)
./setup.sh initial --docker     # Docker deployment
./setup.sh knowledge --force    # Force re-setup
```

### Quick Native VM Commands
```bash
# Start native VMs
./scripts/native-vm/start_autobot_native.sh

# Check status  
./scripts/native-vm/status_autobot_native.sh

# Stop native VMs
./scripts/native-vm/stop_autobot_native.sh
```

### Maintenance
```bash
# Clear all caches
./scripts/cache/clear-all-caches.sh

# Test network health
./scripts/network/network-health-monitor.sh
```

## Migration Notes

All old startup scripts (including `run_autobot.sh`) have been deprecated.
Use the current methods:
- **Production:** `systemctl start autobot-backend`
- **CLI wrapper:** `scripts/start-services.sh start`
- **Docker:** `docker compose up -d`

See [`docs/developer/SERVICE_MANAGEMENT.md`](../../docs/developer/SERVICE_MANAGEMENT.md) for full details.

The old scripts are preserved in `scripts/archive/` for reference but should not be used.
