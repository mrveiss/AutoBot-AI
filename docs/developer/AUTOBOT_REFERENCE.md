# AutoBot Reference

> Operational reference for the AutoBot fleet. For development rules see `CLAUDE.md`.

---

## Project Stack

**Python (Backend, Ansible, SLM):**
- After ANY Python changes: `ruff check <file>`
- Run tests: `python -m pytest <test-file> -v`
- Common issues: E501 (line length), F821 (undefined names), bare excepts

**TypeScript (Frontend - Vue 3):**
- After ANY TypeScript changes: `npm run type-check` or `npx tsc --noEmit`
- After ANY Vue changes: `npm run lint`
- Build verification: `npm run build`
- Common issues: Type mismatches, unused imports, missing interface definitions

**YAML (Ansible, Config):**
- Syntax check: `ansible-playbook --syntax-check <playbook>`
- Lint: `ansible-lint <playbook>`
- Common issues: Indentation, missing required keys, invalid variable references

**Build Check Pattern:**
```bash
ruff check autobot-backend/path/to/changed/file.py
cd autobot-frontend && npm run type-check && npm run lint
cd autobot-slm-backend/ansible && ansible-playbook playbooks/<playbook>.yml --syntax-check
```

---

## Infrastructure

### Service Layout

| Service | IP:Port | Component | Purpose |
|---------|---------|-----------|---------|
| SLM Server | 172.16.168.19:443 | `autobot-slm-backend/` + `autobot-slm-frontend/` | SLM backend + admin UI (nginx+SSL) |
| Main (WSL) | 172.16.168.20:8001 | `autobot-backend/` | Backend API + VNC (6080) |
| Frontend VM | 172.16.168.21:443 | `autobot-frontend/` | User frontend (nginx+SSL, production build) |
| NPU VM | 172.16.168.22:8081 | `autobot-npu-worker/` | Hardware AI acceleration |
| Redis VM | 172.16.168.23:6379 | - | Data layer (Redis Stack) |
| AI Stack VM | 172.16.168.24:8080 | - | AI processing |
| Browser VM | 172.16.168.25:3000 | `autobot-browser-worker/` | Playwright automation |
| LLM CPU | 172.16.168.26 | - | LLM CPU node (05-LLM-CPU, role: llm-cpu) |
| Reserved | 172.16.168.27 | - | (Unassigned) |

### Component Architecture

| Directory | Deploys To | Description |
|-----------|------------|-------------|
| `autobot-backend/` | 172.16.168.20 (Main) | Core AutoBot backend - AI agents, chat, tools |
| `autobot-frontend/` | 172.16.168.21 (Frontend VM) | User chat interface (Vue 3, nginx+SSL) |
| `autobot-slm-backend/` | 172.16.168.19 (SLM) | SLM backend - Fleet management, monitoring |
| `autobot-slm-frontend/` | 172.16.168.19 (SLM) | SLM admin dashboard - Vue 3 UI (nginx+SSL) |
| `autobot-npu-worker/` | 172.16.168.22 (NPU) | NPU acceleration worker |
| `autobot-browser-worker/` | 172.16.168.25 (Browser) | Playwright automation worker |
| `autobot-shared/` | All backends | Common utilities (redis, config, logging) |
| `autobot-infrastructure/` | Dev machine | Per-role infrastructure (not deployed) |

**Critical project structure rules:**
- The SLM frontend is in `autobot-slm-frontend/`, NOT `autobot-vue`
- Worktrees: `../worktrees/issue-<number>/`
- Ansible playbooks and roles: `autobot-slm-backend/ansible/`
- Primary working branch: `Dev_new_gui`
- Test files are colocated next to source files (not in a separate `tests/` directory)
- Never use stale `from src.` imports for migrated modules

### Infrastructure Directory Structure

```text
autobot-infrastructure/
├── autobot-backend/
├── autobot-frontend/
├── autobot-slm-backend/
├── autobot-slm-frontend/
├── autobot-npu-worker/
├── autobot-browser-worker/
└── shared/
    ├── scripts/
    ├── certs/
    ├── config/
    ├── docker/
    ├── mcp/
    ├── tools/
    ├── tests/
    └── analysis/
```

---

## Deployment

### Sync Commands

```bash
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh main autobot-backend/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh frontend autobot-frontend/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh slm autobot-slm-backend/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh slm autobot-slm-frontend/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh npu autobot-npu-worker/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh browser autobot-browser-worker/
```

### Ansible Deployment (PRIMARY METHOD)

**23 Ansible roles** in `autobot-slm-backend/ansible/roles/`:
- Infrastructure: `common`, `dns`, `distributed_setup`, `time_sync`
- Services: `backend`, `frontend`, `redis`, `postgresql`, `monitoring`
- AI/ML: `llm`, `npu-worker`, `ai-stack`, `agent_config`
- Security: `service_auth`, `access_control`, `centralized_logging`
- Management: `slm_manager`, `slm_agent`, `browser`, `vnc`

**Before multi-step deployments:**
- Verify SSH + sudo: `ansible all -m ping` and `ansible all -m command -a "sudo id"`
- Verify all target hosts appear in inventory — missing hosts = silent partial deployment
- Use SLM service management (`/orchestration` or `slm-service-control.yml`) to restart fleet services

**Common Playbooks:**
```bash
cd autobot-slm-backend/ansible

ansible-playbook playbooks/deploy-full.yml
ansible-playbook playbooks/slm-service-control.yml -e "service=autobot-backend action=restart"
ansible-playbook playbooks/deploy-full.yml --tags frontend,backend
ansible-playbook playbooks/deploy-full.yml --limit slm_server
```

**Infrastructure as Code (MANDATORY):** ALL configuration changes MUST go through Ansible - NO exceptions. Direct VM edits are lost on rebuild and overwritten by Ansible.

Workflow: Edit Ansible templates locally → commit → deploy via Ansible → verify.

**Configuration Change Workflow:**

| Change Type | Ansible Location | Deployment Command |
|-------------|------------------|-------------------|
| Service files (systemd) | `roles/*/templates/*.service.j2` | `ansible-playbook deploy-full.yml --tags backend` |
| Environment variables | `roles/*/templates/.env.j2` or `defaults/main.yml` | `ansible-playbook deploy-full.yml --tags backend` |
| Nginx config | `roles/frontend/templates/nginx.conf.j2` | `ansible-playbook deploy-full.yml --tags frontend,nginx` |
| System packages | `roles/common/tasks/main.yml` | `ansible-playbook deploy-full.yml --tags common` |
| Database credentials | `roles/postgresql/defaults/main.yml` | `ansible-playbook deploy-full.yml --tags postgresql` |
| Redis config | `roles/redis/templates/redis.conf.j2` | `ansible-playbook deploy-full.yml --tags redis` |
| TLS certificates | `roles/slm_manager/tasks/tls.yml` | `ansible-playbook deploy-full.yml --tags tls` |

**Emergency Override (use ONLY in critical production incidents):**

1. Make the temporary change to fix the incident
2. Verify it resolved the incident
3. Immediately replicate the change in Ansible
4. Deploy Ansible to overwrite the manual change
5. Close the issue once Ansible matches production

### Frontend Deployment

- `.19` serves SLM admin frontend via nginx+SSL (production build)
- `.21` serves User frontend via nginx+SSL (production build)
- **FORBIDDEN**: `npm run dev` on any VM — production builds only
- Ansible: `ansible-playbook playbooks/deploy-full.yml --tags frontend`
- Manual sync: `./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh frontend autobot-frontend/`

### Local-Only Development

**NEVER edit on remote VMs** — no version control, no backup, VMs are ephemeral.

1. Edit in `/home/kali/Desktop/AutoBot/`
2. Deploy via Ansible or sync script

---

## Release Channels

- **stable**: Tagged releases only (`vYYYY.M.D`)
- **beta**: Prerelease tags (`vYYYY.M.D-beta.N`)
- **dev**: Moving head on `main` (no tag)

---

## Quick Commands

```bash
# Health checks
# NOTE: .20 must be tested from another VM (WSL2 loopback limitation)
ssh autobot@172.16.168.19 'curl --insecure https://172.16.168.20:8443/api/health'
redis-cli -h 172.16.168.23 ping

# Ansible Deployment
cd autobot-slm-backend/ansible
ansible-playbook playbooks/deploy-full.yml
ansible-playbook playbooks/slm-service-control.yml -e "service=autobot-backend action=restart"

# Manual sync
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh main autobot-backend/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh frontend autobot-slm-frontend/
./autobot-infrastructure/shared/scripts/utilities/sync-to-vm.sh slm autobot-slm-backend/

# Memory MCP
mcp__memory__search_nodes --query "keywords"
mcp__memory__create_entities --entities '[{"name": "...", "entityType": "...", "observations": [...]}]'
```

---

## Documentation

**Key docs:**
- [`docs/developer/PHASE_5_DEVELOPER_SETUP.md`](PHASE_5_DEVELOPER_SETUP.md)
- [`docs/api/COMPREHENSIVE_API_DOCUMENTATION.md`](../api/COMPREHENSIVE_API_DOCUMENTATION.md)
- [`docs/system-state.md`](../system-state.md)

**Guides:** `docs/developer/` — HARDCODING_PREVENTION, REDIS_CLIENT_USAGE, UTF8_ENFORCEMENT, INFRASTRUCTURE_DEPLOYMENT, SSOT_CONFIG_GUIDE
