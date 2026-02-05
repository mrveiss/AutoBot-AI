# Folder Restructure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize repository folders by deployment role so each `autobot-*` folder clearly maps to one machine.

**Architecture:** Create new folder structure with clear naming (`autobot-{role}-{type}`), migrate code in phases (copy → update imports → cleanup), maintain git history with `git mv` where possible.

**Tech Stack:** Python, Vue 3/TypeScript, Bash scripts, Git

**Design Doc:** `docs/plans/2026-02-05-folder-restructure-design.md`

**GitHub Issue:** #781

---

## Phase 1: Create Directory Structure (Safe - Additive Only)

### Task 1: Create autobot-shared

**Files:**
- Create: `autobot-shared/__init__.py`
- Create: `autobot-shared/README.md`
- Create: `autobot-shared/requirements.txt`
- Copy: `src/utils/redis_client.py` → `autobot-shared/redis_client.py`
- Copy: `src/utils/http_client.py` → `autobot-shared/http_client.py`
- Copy: `src/utils/logging_manager.py` → `autobot-shared/logging_manager.py`
- Copy: `src/utils/error_boundaries.py` → `autobot-shared/error_boundaries.py`
- Copy: `src/config/ssot_config.py` → `autobot-shared/ssot_config.py`

**Step 1: Create directory and __init__.py**

```bash
mkdir -p autobot-shared
touch autobot-shared/__init__.py
```

**Step 2: Create README.md**

```bash
cat > autobot-shared/README.md << 'EOF'
# AutoBot Shared Utilities

> **Deployment:** Copied to each backend during deploy

Common utilities used across all AutoBot backend components.

## Contents

| File | Purpose |
|------|---------|
| `redis_client.py` | Redis connection utilities |
| `http_client.py` | HTTP client utilities |
| `logging_manager.py` | Centralized logging |
| `error_boundaries.py` | Error handling |
| `ssot_config.py` | SSOT configuration |

## Usage

Each backend's `requirements.txt` should include:
```
-e ../autobot-shared
```

Or copy `autobot-shared/` into the component during deployment.
EOF
```

**Step 3: Copy shared utilities**

```bash
cp src/utils/redis_client.py autobot-shared/
cp src/utils/http_client.py autobot-shared/
cp src/utils/logging_manager.py autobot-shared/
cp src/utils/error_boundaries.py autobot-shared/
cp src/config/ssot_config.py autobot-shared/
```

**Step 4: Create requirements.txt**

```bash
cat > autobot-shared/requirements.txt << 'EOF'
redis>=4.5.0
httpx>=0.24.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
EOF
```

**Step 5: Commit**

```bash
git add autobot-shared/
git commit -m "feat(shared): create autobot-shared with common utilities (#781)"
```

---

### Task 2: Create infrastructure directory

**Files:**
- Create: `infrastructure/README.md`
- Move: `docker/` → `infrastructure/docker/`
- Move: `scripts/` → `infrastructure/scripts/`
- Move: `config/` → `infrastructure/config/`
- Move: `certs/` → `infrastructure/certs/`
- Move: `mcp-servers/` → `infrastructure/mcp/servers/`
- Move: `mcp-tools/` → `infrastructure/mcp/tools/`
- Move: `novnc/` → `infrastructure/novnc/`

**Step 1: Create infrastructure directory**

```bash
mkdir -p infrastructure
```

**Step 2: Create README.md**

```bash
cat > infrastructure/README.md << 'EOF'
# Infrastructure

Dev/ops tooling - not deployed as application code.

## Contents

| Directory | Purpose |
|-----------|---------|
| `docker/` | Dockerfiles and compose configs |
| `scripts/` | Utility and deployment scripts |
| `config/` | Environment configurations |
| `certs/` | SSL certificates |
| `mcp/` | MCP servers and tools |
| `novnc/` | VNC server |
| `tests/` | Test suites |
| `analysis/` | Code analysis tools |
EOF
```

**Step 3: Move directories with git mv**

```bash
git mv docker infrastructure/docker
git mv scripts infrastructure/scripts
git mv config infrastructure/config
git mv certs infrastructure/certs
mkdir -p infrastructure/mcp
git mv mcp-servers infrastructure/mcp/servers
git mv mcp-tools infrastructure/mcp/tools
git mv novnc infrastructure/novnc
```

**Step 4: Move tests and analysis**

```bash
git mv tests infrastructure/tests
mkdir -p infrastructure/analysis
git mv analysis infrastructure/analysis/analysis
git mv code-analysis-suite infrastructure/analysis/code-analysis-suite
git mv reports infrastructure/analysis/reports
```

**Step 5: Commit**

```bash
git add infrastructure/
git commit -m "refactor(infra): move dev/ops tooling to infrastructure/ (#781)"
```

---

### Task 3: Rename SLM directories

**Files:**
- Move: `slm-server/` → `autobot-slm-backend/`
- Move: `slm-admin/` → `autobot-slm-frontend/`
- Move: `ansible/` → `autobot-slm-backend/ansible/`

**Step 1: Rename slm-server**

```bash
git mv slm-server autobot-slm-backend
```

**Step 2: Rename slm-admin**

```bash
git mv slm-admin autobot-slm-frontend
```

**Step 3: Move ansible into SLM backend**

```bash
git mv ansible autobot-slm-backend/ansible
```

**Step 4: Update README files**

```bash
# Update autobot-slm-backend README
cat > autobot-slm-backend/README.md << 'EOF'
# AutoBot SLM Backend

> **Deployment Target: 172.16.168.19 (SLM Machine)**

System Lifecycle Manager backend - manages fleet nodes, code distribution, and system orchestration.

## Sync Command

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh slm autobot-slm-backend/ /home/autobot/autobot-slm-backend/
```

## Key Components

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI endpoints |
| `models/` | SQLAlchemy models |
| `services/` | Business logic |
| `migrations/` | Database migrations |
| `ansible/` | Deployment playbooks |
EOF

# Update autobot-slm-frontend README
cat > autobot-slm-frontend/README.md << 'EOF'
# AutoBot SLM Frontend

> **Deployment Target: 172.16.168.21 (Frontend VM)**

Vue 3 + TypeScript admin dashboard for fleet management.

## Sync Command

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh frontend autobot-slm-frontend/src/ /home/autobot/AutoBot/autobot-slm-frontend/src/
```

## Backend

API: `autobot-slm-backend/` (runs on 172.16.168.19)
EOF
```

**Step 5: Commit**

```bash
git add autobot-slm-backend/ autobot-slm-frontend/
git commit -m "refactor(slm): rename slm-server → autobot-slm-backend, slm-admin → autobot-slm-frontend (#781)"
```

---

### Task 4: Rename main user directories

**Files:**
- Move: `autobot-vue/` → `autobot-user-frontend/`
- Create: `autobot-user-backend/` (placeholder for Phase 2)

**Step 1: Rename autobot-vue**

```bash
git mv autobot-vue autobot-user-frontend
```

**Step 2: Update README**

```bash
cat > autobot-user-frontend/README.md << 'EOF'
# AutoBot User Frontend

> **Deployment Target: 172.16.168.20 (Main Machine)**

Vue 3 chat interface for AutoBot.

## Sync Command

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh main autobot-user-frontend/ /home/autobot/autobot-user-frontend/
```

## Backend

API: `autobot-user-backend/` (same machine)
EOF
```

**Step 3: Create autobot-user-backend placeholder**

```bash
mkdir -p autobot-user-backend
cat > autobot-user-backend/README.md << 'EOF'
# AutoBot User Backend

> **Deployment Target: 172.16.168.20 (Main Machine)**

Core AutoBot backend - AI agents, chat, tools.

## Note

This directory will contain code migrated from `src/` and `backend/` in Phase 2.

## Sync Command

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh main autobot-user-backend/ /home/autobot/autobot-user-backend/
```
EOF
```

**Step 4: Commit**

```bash
git add autobot-user-frontend/ autobot-user-backend/
git commit -m "refactor(user): rename autobot-vue → autobot-user-frontend, create autobot-user-backend placeholder (#781)"
```

---

### Task 5: Create worker directories

**Files:**
- Create: `autobot-npu-worker/`
- Create: `autobot-browser-worker/`

**Step 1: Create autobot-npu-worker**

```bash
mkdir -p autobot-npu-worker
cat > autobot-npu-worker/README.md << 'EOF'
# AutoBot NPU Worker

> **Deployment Target: 172.16.168.22 (NPU Machine)**

AI/NPU hardware acceleration worker.

## Note

This directory will contain code extracted from `src/` in Phase 2:
- NPU-specific processing
- OpenVINO integration
- Hardware acceleration

## Sync Command

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh npu autobot-npu-worker/ /home/autobot/autobot-npu-worker/
```
EOF

cat > autobot-npu-worker/requirements.txt << 'EOF'
# NPU Worker dependencies
openvino>=2023.0.0
numpy>=1.24.0
-e ../autobot-shared
EOF
```

**Step 2: Create autobot-browser-worker**

```bash
mkdir -p autobot-browser-worker
cat > autobot-browser-worker/README.md << 'EOF'
# AutoBot Browser Worker

> **Deployment Target: 172.16.168.25 (Browser Machine)**

Playwright browser automation services.

## Note

This directory will contain code extracted from `src/` in Phase 2:
- Playwright services
- Browser automation
- Screenshot handling

## Sync Command

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh browser autobot-browser-worker/ /home/autobot/autobot-browser-worker/
```
EOF

cat > autobot-browser-worker/requirements.txt << 'EOF'
# Browser Worker dependencies
playwright>=1.40.0
-e ../autobot-shared
EOF
```

**Step 3: Commit**

```bash
git add autobot-npu-worker/ autobot-browser-worker/
git commit -m "feat(workers): create autobot-npu-worker and autobot-browser-worker placeholders (#781)"
```

---

### Task 6: Update CLAUDE.md with new structure

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update Component Architecture section**

Replace the Component Architecture section in CLAUDE.md with:

```markdown
### Component Architecture (CRITICAL - Don't Mix Up!)

| Directory | Deploys To | Description |
|-----------|------------|-------------|
| `autobot-user-backend/` | 172.16.168.20 (Main) | Core AutoBot backend - AI agents, chat, tools |
| `autobot-user-frontend/` | 172.16.168.20 (Main) | Main AutoBot chat interface |
| `autobot-slm-backend/` | 172.16.168.19 (SLM) | **SLM backend** - Fleet management, code sync |
| `autobot-slm-frontend/` | 172.16.168.21 (Frontend VM) | **SLM admin dashboard** - Vue 3 UI for fleet |
| `autobot-npu-worker/` | 172.16.168.22 (NPU) | NPU/AI acceleration worker |
| `autobot-browser-worker/` | 172.16.168.25 (Browser) | Playwright automation |
| `autobot-shared/` | (all backends) | Common utilities |
| `infrastructure/` | (dev machine) | Dev/ops tooling |

**Before editing, verify:**
- `autobot-user-*` → Main AutoBot functionality
- `autobot-slm-*` → SLM fleet management (different system!)
- `autobot-*-worker` → Specialized workers

**Sync commands:**
```bash
# User backend/frontend → Main
./infrastructure/scripts/utilities/sync-to-vm.sh main autobot-user-backend/
./infrastructure/scripts/utilities/sync-to-vm.sh main autobot-user-frontend/

# SLM backend → SLM machine
./infrastructure/scripts/utilities/sync-to-vm.sh slm autobot-slm-backend/

# SLM frontend → Frontend VM
./infrastructure/scripts/utilities/sync-to-vm.sh frontend autobot-slm-frontend/src/

# Workers
./infrastructure/scripts/utilities/sync-to-vm.sh npu autobot-npu-worker/
./infrastructure/scripts/utilities/sync-to-vm.sh browser autobot-browser-worker/
```
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(claude): update CLAUDE.md with new folder structure (#781)"
```

---

### Task 7: Cleanup deprecated directories

**Files:**
- Delete: `autobot/` (empty)
- Delete: `frontend/` (deprecated)
- Delete: `main.py.deprecated`
- Delete: `OLD_CLAUDE.md`

**Step 1: Remove empty/deprecated directories**

```bash
rm -rf autobot/
rm -rf frontend/
rm -f main.py.deprecated
rm -f OLD_CLAUDE.md
```

**Step 2: Commit**

```bash
git add -A
git commit -m "chore: remove deprecated directories and files (#781)"
```

---

## Phase 2: Migrate Code (Future - Separate Plan)

> **Note:** Phase 2 involves migrating `src/` and `backend/` into `autobot-user-backend/` and updating all imports. This is a significant undertaking that should be planned separately after Phase 1 is stable.

### Tasks for Phase 2 (outline):
1. Copy `src/` contents to `autobot-user-backend/`
2. Merge `backend/` into `autobot-user-backend/`
3. Update all imports from `from src.` to `from autobot_user_backend.`
4. Update all imports from `from src.utils.` to `from autobot_shared.`
5. Extract NPU code to `autobot-npu-worker/`
6. Extract browser code to `autobot-browser-worker/`
7. Update sync scripts
8. Run full test suite
9. Remove old `src/` and `backend/` directories

---

## Phase 3: Update Tooling (Future - Separate Plan)

### Tasks for Phase 3 (outline):
1. Update all sync scripts in `infrastructure/scripts/`
2. Update CI/CD configurations
3. Update Docker configurations
4. Update any hardcoded paths

---

## Verification Checklist

After Phase 1:
- [ ] All new directories exist with README.md
- [ ] `autobot-shared/` contains utility files
- [ ] `infrastructure/` contains all tooling
- [ ] `autobot-slm-backend/` and `autobot-slm-frontend/` renamed
- [ ] `autobot-user-frontend/` renamed
- [ ] `autobot-user-backend/` placeholder created
- [ ] Worker placeholders created
- [ ] CLAUDE.md updated
- [ ] Deprecated files removed
- [ ] Git history preserved (use `git log --follow`)
