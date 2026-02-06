# AutoBot SLM Backend

> **Deploys to:** 172.16.168.19 (SLM Server)

System Lifecycle Manager backend - manages fleet nodes, code distribution, and system orchestration.

## This is NOT the main AutoBot backend

- **This code** (`autobot-slm-backend/`) runs on the SLM machine (172.16.168.19)
- **Main AutoBot** (`autobot-core/`) runs on the main machine (172.16.168.20)

## Key Components

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI endpoints for fleet management |
| `models/` | SQLAlchemy models (Node, Role, CodeSource, etc.) |
| `services/` | Business logic (sync orchestrator, database) |
| `migrations/` | Database schema migrations |
| `ansible/` | Deployment playbooks and roles |

## Sync to SLM Machine

```bash
# From /home/kali/Desktop/AutoBot/
./scripts/utilities/sync-to-vm.sh slm autobot-slm-backend/ /home/autobot/slm-server/
```

## Related

- Frontend: `autobot-slm-admin/` (deploys to 172.16.168.21)
- Design docs: `docs/plans/2026-02-03-role-based-code-sync-design.md`
