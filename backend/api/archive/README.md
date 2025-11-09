# Terminal API Archive

**Date Archived**: 2025-01-09
**Reason**: Terminal consolidation - Phase 2

This directory contains archived terminal API implementations that have been superseded by the consolidated terminal system.

---

## Archived Files

### 1. `base_terminal.py.unused`

**Status**: ❌ Unused - Features migrated to `terminal.py`

**Original Purpose**: Abstract base class for terminal implementations with health/status endpoints

**Why Archived**:
- All unique features migrated to consolidated `terminal.py` in Phase 1
- Abstract base class pattern no longer needed
- Endpoints now available in `terminal.py`:
  - `GET /api/terminal/health`
  - `GET /api/terminal/status`
  - `GET /api/terminal/capabilities`
  - `GET /api/terminal/security`
  - `GET /api/terminal/features`
  - `GET /api/terminal/stats`

**Migrated Features**:
- ✅ Health check endpoints
- ✅ System status endpoints
- ✅ Terminal statistics method
- ✅ Security policies documentation

**Re-enablement**: Not recommended - use `terminal.py` instead

---

### 2. `remote_terminal.py.feature`

**Status**: 🚧 Future Feature - Complete but not exposed in UI

**Original Purpose**: SSH multi-host terminal with connection pooling

**Why Archived**:
- Feature is complete and functional
- No Vue components in UI to use it yet
- Not currently needed by any active workflows

**Features Available**:
- SSH connection management across multiple hosts
- Batch command execution on multiple hosts in parallel
- Host discovery and management
- Remote security validation
- Connection pool statistics
- Activity tracking per remote session

**Re-enablement Steps**:

1. **Move file back**:
   ```bash
   mv backend/api/archive/remote_terminal.py.feature backend/api/remote_terminal.py
   ```

2. **Enable router in `backend/app_factory.py`**:
   - Router is already registered as optional
   - Restart backend to activate `/api/remote-terminal/*` endpoints

3. **Create Vue component**:
   ```vue
   <!-- autobot-vue/src/components/RemoteTerminal.vue -->
   <template>
     <div class="remote-terminal">
       <!-- SSH host selector -->
       <!-- Terminal interface per host -->
       <!-- Batch command interface -->
     </div>
   </template>
   ```

4. **API Endpoints Available**:
   - `POST /api/remote-terminal/sessions` - Create SSH session
   - `GET /api/remote-terminal/hosts` - List configured hosts
   - `POST /api/remote-terminal/execute` - Execute command on host(s)
   - `POST /api/remote-terminal/batch` - Execute on multiple hosts
   - `GET /api/remote-terminal/health` - Check all hosts health
   - `GET /api/remote-terminal/pool-stats` - Connection pool statistics

5. **Configuration Required**:
   - SSH host configuration in `~/.ssh/config`
   - SSH key authentication setup
   - Network connectivity to target hosts

6. **Testing**:
   - Un-skip batch 156 tests in `tests/unit/test_api_endpoint_migrations.py`
   - Run tests: `python3 -m pytest tests/unit/test_api_endpoint_migrations.py::TestAPIEndpointMigrations::test_batch_156_*`

**Dependencies**:
- `backend/services/ssh_manager.py` (existing)
- SSH keys configured for target hosts
- Network access to remote hosts

---

## Documentation

See also:
- `docs/architecture/TERMINAL_CONSOLIDATION_ANALYSIS.md` - Full consolidation analysis
- `docs/architecture/TERMINAL_ARCHITECTURE_DIAGRAM.md` - Architecture diagrams
- `docs/architecture/TERMINAL_APPROVAL_WORKFLOW.md` - Approval workflow documentation
- `backend/api/terminal.py` - Active consolidated terminal implementation

---

## Support

If you need to restore or re-enable any of these files, refer to the re-enablement steps above or consult the terminal consolidation documentation.
