# Ansible Role Name Conventions (#7053)

## Canonical Role Names

All `node_roles` inventory entries **must** use the canonical form below.
Short-form aliases (e.g. `backend`) are **deprecated** as of #7053.

| Canonical name            | Deploys / manages                              |
|---------------------------|------------------------------------------------|
| `autobot-backend`         | `/opt/autobot/autobot-backend/`                |
| `autobot-frontend`        | `/opt/autobot/autobot-frontend/`               |
| `autobot-ai-stack`        | `/opt/autobot/autobot-ai-stack/`               |
| `autobot-npu-worker`      | `/opt/autobot/autobot-npu-worker/`             |
| `autobot-browser-worker`  | `/opt/autobot/autobot-browser-worker/`         |
| `autobot-tts-worker`      | `/opt/autobot/autobot-tts-worker/`             |
| `vnc`                     | VNC/display — no `autobot-` prefix by convention |
| `llm`                     | LLM runtime — no `autobot-` prefix by convention |
| `redis`                   | Redis service — no `autobot-` prefix by convention |

## Deprecated Short-Form Aliases

These short forms were previously used interchangeably with the canonical
names. They are now deprecated and must not appear in new inventory entries
or gate conditions.

| Deprecated alias  | Canonical replacement       |
|-------------------|-----------------------------|
| `backend`         | `autobot-backend`           |
| `frontend`        | `autobot-frontend`          |
| `ai-stack`        | `autobot-ai-stack`          |
| `npu-worker`      | `autobot-npu-worker`        |
| `browser`         | `autobot-browser-worker`    |
| `browser-service` | `autobot-browser-worker`    |
| `tts-worker`      | `autobot-tts-worker`        |

## Why the Dual Forms Existed

Prior to #7053, `install.sh` and the fleet-seeding playbook used different
conventions: `install.sh` wrote `node_roles: [autobot-backend, vnc]` (prefixed)
while some older inventory files and gates checked for bare `backend` or
`frontend`. The `role_X_active` shared facts (introduced in #7031) bridged
this gap with OR-chains that accept both forms. The backward-compat OR-chains
remain in place; only new code must use the canonical prefix.

## Shared Role-Active Facts

New gate conditions must use the `role_X_active` boolean facts rather than
raw `node_roles` string checks. These facts are defined in two places (kept
in sync for temp-inventory compatibility — see #7050 / #7051):

- `autobot-slm-backend/ansible/inventory/group_vars/all.yml`
  (loaded automatically for static inventories)
- `autobot-slm-backend/ansible/playbooks/vars/role_active_facts.yml`
  (loaded explicitly via `vars_files:` for temp inventories)

Available facts:

| Fact                    | True when…                                           |
|-------------------------|------------------------------------------------------|
| `role_backend_active`   | host carries `autobot-backend` (or legacy `backend`) |
| `role_frontend_active`  | host carries `autobot-frontend` (or legacy `frontend`) |
| `role_ai_stack_active`  | host carries `autobot-ai-stack` (or legacy `ai-stack`) |
| `role_npu_worker_active`| host carries `autobot-npu-worker` (or legacy `npu-worker`) |
| `role_browser_active`   | host carries `autobot-browser-worker` (or legacy `browser`/`browser-service`) |
| `role_tts_worker_active`| host carries `autobot-tts-worker` (or legacy `tts-worker`) |
| `role_slm_active`       | host is the SLM manager node (by hostname or group)  |
| `role_redis_active`     | host carries `redis` (or group membership)           |
| `role_vnc_active`       | host carries `vnc` (or group membership)             |
| `role_llm_active`       | host carries `llm` (or group membership)             |

## Pre-Commit Enforcement

`tools/lint/check_canonical_role_names.py` (registered in `.pre-commit-config.yaml`)
blocks new gate conditions that check short-form role names directly in
`node_roles`:

```yaml
# BLOCKED — use role_backend_active instead:
when: "'backend' in node_roles"

# ALLOWED — canonical form in node_roles:
when: "'autobot-backend' in node_roles"

# PREFERRED — use the shared fact:
when: role_backend_active
```

Files in the backward-compat allowlist (`group_vars/all.yml`,
`vars/role_active_facts.yml`) are excluded from this check because they
must maintain the OR-chains for existing hosts.

## Adding a New Role

When adding a new role, update **all** of the following:

1. Choose a canonical name: `autobot-<service-name>` (or a bare name if
   the role has no `autobot-` equivalent by convention, like `vnc`/`llm`).
2. Add the canonical name to the table in this document.
3. Add a `role_<name>_active` fact to **both**:
   - `inventory/group_vars/all.yml` (under SHARED ROLE-ACTIVE FACTS)
   - `playbooks/vars/role_active_facts.yml`
4. If the role has a deprecated short-form alias, add it to the
   `_role_aliases` dict in `group_vars/all.yml` and to
   `DEPRECATED_SHORT_FORMS` in `tools/lint/check_canonical_role_names.py`.
5. Add the role to `seed-fleet-nodes.yml` `node_role_map` using the
   canonical name.
