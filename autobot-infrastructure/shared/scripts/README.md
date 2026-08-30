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

### Manual operator tools

Reached for by hand when something has gone wrong. Nothing in CI or the deployment path calls
these, and that is deliberate — but each is maintained, each runs against the current tree, and
each is listed here so an operator can find it (#15127).

- `cleanup-disk-space.sh` — reclaim disk: caches, `__pycache__`, old logs and backups.
  Supports `--dry-run`; resolves the repo root from its own location, so it is safe to run from
  anywhere.
  ```bash
  bash autobot-infrastructure/shared/scripts/cleanup-disk-space.sh --dry-run
  ```
- `monitor_testing.sh` — colour-coded live tail of `logs/backend.log` filtered to PTY execution,
  approval requests, session lifecycle and errors. The manual equivalent
  (`tail -f logs/backend.log | grep …`) appears throughout the developer docs; this is that, with
  the markers already selected.
  ```bash
  bash autobot-infrastructure/shared/scripts/monitor_testing.sh
  ```
- `network/fix-wsl-networking.sh` — diagnose and repair WSL2 port forwarding between frontend and
  backend. See [`docs/developer/WSL2_NETWORKING.md`](../../../docs/developer/WSL2_NETWORKING.md)
  for the failure mode it addresses.
- `install-doc-sync-hook.sh` — install the `post-commit-doc-sync` git hook into this checkout, so
  documentation edits reindex the knowledge base on commit. Run once per clone.
  ```bash
  bash autobot-infrastructure/shared/scripts/install-doc-sync-hook.sh
  ```
- `utilities/start-seq-forwarder.sh` — tail local logs into a running Seq instance at
  `localhost:5341`. Requires `aiohttp` in the interpreter you run it with; it will not install
  anything for you.
  ```bash
  bash autobot-infrastructure/shared/scripts/utilities/start-seq-forwarder.sh
  ```
- `backup_ollama_models.sh` — copy a developer workstation's `~/.ollama/models` (plus an
  `ollama list` manifest) to a timestamped directory before switching that machine to the shared
  model configuration. The Ansible `backup-node-data.yml` play covers the *deployed* model
  directory on a node; this covers the workstation copy, which nothing else does. It prints the
  restore commands when it finishes.
  ```bash
  bash autobot-infrastructure/shared/scripts/backup_ollama_models.sh
  ```
- `utilities/security-audit.sh` — repository hygiene sweep: tracked key/credential file patterns,
  obvious hardcoded secrets, the `.gitignore` patterns that must be present, SSH key permissions,
  and whether `.env` is tracked. Exits non-zero with the finding count. Run it from the repository
  root; it reads the working tree it is run in.
  ```bash
  bash autobot-infrastructure/shared/scripts/utilities/security-audit.sh
  ```
- `build_secure_sandbox.sh` — build `autobot/secure-sandbox:latest`, the hardened image
  `secure_sandbox_executor.py` runs code-execution containers from. This is the only builder of
  that image, and `tests/integration/test_codeexec_docker_smoke.py` — the gate for
  `AUTOBOT_CODEEXEC_ENABLED` — self-skips until it exists locally. Fails closed: it will not
  substitute an unhardened image under that tag.
  ```bash
  bash autobot-infrastructure/shared/scripts/build_secure_sandbox.sh
  ```
- `debug_chat_system.sh` — run the whole of Scenario 3 in
  [`docs/development/MCP_DEBUG_SCENARIOS.md`](../../../docs/development/MCP_DEBUG_SCENARIOS.md)
  ("chat messages not sending") in one pass and print recommendations. Needs `node`, `jq` and the
  MCP servers that document lists.
  ```bash
  bash autobot-infrastructure/shared/scripts/debug_chat_system.sh
  ```
- `cleanup-legacy-python.sh` — one-time-per-machine removal of stale `pyenv`/`conda`/`miniconda`/
  `anaconda3` installs left over from the pre-#1898 toolchain, plus the shell-rc blocks that
  activated them. Refuses to touch anything unless `python3.14` (the deadsnakes-PPA standard,
  #1898) is already on `PATH`. The migration itself landed repo-wide (#1924); this stays as the
  cleanup a developer or VM still carrying the old install reaches for by hand.
  ```bash
  bash autobot-infrastructure/shared/scripts/cleanup-legacy-python.sh
  ```
- `utilities/enable-phase4-enterprise.sh` — drive the `/api/enterprise/*` admin API
  (`autobot-backend/api/enterprise_features.py`, Issue #620) end to end: enable every registered
  feature, run the bulk-enable path, and print the Phase 4 completion validation. Requires
  `AUTOBOT_INTERNAL_API_KEY` in the environment — every route on that router is admin-gated, and
  this is the same trusted-service header `autobot-slm-backend/api/voice_proxy.py` sends, not a
  new credential path. See
  [`docs/prd/enterprise-features-subsystems-PRD.md`](../../../docs/prd/enterprise-features-subsystems-PRD.md)
  before relying on the numbers it prints: most `enable_feature()` paths are logger-only stubs
  today, so a "success" here reflects the status enum flipping, not a verified capability.
  ```bash
  AUTOBOT_INTERNAL_API_KEY=... bash autobot-infrastructure/shared/scripts/utilities/enable-phase4-enterprise.sh
  ```

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
