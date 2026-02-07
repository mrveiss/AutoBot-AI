# Layer Separation - Files Marked for Deletion

**Related Issue:** #729 - Migrate admin functionality from main frontend/backend to SLM

This document tracks backend files that have been marked for deletion as part of the AutoBot/SLM layer separation. These files have been disabled but not yet deleted to allow for phased migration.

## Deleted (Task 1.1 - Completed)

- [x] `backend/services/slm/` (entire directory)
  - `deployment_orchestrator.py`
  - `reconciler.py`
  - `remediator.py`
  - `stateful_manager.py`
  - `db_service.py`
  - `state_machine.py`
  - `__init__.py`

## Marked for Deletion (Next Tasks)

### autobot-user-backend/api/slm/ (Entire Directory)
All files in this directory are non-functional after `backend/services/slm/` removal.
SLM server (172.16.168.19) provides equivalent functionality.

- [ ] `autobot-user-backend/api/slm/stateful.py` - See `slm-server/api/stateful.py`
- [ ] `autobot-user-backend/api/slm/nodes.py` - See `slm-server/api/nodes.py`
- [ ] `autobot-user-backend/api/slm/deployments.py` - See `slm-server/api/deployments.py`
- [ ] `autobot-user-backend/api/slm/heartbeats.py` - See `slm-server/api/nodes.py` (heartbeat endpoints)
- [ ] `autobot-user-backend/api/slm/websockets.py` - See `slm-server/api/websocket.py`
- [ ] `autobot-user-backend/api/slm/__init__.py` - Package file (delete with directory)

### Supporting Files to Update
- [ ] `backend/initialization/router_registry/core_routers.py` - Remove SLM router imports entirely
- [ ] `backend/initialization/lifespan.py` - Remove `_init_slm_reconciler()` function entirely

## Migration Status

| Component | Backend Status | SLM Server Status | Action |
|-----------|---------------|-------------------|---------|
| Node Management | Disabled | ✅ Active | Delete autobot-user-backend/api/slm/nodes.py |
| Deployments | Disabled | ✅ Active | Delete autobot-user-backend/api/slm/deployments.py |
| Heartbeats | Disabled | ✅ Active | Delete autobot-user-backend/api/slm/heartbeats.py |
| Stateful Services | Disabled | ✅ Active | Delete autobot-user-backend/api/slm/stateful.py |
| WebSockets | Disabled | ✅ Active | Delete autobot-user-backend/api/slm/websockets.py |
| Reconciler | Disabled | ✅ Active | Remove from lifespan.py |

## Verification Checklist

Before deleting the remaining files, verify:
- [ ] SLM server (172.16.168.19) is operational
- [ ] All SLM endpoints accessible via SLM server
- [ ] No frontend components calling backend SLM endpoints
- [ ] No other backend services depending on these files
- [ ] All references updated to use SLM server API

## Notes

The backend's SLM endpoints have been disabled by:
1. Deleting `backend/services/slm/` directory (Task 1.1)
2. Commenting out imports in `autobot-user-backend/api/slm/` files
3. Commenting out router registrations in `core_routers.py`
4. Disabling reconciler initialization in `lifespan.py`

Next step: Delete `autobot-user-backend/api/slm/` directory entirely and clean up supporting files.
