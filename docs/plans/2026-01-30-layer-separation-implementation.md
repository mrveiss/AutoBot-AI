# Layer Separation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Separate AutoBot into Management Layer (SLM) and Business Layer (Backend) with clean boundaries.

**Architecture:** Delete all infrastructure/SSH/Ansible code from backend. SLM already has complete infrastructure management. Frontend autobot-vue keeps only business routes; slm-admin handles all infrastructure.

**Tech Stack:** Python/FastAPI (backend), Vue 3/TypeScript (frontends), Ansible (SLM only)

---

## Phase 1: Backend Cleanup - SLM Services

### Task 1.1: Delete backend/services/slm/ folder

**Files:**
- Delete: `backend/services/slm/` (entire folder)

**Step 1: Verify no critical imports**

Run:
```bash
grep -r "from backend.services.slm" backend/ --include="*.py" | grep -v "services/slm/"
```
Expected: List of files importing from this module (need to update these)

**Step 2: Check import dependencies**

Run:
```bash
grep -r "from backend.services.slm" backend/ --include="*.py" | grep -v "services/slm/" | cut -d: -f1 | sort -u
```
Expected: List of files to update

**Step 3: Remove imports from dependent files**

For each file found, remove or comment out the SLM imports. These will be replaced with SLM API calls later.

**Step 4: Delete the folder**

Run:
```bash
rm -rf backend/services/slm/
```

**Step 5: Verify deletion**

Run:
```bash
ls backend/services/slm/ 2>&1
```
Expected: "No such file or directory"

**Step 6: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove services/slm/ - moved to slm-server

Infrastructure services now exclusively in slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 1.2: Delete autobot-user-backend/api/slm/ folder

**Files:**
- Delete: `autobot-user-backend/api/slm/` (entire folder)

**Step 1: Check router registration**

Run:
```bash
grep -r "slm" backend/initialization/router_registry/ --include="*.py"
```
Expected: Find where SLM routers are registered

**Step 2: Remove router registration**

Edit `backend/initialization/router_registry/core_routers.py` or similar - remove SLM router imports and registrations.

**Step 3: Delete the folder**

Run:
```bash
rm -rf autobot-user-backend/api/slm/
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove api/slm/ routes - use slm-server directly

SLM API endpoints now served exclusively by slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 2: Backend Cleanup - SSH/Ansible

### Task 2.1: Delete SSH services

**Files:**
- Delete: `backend/services/ssh_connection_service.py`
- Delete: `backend/services/ssh_manager.py`
- Delete: `backend/services/ssh_connection_pool.py`
- Delete: `backend/services/ssh_provisioner.py`

**Step 1: Find imports**

Run:
```bash
grep -rn "from backend.services.ssh" backend/ --include="*.py" | grep -v "services/ssh"
```

**Step 2: Update dependent files**

For each file found:
- If it's infrastructure-related: mark for deletion
- If it's terminal-related: update to use SLM API

**Step 3: Delete SSH files**

Run:
```bash
rm -f backend/services/ssh_connection_service.py
rm -f backend/services/ssh_manager.py
rm -f backend/services/ssh_connection_pool.py
rm -f backend/services/ssh_provisioner.py
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove SSH services - SLM handles all SSH

SSH connections now managed exclusively by slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 2.2: Delete Ansible executor

**Files:**
- Delete: `backend/services/ansible_executor.py`

**Step 1: Find imports**

Run:
```bash
grep -rn "ansible_executor\|AnsibleExecutor" backend/ --include="*.py"
```

**Step 2: Remove imports from dependent files**

**Step 3: Delete file**

Run:
```bash
rm -f backend/services/ansible_executor.py
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove ansible_executor - SLM handles deployments

Ansible execution now exclusively in slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 3: Backend Cleanup - Infrastructure APIs

### Task 3.1: Delete infrastructure API files

**Files:**
- Delete: `autobot-user-backend/api/infrastructure.py`
- Delete: `autobot-user-backend/api/infrastructure_hosts.py`
- Delete: `autobot-user-backend/api/infrastructure_nodes.py`
- Delete: `autobot-user-backend/api/infrastructure_monitor.py`

**Step 1: Check router registration**

Run:
```bash
grep -rn "infrastructure" backend/initialization/ --include="*.py"
```

**Step 2: Remove router registrations**

Edit the router registry files to remove infrastructure router imports and registrations.

**Step 3: Delete files**

Run:
```bash
rm -f autobot-user-backend/api/infrastructure.py
rm -f autobot-user-backend/api/infrastructure_hosts.py
rm -f autobot-user-backend/api/infrastructure_nodes.py
rm -f autobot-user-backend/api/infrastructure_monitor.py
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove infrastructure APIs - use slm-server

Infrastructure endpoints now served by slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 3.2: Delete infrastructure services and models

**Files:**
- Delete: `backend/services/infrastructure_db.py`
- Delete: `backend/services/infrastructure_host_service.py`
- Delete: `backend/services/node_enrollment_service.py`
- Delete: `backend/models/infrastructure.py`
- Delete: `backend/schemas/infrastructure.py`
- Delete: `backend/tasks/deployment_tasks.py`
- Delete: `backend/test_infrastructure_db.py`

**Step 1: Find and update dependencies**

Run:
```bash
grep -rn "infrastructure_db\|infrastructure_host\|node_enrollment" backend/ --include="*.py"
```

**Step 2: Delete files**

Run:
```bash
rm -f backend/services/infrastructure_db.py
rm -f backend/services/infrastructure_host_service.py
rm -f backend/services/node_enrollment_service.py
rm -f backend/models/infrastructure.py
rm -f backend/schemas/infrastructure.py
rm -f backend/tasks/deployment_tasks.py
rm -f backend/test_infrastructure_db.py
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove infrastructure services/models

Infrastructure data now managed by slm-server database.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 4: Backend Cleanup - Monitoring

### Task 4.1: Delete infrastructure monitoring

**Files:**
- Delete: `autobot-user-backend/api/monitoring_hardware.py`
- Delete: `autobot-user-backend/api/monitoring_alerts.py`
- Delete: `autobot-user-backend/api/service_monitor.py`
- Delete: `autobot-user-backend/api/phase9_monitoring.py`
- Delete: `backend/services/consolidated_health_service.py`

**Step 1: Check router registrations**

Run:
```bash
grep -rn "monitoring_hardware\|monitoring_alerts\|service_monitor\|phase9_monitoring" backend/initialization/ --include="*.py"
```

**Step 2: Remove router registrations**

**Step 3: Delete files**

Run:
```bash
rm -f autobot-user-backend/api/monitoring_hardware.py
rm -f autobot-user-backend/api/monitoring_alerts.py
rm -f autobot-user-backend/api/service_monitor.py
rm -f autobot-user-backend/api/phase9_monitoring.py
rm -f backend/services/consolidated_health_service.py
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove infrastructure monitoring - use slm-server

Infrastructure monitoring now in slm-server. Renamed phase9 to monitoring.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 4.2: Review and clean autobot-user-backend/api/monitoring.py

**Files:**
- Modify: `autobot-user-backend/api/monitoring.py`

**Step 1: Read the file**

Identify which endpoints are:
- Infrastructure monitoring (DELETE)
- Application monitoring (KEEP)

**Step 2: Remove infrastructure endpoints**

Keep only application-level monitoring (chat performance, agent metrics, etc.)

**Step 3: Commit**

```bash
git add autobot-user-backend/api/monitoring.py
git commit -m "refactor(backend): clean monitoring.py - keep only app metrics

Removed infrastructure monitoring endpoints. Application metrics remain.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 5: Backend Cleanup - Additional Files

### Task 5.1: Delete VM services

**Files:**
- Delete: `autobot-user-backend/api/vm_services.py`
- Delete: `backend/services/vm_service_registry.py`

**Step 1: Check dependencies and remove**

Run:
```bash
grep -rn "vm_services\|vm_service_registry" backend/ --include="*.py"
```

**Step 2: Delete files**

Run:
```bash
rm -f autobot-user-backend/api/vm_services.py
rm -f backend/services/vm_service_registry.py
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(backend): remove VM services - use slm-server

VM service management now in slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 5.2: Clean up terminal handlers

**Files:**
- Review: `autobot-user-backend/api/terminal.py`
- Review: `autobot-user-backend/api/ssh_terminal_handlers.py`
- Review: `autobot-user-backend/api/agent_terminal.py`

**Step 1: Analyze terminal code**

Determine if terminal functionality should:
- Stay in backend (for chat-integrated terminal)
- Move to SLM (for infrastructure terminal)

**Step 2: Update terminal to use SLM API for SSH**

If keeping terminal in backend, update it to proxy SSH requests to SLM API instead of direct SSH.

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor(backend): update terminal to use SLM API for SSH

Terminal now proxies SSH requests through slm-server.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 6: Frontend - autobot-vue Cleanup

### Task 6.1: Remove infrastructure routes from router

**Files:**
- Modify: `autobot-user-frontend/src/router/index.ts`

**Step 1: Remove route imports**

Remove imports for:
- ToolsView
- MonitoringView
- SettingsView
- InfrastructureManager
- SecretsView
- TLSCertificatesView

**Step 2: Remove route definitions**

Remove routes:
- `/tools` and all children
- `/monitoring` and all children
- `/settings` and all children
- `/infrastructure`
- `/tls-certificates`
- `/secrets`

**Step 3: Update navigation**

Keep only:
- `/chat`
- `/knowledge`
- `/automation`
- `/analytics`

**Step 4: Commit**

```bash
git add autobot-user-frontend/src/router/index.ts
git commit -m "refactor(frontend): remove infrastructure routes from autobot-vue

Routes moved to slm-admin. autobot-vue now business-only.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6.2: Remove infrastructure components

**Files:**
- Delete: `autobot-user-frontend/src/views/ToolsView.vue`
- Delete: `autobot-user-frontend/src/views/MonitoringView.vue`
- Delete: `autobot-user-frontend/src/views/SettingsView.vue`
- Delete: `autobot-user-frontend/src/views/InfrastructureManager.vue`
- Delete: `autobot-user-frontend/src/views/SecretsView.vue`
- Delete: `autobot-user-frontend/src/views/TLSCertificatesView.vue`
- Delete: `autobot-user-frontend/src/components/settings/` (entire folder)
- Delete: `autobot-user-frontend/src/components/infrastructure/` (entire folder)
- Delete: `autobot-user-frontend/src/composables/useInfrastructure.ts`

**Step 1: Delete view files**

Run:
```bash
rm -f autobot-user-frontend/src/views/ToolsView.vue
rm -f autobot-user-frontend/src/views/MonitoringView.vue
rm -f autobot-user-frontend/src/views/SettingsView.vue
rm -f autobot-user-frontend/src/views/InfrastructureManager.vue
rm -f autobot-user-frontend/src/views/SecretsView.vue
rm -f autobot-user-frontend/src/views/TLSCertificatesView.vue
```

**Step 2: Delete component folders**

Run:
```bash
rm -rf autobot-user-frontend/src/components/settings/
rm -rf autobot-user-frontend/src/components/infrastructure/
rm -rf autobot-user-frontend/src/components/monitoring/
```

**Step 3: Delete composables**

Run:
```bash
rm -f autobot-user-frontend/src/composables/useInfrastructure.ts
```

**Step 4: Commit**

```bash
git add -A
git commit -m "refactor(frontend): remove infrastructure components from autobot-vue

Components now in slm-admin. autobot-vue is business-only.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

### Task 6.3: Update App.vue navigation

**Files:**
- Modify: `autobot-user-frontend/src/App.vue`

**Step 1: Remove infrastructure nav items**

Update navigation to show only:
- Chat
- Knowledge
- Automation
- Analytics

**Step 2: Add link to SLM Admin**

Add a link/button to open slm-admin for infrastructure management.

**Step 3: Commit**

```bash
git add autobot-user-frontend/src/App.vue
git commit -m "refactor(frontend): update App.vue navigation

Removed infrastructure nav items. Added link to SLM Admin.
Part of layer separation (#729)

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Phase 7: Frontend - slm-admin Consolidation

### Task 7.1: Verify TLS Certificates view exists

**Files:**
- Check: `slm-admin/src/views/` for TLS view

**Step 1: Check existing views**

Run:
```bash
ls slm-admin/src/views/ | grep -i tls
```

**Step 2: If missing, add route**

If TLS view doesn't exist, add route to `/security` or create `/tls` route.

**Step 3: Commit if changes made**

---

### Task 7.2: Verify Secrets Manager exists

**Files:**
- Check: `slm-admin/src/views/` for Secrets view

**Step 1: Check existing views**

Run:
```bash
ls slm-admin/src/views/ | grep -i secret
```

**Step 2: If missing, add secrets route**

Add `/secrets` route to slm-admin router.

**Step 3: Commit if changes made**

---

## Phase 8: Verification

### Task 8.1: Verify backend has no SSH/Ansible

**Step 1: Search for SSH imports**

Run:
```bash
grep -rn "paramiko\|ssh\|ansible" backend/ --include="*.py" | grep -v "__pycache__"
```
Expected: No results (or only comments/docs)

**Step 2: Search for infrastructure imports**

Run:
```bash
grep -rn "infrastructure" backend/ --include="*.py" | grep -v "__pycache__"
```
Expected: No results

---

### Task 8.2: Test backend startup

**Step 1: Start backend**

Run:
```bash
cd /home/kali/Desktop/AutoBot && python -m backend.main --help
```
Expected: No import errors

**Step 2: Run backend tests**

Run:
```bash
pytest backend/tests/ -v --ignore=backend/tests/infrastructure
```
Expected: Tests pass

---

### Task 8.3: Test frontend builds

**Step 1: Build autobot-vue**

Run:
```bash
cd autobot-vue && npm run build
```
Expected: Build succeeds

**Step 2: Build slm-admin**

Run:
```bash
cd slm-admin && npm run build
```
Expected: Build succeeds

---

### Task 8.4: Final commit and tag

**Step 1: Create summary commit**

Run:
```bash
git add -A
git commit -m "feat: complete layer separation - management vs business (#729)

BREAKING CHANGE: Infrastructure APIs removed from backend.

Management Layer (SLM):
- All SSH/Ansible operations
- Node deployment and enrollment
- Infrastructure monitoring
- Fleet management
- TLS certificates
- Secrets (infrastructure)

Business Layer (Backend):
- Chat and AI agents
- Knowledge management
- Workflow automation
- Application analytics
- LLM provider health

Frontend:
- autobot-vue: Chat, Knowledge, Automation, Analytics
- slm-admin: All infrastructure operations

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Success Criteria Checklist

- [ ] `grep -r "paramiko" backend/` returns nothing
- [ ] `grep -r "ansible" backend/` returns nothing (except comments)
- [ ] `grep -r "ssh_connection" backend/` returns nothing
- [ ] `backend/services/slm/` folder does not exist
- [ ] `autobot-user-backend/api/slm/` folder does not exist
- [ ] `autobot-user-backend/api/infrastructure*.py` files do not exist
- [ ] `autobot-vue` has only 4 main routes: chat, knowledge, automation, analytics
- [ ] `slm-admin` has TLS and Secrets management
- [ ] Backend starts without import errors
- [ ] Both frontends build successfully
