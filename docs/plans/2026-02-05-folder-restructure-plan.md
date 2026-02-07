# Folder Restructure Implementation Plan

> **HISTORICAL NOTE**: This document describes the initial flat infrastructure structure.
> The infrastructure has since been reorganized to a per-role structure.
> See the current structure in `infrastructure/README.md`.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Reorganize repository folders by deployment role so each `autobot-*` folder clearly maps to one machine.

**Architecture:** Create new folder structure with clear naming (`autobot-{role}-{type}`), migrate code in phases (copy then update imports then cleanup), maintain git history with `git mv` where possible.

**Tech Stack:** Python, Vue 3/TypeScript, Bash scripts, Git

**Design Doc:** `docs/plans/2026-02-05-folder-restructure-design.md`

**GitHub Issue:** #781

---

## Current Infrastructure Structure

The infrastructure folder now uses a per-role organization:

```text
infrastructure/
├── autobot-user-backend/       # User backend: docker, tests, config, scripts, templates
├── autobot-user-frontend/      # User frontend infra
├── autobot-slm-backend/        # SLM backend infra
├── autobot-slm-frontend/       # SLM frontend infra
├── autobot-npu-worker/         # NPU worker infra
├── autobot-browser-worker/     # Browser worker infra
└── shared/                     # Shared infrastructure
    ├── scripts/                # Common utilities, sync scripts
    ├── certs/                  # Certificate management
    ├── config/                 # Shared configurations
    ├── docker/                 # Shared docker resources
    ├── mcp/                    # MCP server configs
    ├── tools/                  # Development tools
    ├── tests/                  # Shared test utilities
    └── analysis/               # Analysis tools
```

---

## Phase 1: Create Directory Structure (Safe - Additive Only)

### Task 1: Create autobot-shared

**Files:**

- Create: `autobot-shared/__init__.py`
- Create: `autobot-shared/README.md`
- Create: `autobot-shared/requirements.txt`
- Copy: `src/utils/redis_client.py` to `autobot-shared/redis_client.py`
- Copy: `src/utils/http_client.py` to `autobot-shared/http_client.py`
- Copy: `src/utils/logging_manager.py` to `autobot-shared/logging_manager.py`
- Copy: `src/utils/error_boundaries.py` to `autobot-shared/error_boundaries.py`
- Copy: `src/config/ssot_config.py` to `autobot-shared/ssot_config.py`

### Task 2: Create infrastructure directory

**Files:**

- Create: `infrastructure/README.md`
- Move: `docker/` to `infrastructure/docker/`
- Move: `scripts/` to `infrastructure/scripts/`
- Move: `config/` to `infrastructure/config/`
- Move: `certs/` to `infrastructure/certs/`
- Move: `mcp-servers/` to `infrastructure/mcp/servers/`
- Move: `mcp-tools/` to `infrastructure/mcp/tools/`
- Move: `novnc/` to `infrastructure/novnc/`

**Note:** Infrastructure has since been reorganized to per-role structure.
See `infrastructure/README.md` for current layout.

### Task 3: Rename SLM directories

**Files:**

- Move: `slm-server/` to `autobot-slm-backend/`
- Move: `slm-admin/` to `autobot-slm-frontend/`
- Move: `ansible/` to `autobot-slm-backend/ansible/`

### Task 4: Rename main user directories

**Files:**

- Move: `autobot-vue/` to `autobot-user-frontend/`
- Create: `autobot-user-backend/` (placeholder for Phase 2)

### Task 5: Create worker directories

**Files:**

- Create: `autobot-npu-worker/`
- Create: `autobot-browser-worker/`

### Task 6: Update CLAUDE.md with new structure

**Files:**

- Modify: `CLAUDE.md`

Update sync commands to use new paths:

```bash
# User backend/frontend to Main
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-backend/
./infrastructure/shared/scripts/sync-to-vm.sh main autobot-user-frontend/

# SLM backend to SLM machine
./infrastructure/shared/scripts/sync-to-vm.sh slm autobot-slm-backend/

# SLM frontend to Frontend VM
./infrastructure/shared/scripts/sync-to-vm.sh frontend autobot-slm-frontend/

# Workers
./infrastructure/shared/scripts/sync-to-vm.sh npu autobot-npu-worker/
./infrastructure/shared/scripts/sync-to-vm.sh browser autobot-browser-worker/
```

### Task 7: Cleanup deprecated directories

**Files:**

- Delete: `autobot/` (empty)
- Delete: `frontend/` (deprecated)
- Delete: `main.py.deprecated`
- Delete: `OLD_CLAUDE.md`

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

1. Update all sync scripts in `infrastructure/shared/scripts/`
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
