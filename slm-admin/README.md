# SLM Admin Dashboard

> **Deployment Target: 172.16.168.21 (Frontend VM)**

Vue 3 + TypeScript admin interface for the System Lifecycle Manager.

## This is NOT the main AutoBot frontend

- **This code** (`slm-admin/`) is the SLM fleet management UI
- **Main AutoBot UI** (`autobot-vue/`) is the chat interface

## Key Components

| Directory | Purpose |
|-----------|---------|
| `src/views/` | Page components (FleetOverview, CodeSyncView, etc.) |
| `src/components/` | Reusable UI components |
| `src/composables/` | Vue composables (useCodeSync, useRoles, etc.) |
| `src/config/` | SSOT configuration |

## Sync to Frontend VM

```bash
# From /home/kali/Desktop/AutoBot/
./scripts/utilities/sync-to-vm.sh frontend slm-admin/src/ /home/autobot/AutoBot/slm-admin/src/
```

## Backend

- API: `slm-server/` (runs on 172.16.168.19)
- Endpoints: `http://172.16.168.19:8000/api/`

## Development

Edit locally, then sync:

```bash
# Never run npm dev locally - always sync to VM
./scripts/utilities/sync-to-vm.sh frontend slm-admin/src/ /home/autobot/AutoBot/slm-admin/src/
```

Access at: http://172.16.168.21:5173
