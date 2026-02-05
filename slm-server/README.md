# SLM Server

> **Deployment Target: 172.16.168.19 (SLM Machine)**

System Lifecycle Manager backend - manages fleet nodes, code distribution, and system orchestration.

## This is NOT the main AutoBot backend

- **This code** (`slm-server/`) runs on the SLM machine (172.16.168.19)
- **Main AutoBot** (`src/`) runs on the main machine (172.16.168.20)

## Key Components

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI endpoints for fleet management |
| `models/` | SQLAlchemy models (Node, Role, CodeSource, etc.) |
| `services/` | Business logic (sync orchestrator, database) |
| `migrations/` | Database schema migrations |

## Sync to SLM Machine

```bash
# From /home/kali/Desktop/AutoBot/
./scripts/utilities/sync-to-vm.sh slm slm-server/ /home/autobot/slm-server/
```

## Related

- Frontend: `slm-admin/` (deploys to 172.16.168.21)
- Design docs: `docs/plans/2026-02-03-role-based-code-sync-design.md`
