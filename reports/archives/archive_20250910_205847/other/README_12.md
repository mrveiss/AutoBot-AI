# AutoBot Scripts Organization

## Directory Structure

```
scripts/
├── analysis/         # Test scripts and analysis tools (moved from root)
├── archive/          # Obsolete startup scripts (replaced by run_autobot.sh)
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

### Essential Scripts (ONLY 2 FILES)
- **`run_autobot.sh`** - Unified startup script (combines all previous run scripts)
- **`setup.sh`** - Unified setup script (handles all setup tasks)

## Script Categories

### Archive (Obsolete - Use run_autobot.sh instead)
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

### Using the Unified Script (Recommended)
```bash
# Standard native VM startup
./run_autobot.sh

# Development mode
./run_autobot.sh --dev

# With specific options
./run_autobot.sh --dev --no-browser --rebuild
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

All old startup scripts have been consolidated into `run_autobot.sh`. 
If you were using:
- `run_agent.sh --dev` → Now use `run_autobot.sh --dev`
- `run_agent_native.sh` → Now use `run_autobot.sh` (native is default)
- `run-docker-desktop.sh` → Now use `run_autobot.sh --docker`

The old scripts are preserved in `scripts/archive/` for reference but should not be used.