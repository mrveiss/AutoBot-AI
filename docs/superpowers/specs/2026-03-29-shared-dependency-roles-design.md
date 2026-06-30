# Shared Dependency Roles Design

**Date:** 2026-03-29
**Issue:** #2747 (provisioning), single-host install support
**Status:** Approved

## Problem

Multiple service roles independently install the same infrastructure packages (nginx, Python 3.14, Node.js). On multi-node deployments this is harmless — each node installs its own. On single-host deployments, roles conflict: duplicate nginx configs, redundant PPA additions, and no way to know if a dependency can be safely removed when a role is unassigned.

### Current State

| Dependency | Installed By |
|---|---|
| nginx | `slm_manager`, `backend`, `frontend` |
| Python 3.14 | `slm_manager`, `backend`, `backend_services` |
| Node.js 20 | `slm_manager`, `frontend`, `browser`, `monitoring` |
| PostgreSQL | `postgresql` (already standalone) |
| Redis | `redis` (already standalone) |

## Design

### 1. Static Dependency Map

Add `ROLE_DEPENDENCIES` to `services/role_registry.py`:

```python
ROLE_DEPENDENCIES: dict[str, list[str]] = {
    # SLM roles
    "slm-backend":    ["python312", "nginx"],
    "slm-frontend":   ["nodejs", "nginx"],
    "slm-database":   ["postgresql"],
    "slm-monitoring": [],
    # Service roles
    "backend":        ["python312", "nginx"],
    "celery":         ["python312"],
    "frontend":       ["nodejs", "nginx"],
    "redis":          [],
    "ai-stack":       ["python312"],
    "chromadb":       ["python312"],
    "browser-service":["nodejs"],
    "npu-worker":     ["python312"],
    "vnc":            [],
    "slm-agent":      [],
}
```

Dependencies are infrastructure packages: `nginx`, `python312`, `nodejs`, `postgresql`. Redis and PostgreSQL are already standalone Ansible roles that provision themselves.

### 2. New Dependency Ansible Roles

Extract install logic from existing service roles into three new roles:

**`roles/nginx/`** — extracted from `slm_manager` and `frontend`
- Install nginx package
- Ensure service enabled
- Base config (worker_processes, etc.)
- Does NOT configure vhosts (stays in service roles)

**`roles/python312/`** — extracted from `slm_manager` and `backend`
- Add deadsnakes PPA
- Install python3.14, python3.14-venv, python3.14-dev
- Does NOT create venvs (stays in service roles)

**`roles/nodejs/`** — extracted from `slm_manager`, `frontend`, `browser`
- Add NodeSource 20.x repo
- Install nodejs (includes npm)
- Does NOT run npm build (stays in service roles)

`postgresql` and `redis` already exist as standalone roles — no changes needed.

After extraction, service roles remove their install tasks and assume the dependency is present.

### 3. Provisioning Phase 0

Add a new phase at the start of `provision-fleet-roles.yml`:

```yaml
- name: "Provision Phase 0: Shared Dependencies"
  hosts: all
  become: true
  gather_facts: true
  tasks:
    - name: "Deps | Install nginx"
      ansible.builtin.include_role:
        name: nginx
      when: "'nginx' in (node_dependencies | default([]))"

    - name: "Deps | Install Python 3.14"
      ansible.builtin.include_role:
        name: python312
      when: "'python312' in (node_dependencies | default([]))"

    - name: "Deps | Install Node.js"
      ansible.builtin.include_role:
        name: nodejs
      when: "'nodejs' in (node_dependencies | default([]))"

    # Removals
    - name: "Deps | Remove nginx if marked"
      ansible.builtin.apt:
        name: nginx
        state: absent
        purge: true
      when: "'nginx' in (pending_dep_removals | default([]))"

    - name: "Deps | Remove Python 3.14 if marked"
      ansible.builtin.apt:
        name: [python3.14, python3.14-venv, python3.14-dev]
        state: absent
        purge: true
      when: "'python312' in (pending_dep_removals | default([]))"

    - name: "Deps | Remove Node.js if marked"
      ansible.builtin.apt:
        name: nodejs
        state: absent
        purge: true
      when: "'nodejs' in (pending_dep_removals | default([]))"
```

The `node_dependencies` variable is computed by `setup_wizard.py` in the dynamic inventory — it resolves `ROLE_DEPENDENCIES` for all roles assigned to each node, deduplicates, and sets it as a host var:

```yaml
<backend-ip>:
  node_roles: [backend, frontend, redis, ai-stack, ...]
  node_dependencies: [nginx, python312, nodejs]
  pending_dep_removals: []
```

### 4. Orphan Detection and Removal Guard

**No schema changes.** Dependencies tracked implicitly via the static map. Pending removals stored in `Node.extra_data` JSON field.

**When a role is unassigned from a node (`nodes.py`):**
1. Look up `ROLE_DEPENDENCIES` for the removed role
2. For each dependency, check if any remaining active role on that node still needs it
3. If not needed → include in API response as `orphaned_dependencies: ["nodejs"]`
4. Frontend shows: "Orphaned — mark for removal?"

**New endpoint: `DELETE /api/nodes/{id}/dependencies/{dep_name}`**
- Checks `ROLE_DEPENDENCIES` — if ANY active role on this node still needs it → `409 Conflict`
- If truly orphaned → adds to `pending_removals` list in `Node.extra_data`
- Next provisioning run reads `pending_dep_removals` and executes removal

**Guard logic (pseudocode):**
```python
def can_remove_dependency(node_id: str, dep_name: str) -> bool:
    active_roles = get_active_roles(node_id)
    for role in active_roles:
        if dep_name in ROLE_DEPENDENCIES.get(role, []):
            return False  # Still needed
    return True
```

### 5. Files Changed

**New Ansible roles (3):**
- `roles/nginx/tasks/main.yml` — install nginx, base config
- `roles/python312/tasks/main.yml` — deadsnakes PPA, install python3.14
- `roles/nodejs/tasks/main.yml` — NodeSource repo, install nodejs

**Modified Ansible roles (5) — remove install tasks:**
- `roles/slm_manager/tasks/main.yml` — remove nginx, python312, nodejs install
- `roles/backend/tasks/main.yml` — remove python312 install
- `roles/frontend/tasks/main.yml` — remove nodejs install
- `roles/browser/tasks/main.yml` — remove nodejs install
- `roles/ai-stack/tasks/main.yml` — remove python install

**Modified provisioning:**
- `playbooks/provision-fleet-roles.yml` — add Phase 0
- `api/setup_wizard.py` — compute `node_dependencies` and `pending_dep_removals`

**Modified backend code:**
- `services/role_registry.py` — add `ROLE_DEPENDENCIES`
- `api/nodes.py` — orphan detection on role unassign, DELETE endpoint

**Not changed:**
- `roles/postgresql/` — already standalone
- `roles/redis/` — already standalone
- Database schema — no changes (uses existing `extra_data` JSON)
