# Folder Restructure Design

> **HISTORICAL NOTE**: This document describes the initial flat infrastructure structure.
> The infrastructure has since been reorganized to a per-role structure.
> See the current structure in `infrastructure/README.md`.

> **For Claude:** This is a design document. Implementation requires a separate plan.

**Goal:** Reorganize the repository so folders clearly indicate deployment targets by role.

**Principle:** Each deployable component gets its own folder with clear naming: `autobot-{role}-{type}`

---

## Final Structure

```text
/AutoBot/
│
├── # DEPLOYABLE COMPONENTS
│
├── autobot-user-backend/           # Deploys to 172.16.168.20 (Main)
│   ├── api/                        # FastAPI endpoints
│   ├── services/                   # Business logic
│   ├── models/                     # SQLAlchemy models
│   ├── migrations/                 # Database migrations
│   ├── agents/                     # AI agents
│   ├── tools/                      # Agent tools
│   ├── resources/                  # prompts/, templates/, content/
│   ├── main.py                     # Entry point
│   ├── requirements.txt            # Python dependencies
│   └── README.md                   # Deployment instructions
│
├── autobot-user-frontend/          # Deploys to 172.16.168.20 (Main)
│   ├── src/                        # Vue source
│   ├── public/                     # Static assets
│   ├── package.json                # Node dependencies
│   └── README.md
│
├── autobot-slm-backend/            # Deploys to 172.16.168.19 (SLM)
│   ├── api/                        # FastAPI endpoints
│   ├── services/                   # Sync orchestrator, etc.
│   ├── models/                     # Fleet models
│   ├── migrations/                 # SLM migrations
│   ├── ansible/                    # Deployment playbooks
│   ├── main.py
│   ├── requirements.txt
│   └── README.md
│
├── autobot-slm-frontend/           # Deploys to 172.16.168.21 (Frontend VM)
│   ├── src/                        # Vue source
│   ├── public/
│   ├── package.json
│   └── README.md
│
├── autobot-npu-worker/             # Deploys to 172.16.168.22 (NPU)
│   ├── workers/                    # NPU worker processes
│   ├── models/                     # AI models
│   ├── main.py
│   ├── requirements.txt            # OpenVINO, torch, etc.
│   └── README.md
│
├── autobot-browser-worker/         # Deploys to 172.16.168.25 (Browser)
│   ├── services/                   # Playwright services
│   ├── main.py
│   ├── requirements.txt            # Playwright, etc.
│   └── README.md
│
├── autobot-shared/                 # Deployed with each backend
│   ├── redis_client.py             # Redis connection
│   ├── http_client.py              # HTTP utilities
│   ├── logging_manager.py          # Centralized logging
│   ├── error_boundaries.py         # Error handling
│   ├── ssot_config.py              # SSOT configuration
│   ├── requirements.txt            # Base dependencies
│   └── README.md
│
├── # INFRASTRUCTURE (Dev/Ops tooling - not deployed as code)
│
├── infrastructure/                 # Per-role organization (CURRENT)
│   ├── autobot-user-backend/       # User backend infra
│   ├── autobot-user-frontend/      # User frontend infra
│   ├── autobot-slm-backend/        # SLM backend infra
│   ├── autobot-slm-frontend/       # SLM frontend infra
│   ├── autobot-npu-worker/         # NPU worker infra
│   ├── autobot-browser-worker/     # Browser worker infra
│   └── shared/                     # Shared infrastructure
│       ├── scripts/                # Utility scripts
│       ├── config/                 # Environment configs
│       ├── certs/                  # Certificates
│       ├── mcp/                    # MCP servers and tools
│       ├── novnc/                  # VNC server
│       ├── analysis/               # Code analysis tools
│       └── tests/                  # Test suites
│
├── # ROOT LEVEL (Documentation and minimal config)
│
├── docs/                           # All documentation
│   ├── plans/                      # Design documents
│   ├── developer/                  # Developer guides
│   ├── api/                        # API documentation
│   └── system-state.md
│
├── README.md                       # Project overview
├── CLAUDE.md                       # AI development instructions
├── CHANGELOG.md                    # Version history
├── .gitignore
├── pytest.ini                      # Test config (runs all component tests)
└── pyproject.toml                  # Project metadata (optional)
```

---

## Migration Mapping

### Deployable Code

| Current | New | Action |
|---------|-----|--------|
| `src/` | `autobot-user-backend/` | Rename + reorganize |
| `backend/` | `autobot-user-backend/` | Merge into user-backend |
| `autobot-user-frontend/` | `autobot-user-frontend/` | Rename |
| `slm-server/` | `autobot-slm-backend/` | Rename |
| `slm-admin/` | `autobot-slm-frontend/` | Rename |
| `ansible/` | `autobot-slm-backend/ansible/` | Move into SLM |
| (extract from src/) | `autobot-npu-worker/` | Create new |
| (extract from src/) | `autobot-browser-worker/` | Create new |

### Shared Utilities

| Current | New |
|---------|-----|
| `autobot-user-backend/utils/redis_client.py` | `autobot-shared/redis_client.py` |
| `autobot-user-backend/utils/http_client.py` | `autobot-shared/http_client.py` |
| `autobot-user-backend/utils/logging_manager.py` | `autobot-shared/logging_manager.py` |
| `autobot-user-backend/utils/error_boundaries.py` | `autobot-shared/error_boundaries.py` |
| `src/config/ssot_config.py` | `autobot-shared/ssot_config.py` |

### Infrastructure (Current Per-Role Structure)

| Current | New |
|---------|-----|
| `docker/`, `Dockerfile`, `docker-compose.yml` | `infrastructure/<role>/docker/` or `infrastructure/shared/docker/` |
| `scripts/` | `infrastructure/shared/scripts/` |
| `config/` | `infrastructure/shared/config/` |
| `certs/` | `infrastructure/shared/certs/` |
| `tests/` | `infrastructure/<role>/tests/` or `infrastructure/shared/tests/` |
| `mcp-servers/`, `mcp-tools/` | `infrastructure/shared/mcp/` |
| `novnc/` | `infrastructure/shared/novnc/` |
| `analysis/`, `code-analysis-suite/`, `reports/` | `infrastructure/shared/analysis/` |

### Into User Backend Resources

| Current | New |
|---------|-----|
| `prompts/` | `autobot-user-backend/resources/prompts/` |
| `templates/` | `autobot-user-backend/resources/templates/` |
| `content/` | `autobot-user-backend/resources/content/` |
| `system_knowledge/` | `autobot-user-backend/resources/knowledge/` |
| `models/` | `autobot-user-backend/models/` |
| `migrations/` | `autobot-user-backend/migrations/` |
| `monitoring/` | `autobot-user-backend/monitoring/` |

### Into Docs

| Current | New |
|---------|-----|
| `planning/` | `docs/planning/` |
| `designs/` | `docs/designs/` |
| `tasks/` | `docs/tasks/` |
| `examples/` | `docs/examples/` |

### Delete (Empty/Deprecated)

| Directory | Reason |
|-----------|--------|
| `autobot/` | Empty directory |
| `frontend/` | Deprecated (only static/) |
| `main.py.deprecated` | Deprecated file |
| `OLD_CLAUDE.md` | Deprecated file |
| Various `*.md` report files at root | Move to docs or delete |

### Data Directories (Per-Component)

Each component has its own data directory (gitignored):

| Component | Data Location | Contents |
|-----------|---------------|----------|
| `autobot-user-backend/data/` | Main (.20) | `autobot.db`, `chroma_db/`, user data |
| `autobot-slm-backend/data/` | SLM (.19) | `slm.db`, fleet state |
| `autobot-npu-worker/data/` | NPU (.22) | Model cache, inference data |
| `autobot-browser-worker/data/` | Browser (.25) | Screenshots, session data |

**Gitignored patterns** (in each component):

```text
# In each autobot-*/
data/
logs/
*.db
__pycache__/
.venv/
node_modules/
```

Root-level data folders to migrate:

| Current | New |
|---------|-----|
| `data/` | `autobot-user-backend/data/` |
| `chroma_db/` | `autobot-user-backend/data/chroma_db/` |
| `logs/` | Per-component `logs/` |
| `backups/` | `autobot-slm-backend/data/backups/` (SLM manages backups) |
| `temp/`, `debug/`, `outputs/` | Per-component as needed |

---

## Deployment Mapping

| Component | Machine | IP | Command |
|-----------|---------|-----|---------|
| `autobot-user-backend/` | Main | 172.16.168.20 | `sync-to-vm.sh main autobot-user-backend/` |
| `autobot-user-frontend/` | Main | 172.16.168.20 | `sync-to-vm.sh main autobot-user-frontend/` |
| `autobot-slm-backend/` | SLM | 172.16.168.19 | `sync-to-vm.sh slm autobot-slm-backend/` |
| `autobot-slm-frontend/` | Frontend VM | 172.16.168.21 | `sync-to-vm.sh frontend autobot-slm-frontend/` |
| `autobot-npu-worker/` | NPU | 172.16.168.22 | `sync-to-vm.sh npu autobot-npu-worker/` |
| `autobot-browser-worker/` | Browser | 172.16.168.25 | `sync-to-vm.sh browser autobot-browser-worker/` |
| `autobot-shared/` | (all backends) | - | Deployed with each backend |

**Sync script location:** `infrastructure/shared/scripts/sync-to-vm.sh`

---

## Import Changes

After restructure, imports change:

```python
# Before
from src.utils.redis_client import get_redis_client
from src.config.ssot_config import config

# After
from autobot_shared.redis_client import get_redis_client
from autobot_shared.ssot_config import config
```

Each component's `requirements.txt` includes:

```text
-e ../autobot-shared
```

Or `autobot-shared` is copied into each component during deploy.

---

## Implementation Phases

### Phase 1: Create Structure (Safe)

1. Create new directories
2. Copy (don't move) files to new locations
3. Verify structure

### Phase 2: Update Imports

1. Update all import statements
2. Run tests
3. Fix any broken imports

### Phase 3: Update Tooling

1. Update sync scripts
2. Update CLAUDE.md
3. Update CI/CD configs

### Phase 4: Cleanup

1. Remove old directories
2. Update .gitignore
3. Final commit

---

## Risks

| Risk | Mitigation |
|------|------------|
| Broken imports | Phase 2 dedicated to import fixes |
| Lost files | Copy-then-delete, not move |
| Deploy scripts break | Update scripts in Phase 3 |
| Git history loss | Use `git mv` where possible |

---

## Success Criteria

- [ ] Each `autobot-*` folder clearly maps to one machine
- [ ] No ambiguity about where code deploys
- [ ] All tests pass after restructure
- [ ] Sync scripts work with new paths
- [ ] CLAUDE.md updated with new structure
