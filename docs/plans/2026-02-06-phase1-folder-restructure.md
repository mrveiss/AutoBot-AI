# Phase 1: Create Folder Structure - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the new folder structure and copy all files to their new locations without deleting anything.

**Architecture:** Create `autobot-*` directories for each deployable component, `infrastructure/` for dev/ops tooling, then copy files from current locations. Original files remain untouched for safety.

**Tech Stack:** Bash (mkdir, cp, rsync), Git

**Issue:** #781 - refactor: Reorganize repository folders by deployment role

---

## Task 1: Create Base Directory Structure

**Files:**
- Create: `autobot-user-backend/`
- Create: `autobot-user-frontend/`
- Create: `autobot-slm-backend/`
- Create: `autobot-slm-frontend/`
- Create: `autobot-npu-worker/`
- Create: `autobot-browser-worker/`
- Create: `autobot-shared/`
- Create: `infrastructure/`

**Step 1: Create all top-level directories**

```bash
mkdir -p autobot-user-backend/{api,services,models,migrations,agents,tools,resources/{prompts,templates,content,knowledge},monitoring}
mkdir -p autobot-user-frontend/{src,public}
mkdir -p autobot-slm-backend/{api,services,models,migrations,ansible}
mkdir -p autobot-slm-frontend/{src,public}
mkdir -p autobot-npu-worker/{workers,models}
mkdir -p autobot-browser-worker/services
mkdir -p autobot-shared
mkdir -p infrastructure/{docker,scripts,config,certs,mcp,novnc,analysis,tests}
```

**Step 2: Verify directories created**

```bash
ls -la autobot-* infrastructure/
```

Expected: All 8 top-level directories exist with subdirectories.

**Step 3: Commit structure**

```bash
git add autobot-* infrastructure/
git commit -m "chore(structure): create new folder structure (#781)

Phase 1, Task 1: Create base directories for reorganization.
- autobot-user-backend/ for main backend (→ .20)
- autobot-user-frontend/ for main frontend (→ .20)
- autobot-slm-backend/ for SLM backend (→ .19)
- autobot-slm-frontend/ for SLM frontend (→ .21)
- autobot-npu-worker/ for NPU worker (→ .22)
- autobot-browser-worker/ for browser worker (→ .25)
- autobot-shared/ for shared utilities
- infrastructure/ for dev/ops tooling"
```

---

## Task 2: Copy Shared Utilities to autobot-shared/

**Files:**
- Copy: `src/utils/redis_client.py` → `autobot-shared/redis_client.py`
- Copy: `src/utils/http_client.py` → `autobot-shared/http_client.py`
- Copy: `src/utils/logging_manager.py` → `autobot-shared/logging_manager.py`
- Copy: `src/utils/error_boundaries.py` → `autobot-shared/error_boundaries.py`
- Copy: `src/config/ssot_config.py` → `autobot-shared/ssot_config.py`
- Create: `autobot-shared/__init__.py`
- Create: `autobot-shared/requirements.txt`
- Create: `autobot-shared/README.md`

**Step 1: Copy shared utility files**

```bash
cp src/utils/redis_client.py autobot-shared/
cp src/utils/http_client.py autobot-shared/
cp src/utils/logging_manager.py autobot-shared/
cp src/utils/error_boundaries.py autobot-shared/
cp src/config/ssot_config.py autobot-shared/
```

**Step 2: Create __init__.py**

Create `autobot-shared/__init__.py`:
```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot shared utilities - deployed with each backend component."""

from .redis_client import get_redis_client
from .ssot_config import config

__all__ = ["get_redis_client", "config"]
```

**Step 3: Create requirements.txt**

Create `autobot-shared/requirements.txt`:
```
redis>=4.0.0
pyyaml>=6.0
pydantic>=2.0
python-dotenv>=1.0.0
```

**Step 4: Create README.md**

Create `autobot-shared/README.md`:
```markdown
# AutoBot Shared Utilities

Shared utilities deployed with each backend component.

## Deployment

This module is included in each backend's deployment:
- autobot-user-backend
- autobot-slm-backend
- autobot-npu-worker
- autobot-browser-worker

## Usage

```python
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
```

## Contents

| File | Purpose |
|------|---------|
| `redis_client.py` | Redis connection management |
| `http_client.py` | HTTP client utilities |
| `logging_manager.py` | Centralized logging |
| `error_boundaries.py` | Error handling |
| `ssot_config.py` | SSOT configuration |
```

**Step 5: Commit**

```bash
git add autobot-shared/
git commit -m "chore(shared): copy shared utilities to autobot-shared/ (#781)

Phase 1, Task 2: Populate autobot-shared with common utilities.
- redis_client.py, http_client.py, logging_manager.py
- error_boundaries.py, ssot_config.py
- Added __init__.py, requirements.txt, README.md"
```

---

## Task 3: Copy SLM Backend to autobot-slm-backend/

**Files:**
- Copy: `slm-server/*` → `autobot-slm-backend/`
- Copy: `ansible/*` → `autobot-slm-backend/ansible/`

**Step 1: Copy slm-server contents**

```bash
# Copy all slm-server contents (excluding node_modules, __pycache__, .env)
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' --exclude='logs/' --exclude='data/' --exclude='*.db' slm-server/ autobot-slm-backend/
```

**Step 2: Copy ansible playbooks**

```bash
rsync -av ansible/ autobot-slm-backend/ansible/
```

**Step 3: Update README with deployment target**

Update `autobot-slm-backend/README.md` to add deployment info at the top:
```markdown
# AutoBot SLM Backend

> **Deploys to:** 172.16.168.19 (SLM Server)

[rest of existing content]
```

**Step 4: Commit**

```bash
git add autobot-slm-backend/
git commit -m "chore(slm-backend): copy SLM backend to autobot-slm-backend/ (#781)

Phase 1, Task 3: Populate autobot-slm-backend.
- Copied slm-server/ contents
- Moved ansible/ playbooks into component
- Updated README with deployment target"
```

---

## Task 4: Copy SLM Frontend to autobot-slm-frontend/

**Files:**
- Copy: `slm-admin/*` → `autobot-slm-frontend/`

**Step 1: Copy slm-admin contents**

```bash
rsync -av --exclude='node_modules' --exclude='dist' --exclude='.env' slm-admin/ autobot-slm-frontend/
```

**Step 2: Update README with deployment target**

Update `autobot-slm-frontend/README.md`:
```markdown
# AutoBot SLM Frontend

> **Deploys to:** 172.16.168.21 (Frontend VM)

[rest of existing content]
```

**Step 3: Commit**

```bash
git add autobot-slm-frontend/
git commit -m "chore(slm-frontend): copy SLM frontend to autobot-slm-frontend/ (#781)

Phase 1, Task 4: Populate autobot-slm-frontend.
- Copied slm-admin/ contents
- Updated README with deployment target"
```

---

## Task 5: Copy User Frontend to autobot-user-frontend/

**Files:**
- Copy: `autobot-vue/*` → `autobot-user-frontend/`

**Step 1: Copy autobot-vue contents**

```bash
rsync -av --exclude='node_modules' --exclude='dist' --exclude='.env' --exclude='logs/' --exclude='test-results/' autobot-vue/ autobot-user-frontend/
```

**Step 2: Update README with deployment target**

Create/update `autobot-user-frontend/README.md`:
```markdown
# AutoBot User Frontend

> **Deploys to:** 172.16.168.20 (Main Server)

Vue 3 + TypeScript chat interface for AutoBot.

## Development

```bash
npm install
npm run dev
```

## Deployment

Synced to main server via:
```bash
./infrastructure/scripts/utilities/sync-to-vm.sh main autobot-user-frontend/
```
```

**Step 3: Commit**

```bash
git add autobot-user-frontend/
git commit -m "chore(user-frontend): copy user frontend to autobot-user-frontend/ (#781)

Phase 1, Task 5: Populate autobot-user-frontend.
- Copied autobot-vue/ contents
- Updated README with deployment target"
```

---

## Task 6: Copy User Backend to autobot-user-backend/

**Files:**
- Copy: `src/*` → `autobot-user-backend/` (reorganized)
- Copy: `backend/*` → `autobot-user-backend/` (merged)
- Copy: `prompts/` → `autobot-user-backend/resources/prompts/`
- Copy: `templates/` → `autobot-user-backend/resources/templates/`
- Copy: `content/` → `autobot-user-backend/resources/content/`
- Copy: `system_knowledge/` → `autobot-user-backend/resources/knowledge/`
- Copy: `migrations/` → `autobot-user-backend/migrations/`
- Copy: `monitoring/` → `autobot-user-backend/monitoring/`

**Step 1: Copy src/ contents (main code)**

```bash
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='config/ssot_config.py' --exclude='utils/redis_client.py' --exclude='utils/http_client.py' --exclude='utils/logging_manager.py' --exclude='utils/error_boundaries.py' src/ autobot-user-backend/
```

**Step 2: Copy backend/ contents (API layer)**

```bash
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='tests/' backend/api/ autobot-user-backend/api/
rsync -av --exclude='__pycache__' --exclude='*.pyc' backend/services/ autobot-user-backend/services/
rsync -av --exclude='__pycache__' --exclude='*.pyc' backend/models/ autobot-user-backend/models/
rsync -av --exclude='__pycache__' --exclude='*.pyc' backend/middleware/ autobot-user-backend/middleware/
rsync -av --exclude='__pycache__' --exclude='*.pyc' backend/schemas/ autobot-user-backend/schemas/
rsync -av --exclude='__pycache__' --exclude='*.pyc' backend/security/ autobot-user-backend/security/
rsync -av --exclude='__pycache__' --exclude='*.pyc' backend/initialization/ autobot-user-backend/initialization/
cp backend/main.py autobot-user-backend/
cp backend/app_factory.py autobot-user-backend/
cp backend/dependencies.py autobot-user-backend/
cp backend/*.py autobot-user-backend/ 2>/dev/null || true
```

**Step 3: Copy resources**

```bash
rsync -av prompts/ autobot-user-backend/resources/prompts/
rsync -av templates/ autobot-user-backend/resources/templates/
rsync -av content/ autobot-user-backend/resources/content/
rsync -av system_knowledge/ autobot-user-backend/resources/knowledge/
```

**Step 4: Copy migrations and monitoring**

```bash
rsync -av --exclude='__pycache__' migrations/ autobot-user-backend/migrations/
rsync -av monitoring/ autobot-user-backend/monitoring/
```

**Step 5: Create requirements.txt**

Create `autobot-user-backend/requirements.txt`:
```
-e ../autobot-shared

# Core
fastapi>=0.100.0
uvicorn>=0.23.0
pydantic>=2.0

# Database
sqlalchemy>=2.0
alembic>=1.12.0
aiosqlite>=0.19.0

# AI/ML
openai>=1.0.0
anthropic>=0.18.0
chromadb>=0.4.0
sentence-transformers>=2.2.0

# Include existing requirements
-r ../requirements.txt
```

**Step 6: Create README.md**

Create `autobot-user-backend/README.md`:
```markdown
# AutoBot User Backend

> **Deploys to:** 172.16.168.20 (Main Server)

Core AutoBot backend - AI agents, chat workflows, and API endpoints.

## Structure

| Directory | Purpose |
|-----------|---------|
| `api/` | FastAPI endpoint routers |
| `services/` | Business logic services |
| `models/` | SQLAlchemy database models |
| `agents/` | AI agent implementations |
| `tools/` | Agent tools |
| `resources/` | Prompts, templates, content |
| `migrations/` | Database migrations |

## Development

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8001
```

## Deployment

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh main autobot-user-backend/
```
```

**Step 7: Commit**

```bash
git add autobot-user-backend/
git commit -m "chore(user-backend): copy user backend to autobot-user-backend/ (#781)

Phase 1, Task 6: Populate autobot-user-backend.
- Merged src/ and backend/ into unified structure
- Moved prompts/, templates/, content/ to resources/
- Added requirements.txt and README.md"
```

---

## Task 7: Copy Infrastructure Files

**Files:**
- Copy: `docker/` → `infrastructure/docker/`
- Copy: `scripts/` → `infrastructure/scripts/`
- Copy: `config/` → `infrastructure/config/`
- Copy: `certs/` → `infrastructure/certs/`
- Copy: `tests/` → `infrastructure/tests/`
- Copy: `mcp-servers/` → `infrastructure/mcp/servers/`
- Copy: `mcp-tools/` → `infrastructure/mcp/tools/`
- Copy: `novnc/` → `infrastructure/novnc/`
- Copy: `analysis/`, `code-analysis-suite/`, `reports/` → `infrastructure/analysis/`
- Move: `Dockerfile`, `docker-compose.yml` → `infrastructure/docker/`

**Step 1: Copy docker files**

```bash
rsync -av docker/ infrastructure/docker/
cp Dockerfile infrastructure/docker/
cp docker-compose.yml infrastructure/docker/
```

**Step 2: Copy scripts**

```bash
rsync -av scripts/ infrastructure/scripts/
```

**Step 3: Copy config and certs**

```bash
rsync -av --exclude='*.pyc' --exclude='__pycache__' config/ infrastructure/config/
rsync -av certs/ infrastructure/certs/
```

**Step 4: Copy tests**

```bash
rsync -av --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' tests/ infrastructure/tests/
```

**Step 5: Copy MCP servers and tools**

```bash
mkdir -p infrastructure/mcp/servers infrastructure/mcp/tools
rsync -av mcp-servers/ infrastructure/mcp/servers/
rsync -av mcp-tools/ infrastructure/mcp/tools/
```

**Step 6: Copy novnc and analysis**

```bash
rsync -av novnc/ infrastructure/novnc/
rsync -av analysis/ infrastructure/analysis/
rsync -av code-analysis-suite/ infrastructure/analysis/code-analysis-suite/
rsync -av reports/ infrastructure/analysis/reports/
```

**Step 7: Create infrastructure README**

Create `infrastructure/README.md`:
```markdown
# AutoBot Infrastructure

Development and operations tooling - not deployed as application code.

## Contents

| Directory | Purpose |
|-----------|---------|
| `docker/` | Dockerfiles and compose files |
| `scripts/` | Utility and deployment scripts |
| `config/` | Environment configurations |
| `certs/` | SSL certificates |
| `tests/` | Test suites |
| `mcp/` | MCP servers and tools |
| `novnc/` | VNC server |
| `analysis/` | Code analysis tools and reports |

## Key Scripts

- `scripts/utilities/sync-to-vm.sh` - Sync code to VMs
- `scripts/startup/` - Service startup scripts
- `scripts/deployment/` - Deployment automation
```

**Step 8: Commit**

```bash
git add infrastructure/
git commit -m "chore(infra): copy infrastructure files (#781)

Phase 1, Task 7: Populate infrastructure directory.
- docker/, scripts/, config/, certs/, tests/
- mcp-servers/ and mcp-tools/ → mcp/
- novnc/, analysis/, code-analysis-suite/, reports/"
```

---

## Task 8: Create NPU and Browser Worker Stubs

**Files:**
- Create: `autobot-npu-worker/main.py`
- Create: `autobot-npu-worker/requirements.txt`
- Create: `autobot-npu-worker/README.md`
- Create: `autobot-browser-worker/main.py`
- Create: `autobot-browser-worker/requirements.txt`
- Create: `autobot-browser-worker/README.md`

**Step 1: Create NPU worker stub**

Create `autobot-npu-worker/main.py`:
```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot NPU Worker - Hardware AI acceleration service.

Deploys to: 172.16.168.22 (NPU VM)

This is a stub for Phase 1. NPU-specific code will be extracted
from autobot-user-backend in a future phase.
"""

import logging

logger = logging.getLogger(__name__)


def main():
    """NPU worker entry point."""
    logger.info("NPU Worker starting...")
    # TODO: Extract NPU code from src/ in Phase 2+


if __name__ == "__main__":
    main()
```

Create `autobot-npu-worker/requirements.txt`:
```
-e ../autobot-shared

# NPU/AI
openvino>=2023.0
torch>=2.0.0
numpy>=1.24.0
```

Create `autobot-npu-worker/README.md`:
```markdown
# AutoBot NPU Worker

> **Deploys to:** 172.16.168.22 (NPU VM)

Hardware AI acceleration worker using Intel NPU/OpenVINO.

## Status

**Stub** - NPU-specific code will be extracted from main backend in a future phase.

## Deployment

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh npu autobot-npu-worker/
```
```

**Step 2: Create Browser worker stub**

Create `autobot-browser-worker/main.py`:
```python
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""AutoBot Browser Worker - Playwright automation service.

Deploys to: 172.16.168.25 (Browser VM)

This is a stub for Phase 1. Browser-specific code will be extracted
from autobot-user-backend in a future phase.
"""

import logging

logger = logging.getLogger(__name__)


def main():
    """Browser worker entry point."""
    logger.info("Browser Worker starting...")
    # TODO: Extract browser automation code from src/ in Phase 2+


if __name__ == "__main__":
    main()
```

Create `autobot-browser-worker/requirements.txt`:
```
-e ../autobot-shared

# Browser automation
playwright>=1.40.0
```

Create `autobot-browser-worker/README.md`:
```markdown
# AutoBot Browser Worker

> **Deploys to:** 172.16.168.25 (Browser VM)

Playwright-based browser automation worker.

## Status

**Stub** - Browser automation code will be extracted from main backend in a future phase.

## Deployment

```bash
./infrastructure/scripts/utilities/sync-to-vm.sh browser autobot-browser-worker/
```
```

**Step 3: Commit**

```bash
git add autobot-npu-worker/ autobot-browser-worker/
git commit -m "chore(workers): create NPU and browser worker stubs (#781)

Phase 1, Task 8: Create stub directories for NPU and browser workers.
- autobot-npu-worker/ for NPU VM (.22)
- autobot-browser-worker/ for browser VM (.25)
- Code extraction planned for future phases"
```

---

## Task 9: Verify Phase 1 Complete

**Step 1: Verify all directories exist**

```bash
ls -la autobot-* infrastructure/
```

Expected: All 8 directories with contents.

**Step 2: Verify file counts**

```bash
echo "=== File counts ==="
echo "autobot-user-backend: $(find autobot-user-backend -type f | wc -l) files"
echo "autobot-user-frontend: $(find autobot-user-frontend -type f | wc -l) files"
echo "autobot-slm-backend: $(find autobot-slm-backend -type f | wc -l) files"
echo "autobot-slm-frontend: $(find autobot-slm-frontend -type f | wc -l) files"
echo "autobot-npu-worker: $(find autobot-npu-worker -type f | wc -l) files"
echo "autobot-browser-worker: $(find autobot-browser-worker -type f | wc -l) files"
echo "autobot-shared: $(find autobot-shared -type f | wc -l) files"
echo "infrastructure: $(find infrastructure -type f | wc -l) files"
```

**Step 3: Verify original directories untouched**

```bash
echo "=== Original directories still exist ==="
ls -d src/ backend/ slm-server/ slm-admin/ autobot-vue/ scripts/ docker/ tests/ 2>/dev/null && echo "All original directories intact"
```

**Step 4: Update GitHub issue with progress**

Add comment to issue #781:
```
## Phase 1 Complete ✓

Created new folder structure:
- [x] `autobot-user-backend/` - Main backend code
- [x] `autobot-user-frontend/` - Main Vue frontend
- [x] `autobot-slm-backend/` - SLM backend + ansible
- [x] `autobot-slm-frontend/` - SLM admin dashboard
- [x] `autobot-npu-worker/` - NPU worker stub
- [x] `autobot-browser-worker/` - Browser worker stub
- [x] `autobot-shared/` - Shared utilities
- [x] `infrastructure/` - Dev/ops tooling

Original directories preserved. Ready for Phase 2 (import updates).
```

---

## Phase 1 Checklist

- [ ] Task 1: Create base directory structure
- [ ] Task 2: Copy shared utilities
- [ ] Task 3: Copy SLM backend
- [ ] Task 4: Copy SLM frontend
- [ ] Task 5: Copy user frontend
- [ ] Task 6: Copy user backend
- [ ] Task 7: Copy infrastructure files
- [ ] Task 8: Create worker stubs
- [ ] Task 9: Verify and update issue

**Next:** Phase 2 - Update all imports to use new paths
