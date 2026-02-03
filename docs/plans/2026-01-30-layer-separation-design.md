# Layer Separation Design: Management vs Business

**Date:** 2026-01-30
**Status:** Approved
**Author:** mrveiss

---

## Overview

Separate AutoBot into two distinct layers:
- **Management Layer (SLM)** - Infrastructure control, deployments, monitoring, fleet management
- **Business Layer (Backend)** - Application logic, chat, agents, AI/ML, user features

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MAIN MACHINE (SLM)                       │
│                                                             │
│   slm-server/ ────────── deploys directly to ──────────┐   │
│       │                                                 │   │
│       │ (SSH, Ansible, direct control)                  │   │
│       ↓                                                 ↓   │
│   ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐  ┌───────┐   │
│   │ VM1   │  │ VM2   │  │ VM3   │  │ VM4   │  │ VM5   │   │
│   │Frontend│  │ NPU   │  │ Redis │  │AI Stack│  │Browser│   │
│   └───────┘  └───────┘  └───────┘  └───────┘  └───────┘   │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                 SEPARATE: APPLICATION LAYER                  │
│                                                             │
│   backend/ ←──→ autobot-vue/ (user-facing app)              │
│      │                                                      │
│      └── uses src/ for business logic                       │
└─────────────────────────────────────────────────────────────┘
```

## Principles

1. **SLM is fully self-contained** - All infrastructure operations in slm-server
2. **Backend never SSH/Ansible directly** - No infrastructure code in backend
3. **Backend calls SLM API** - If backend needs infrastructure actions, it calls SLM

---

## Backend Migration (DELETE from backend/)

### SLM Services → slm-server/services/

| File | Action |
|------|--------|
| `backend/services/slm/deployment_orchestrator.py` | DELETE (SLM has equivalent) |
| `backend/services/slm/reconciler.py` | DELETE |
| `backend/services/slm/remediator.py` | DELETE |
| `backend/services/slm/stateful_manager.py` | DELETE |
| `backend/services/slm/db_service.py` | DELETE |
| `backend/services/slm/state_machine.py` | DELETE |
| `backend/services/slm/__init__.py` | DELETE |

### SSH/Ansible → slm-server/services/

| File | Action |
|------|--------|
| `backend/services/ansible_executor.py` | DELETE (SLM has equivalent) |
| `backend/services/ssh_connection_service.py` | DELETE |
| `backend/services/ssh_manager.py` | DELETE |
| `backend/services/ssh_connection_pool.py` | DELETE |
| `backend/services/ssh_provisioner.py` | DELETE |

### Infrastructure APIs → DELETE

| File | Action |
|------|--------|
| `backend/api/infrastructure.py` | DELETE |
| `backend/api/infrastructure_hosts.py` | DELETE |
| `backend/api/infrastructure_nodes.py` | DELETE |
| `backend/api/infrastructure_monitor.py` | DELETE |
| `backend/api/slm/*` (entire folder) | DELETE |

### Infrastructure Monitoring → slm-server/

| File | Action |
|------|--------|
| `backend/api/monitoring.py` | REVIEW - split infra vs app |
| `backend/api/monitoring_hardware.py` | DELETE → SLM |
| `backend/api/monitoring_alerts.py` | DELETE → SLM |
| `backend/api/service_monitor.py` | DELETE → SLM |
| `backend/api/phase9_monitoring.py` | DELETE (rename to monitoring in SLM) |
| `backend/services/consolidated_health_service.py` | DELETE → SLM |

### Infrastructure DB/Services → DELETE

| File | Action |
|------|--------|
| `backend/services/infrastructure_db.py` | DELETE |
| `backend/services/infrastructure_host_service.py` | DELETE |
| `backend/services/node_enrollment_service.py` | DELETE |
| `backend/tasks/deployment_tasks.py` | DELETE |
| `backend/models/infrastructure.py` | DELETE |
| `backend/schemas/infrastructure.py` | DELETE |

---

## What Stays in Backend

| Category | Examples |
|----------|----------|
| Chat/Agents | Chat API, agent orchestration, conversation |
| AI/ML | LLM providers, RAG, knowledge, embeddings |
| Application metrics | Chat latency, agent performance, business KPIs |
| LLM provider health | `provider_health/` - monitors LLM availability |
| User management | Auth, sessions, permissions |
| Business logic | Workflow automation, batch processing |

---

## Frontend Consolidation

### autobot-vue (After Migration)

**STAYS - Business Logic:**
- `/chat` - AI Assistant
- `/knowledge` - Knowledge Base
- `/automation` - Workflow Builder
- `/analytics` - Codebase & BI Analytics

**REMOVE - Moves to SLM:**
- `/tools` - All subsections
- `/monitoring` - All subsections
- `/settings` - All subsections
- `/infrastructure`
- `/tls-certificates`
- `/secrets`

### slm-admin (Infrastructure Portal)

**Already has:**
- Fleet Overview, Services, Deployments
- Backups, Replications, Maintenance
- Monitoring (system, infra, logs, dashboards, alerts, errors)
- Settings (general, infrastructure, nodes, monitoring, notifications, API, backend)
- Tools (terminal, files, browser, VNC, voice, MCP, agents, vision, batch)
- Security

**Consolidate from autobot-vue:**
- Ensure TLS Certificates view exists
- Ensure Secrets Manager exists
- Merge any missing subsections (keep best implementation, SLM style)

---

## Naming Cleanup

| Old | New |
|-----|-----|
| `phase9_monitoring` | `monitoring` |
| Any `phase9_*` references | Remove phase prefix |

---

## Two-App Architecture

| App | Purpose | Focus |
|-----|---------|-------|
| **autobot-vue** | User-facing AI app | Chat, Knowledge, Workflows, Analytics |
| **slm-admin** | Infrastructure portal | Fleet, Deployments, Monitoring, Settings, Tools |

---

## Implementation Order

1. **Backend cleanup** - Remove infrastructure code from backend/
2. **SLM consolidation** - Ensure SLM has all needed functionality
3. **Frontend autobot-vue** - Remove infrastructure routes
4. **Frontend slm-admin** - Add any missing features from autobot-vue
5. **API client** - If backend needs infra info, add SLM API client
6. **Testing** - Verify both apps work independently

---

## Files to Review (May Have Mixed Concerns)

- `backend/api/monitoring.py` - Split app vs infra monitoring
- `backend/api/services.py` - Check if infrastructure-related
- `backend/api/vm_services.py` - Likely DELETE
- `backend/services/redis_service_manager.py` - Review
- `backend/services/vm_service_registry.py` - Likely DELETE

---

## Success Criteria

- [ ] Backend has zero SSH/Ansible imports
- [ ] Backend has zero infrastructure deployment code
- [ ] SLM handles all VM deployments directly
- [ ] autobot-vue only has business routes (chat, knowledge, automation, analytics)
- [ ] slm-admin has all infrastructure/ops functionality
- [ ] No functionality lost during migration
