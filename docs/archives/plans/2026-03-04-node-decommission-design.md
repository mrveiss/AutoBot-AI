# SLM Node Decommission Feature

**Date:** 2026-03-04
**Issue:** #1369
**Status:** Approved
**Author:** mrveiss

## Problem

Removing a node from the AutoBot fleet requires manual SSH work: stopping services, deleting venvs, cleaning orphan packages, removing systemd units. The existing `remove-role.yml` only removes the systemd unit file — it leaves application code, venvs (often 4-8GB of nvidia/torch), pip caches, and user-level packages on disk.

There is no single "undeploy this node" action in the SLM UI.

## Goals

1. Fix per-role removal to also clean disk (code, venvs, caches)
2. Add a full node decommission flow: one action to safely remove all AutoBot software from a node
3. Block decommission when required roles have no other host — force migration first
4. Provide audit trail and optional backup before destruction

## Non-Goals

- Auto-migration of roles (user must migrate manually via existing UI)
- OS-level cleanup (uninstalling system packages, removing users)
- Decommissioning the SLM Manager node (.19)

---

## Design

### 1. Fix `remove-role.yml` — Disk Cleanup

Current behavior: stops service, removes systemd unit file. That's it.

**Add after unit removal:**

```yaml
- name: Remove role application directory
  file:
    path: "/opt/autobot/{{ role_target_dir }}"
    state: absent
  when: role_target_dir is defined

- name: Remove role venv if separate from app dir
  file:
    path: "/opt/autobot/{{ role_target_dir }}/venv"
    state: absent
  when: role_target_dir is defined

- name: Clean orphan user-level Python packages
  file:
    path: "/home/{{ service_user | default('autobot') }}/.local/lib"
    state: absent

- name: Clean pip cache for service user
  file:
    path: "/home/{{ service_user | default('autobot') }}/.cache/pip"
    state: absent
```

The `role_target_dir` variable maps from role name to directory name. This mapping will be added as an extra var passed by the backend (derived from `Role.target_path`).

### 2. New `decommission-node.yml` Playbook

Runs on the target node. Phases:

1. **Optional backup** — if `backup_before_decommission=true`:
   - Archive all data dirs to `/opt/autobot/backups/decommission-<timestamp>/`
   - Data dir map: redis, postgresql, ai-stack models, etc.

2. **Stop all AutoBot services:**
   ```yaml
   - name: Find all autobot services
     shell: systemctl list-units 'autobot-*' --no-pager --plain --no-legend | awk '{print $1}'
     register: autobot_services

   - name: Stop all autobot services
     systemd:
       name: "{{ item }}"
       state: stopped
       enabled: false
     loop: "{{ autobot_services.stdout_lines }}"
   ```

3. **Remove all systemd unit files:**
   ```yaml
   - name: Remove autobot service files
     shell: rm -f /etc/systemd/system/autobot-*.service

   - name: Reload systemd
     systemd:
       daemon_reload: true
   ```

4. **Remove application code:**
   ```yaml
   - name: Remove /opt/autobot contents (preserve backups if present)
     shell: |
       find /opt/autobot -mindepth 1 -maxdepth 1 ! -name 'backups' -exec rm -rf {} +
   ```

5. **Remove data and logs:**
   ```yaml
   - name: Remove autobot data
     file:
       path: "{{ item }}"
       state: absent
     loop:
       - /var/lib/autobot
       - /var/log/autobot
   ```

6. **Clean user packages and caches:**
   ```yaml
   - name: Remove orphan user Python packages
     shell: rm -rf /home/*/.local/lib/python* /home/*/.cache/pip
   ```

7. **Remove SLM agent** (so the node stops phoning home):
   ```yaml
   - name: Stop and disable SLM agent
     systemd:
       name: autobot-slm-agent
       state: stopped
       enabled: false
     ignore_errors: true

   - name: Remove SLM agent files
     file:
       path: /opt/autobot/autobot-slm-agent
       state: absent
   ```

### 3. Backend API

#### Preflight endpoint: `GET /api/nodes/{node_id}/decommission/preflight`

Response schema:

```python
class DecommissionPreflight(BaseModel):
    can_proceed: bool
    must_migrate: list[dict]      # required roles with no other active host
    should_migrate: list[dict]    # degraded_without roles with no other active host
    safe_to_remove: list[dict]    # optional or redundant roles
```

Logic:
1. Fetch all `NodeRole` records for the node
2. For each role:
   - Query `NodeRole` table for OTHER nodes running the same role with status `active`
   - If `Role.required=true` and no other active host -> `must_migrate`
   - If `Role.degraded_without` is set and no other active host -> `should_migrate`
   - Otherwise -> `safe_to_remove`
3. `can_proceed = len(must_migrate) == 0`

#### Decommission endpoint: `POST /api/nodes/{node_id}/decommission`

Request:

```python
class DecommissionRequest(BaseModel):
    backup: bool = True
    confirm_node_id: str  # Must match node_id for safety
```

Flow:
1. Validate `confirm_node_id == node_id`
2. Block if `node_id` is SLM Manager
3. Re-run preflight server-side — block if `must_migrate` is non-empty
4. Create `Deployment` record for audit
5. Run `decommission-node.yml` via `PlaybookExecutor` with `--limit node_id`
6. On success:
   - Delete all `NodeRole` records for node
   - Delete all `NodeCodeVersion` records for node
   - Set `Node.status = 'decommissioned'`
   - Broadcast `node_decommissioned` WebSocket event
7. On failure: update Deployment record with error, leave node in current state

#### NodeStatus addition:

```python
DECOMMISSIONED = "decommissioned"
```

Decommissioned nodes remain in DB for audit. Can be re-enrolled via existing enroll flow.

### 4. Frontend

#### New component: `DecommissionModal.vue`

Opened from NodeCard action menu -> "Decommission".

**Layout:**

```
+---------------------------------------------+
|  ! Decommission Node: 04-NPU-Worker        |
|  IP: 172.16.168.22                          |
|                                             |
|  This will permanently remove all AutoBot   |
|  software and data from this node.          |
|                                             |
|  -- Role Preflight Check --                 |
|                                             |
|  [red] Must migrate first:                  |
|     redis - required, only instance [Migrate]|
|                                             |
|  [yellow] Recommended to migrate:           |
|     tts-worker - voice degraded  [Migrate]  |
|                                             |
|  [green] Safe to remove:                    |
|     npu-worker - optional, no hardware      |
|     slm-agent - removed during decommission |
|                                             |
|  -- Options --                              |
|  [x] Backup data before removal             |
|                                             |
|  -- Confirm --                              |
|  Type "04-NPU-Worker" to confirm:           |
|  [____________________________]             |
|                                             |
|  [Cancel]              [Decommission] (red) |
|  (button disabled until name typed +        |
|   no red items remain)                      |
+---------------------------------------------+
```

**States:**
- Loading: fetching preflight
- Blocked: must_migrate items present — Decommission button disabled
- Ready: all red items resolved, waiting for type-to-confirm
- Running: playbook executing, progress bar via WebSocket
- Complete: success message, node removed from active fleet view
- Failed: error message with playbook output

#### NodeCard changes:
- Add "Decommission" to action dropdown (after "Reboot", with separator)
- Red text/icon to signal destructive action
- Hidden for SLM Manager node

#### FleetOverview changes:
- Wire `handleNodeAction('decommission', node)` to open DecommissionModal
- Decommissioned nodes show greyed out with "Re-enroll" action

#### useRoles.ts additions:
```typescript
async function decommissionPreflight(nodeId: string): Promise<DecommissionPreflight>
async function decommissionNode(nodeId: string, backup: boolean, confirmNodeId: string): Promise<void>
```

---

## File Changes Summary

| Layer | File | Change |
|-------|------|--------|
| Ansible | `playbooks/remove-role.yml` | Add disk cleanup steps (code, venvs, caches) |
| Ansible | `playbooks/decommission-node.yml` | **New** — full node cleanup playbook |
| Backend | `models/database.py` | Add `DECOMMISSIONED` to `NodeStatus` |
| Backend | `api/nodes.py` | Add `decommission` + `decommission/preflight` endpoints |
| Frontend | `components/fleet/DecommissionModal.vue` | **New** — modal with preflight gate, migration links, type-to-confirm |
| Frontend | `components/fleet/NodeCard.vue` | Add "Decommission" to action menu |
| Frontend | `views/FleetOverview.vue` | Wire decommission action handler |
| Frontend | `composables/useRoles.ts` | Add `decommissionPreflight()` + `decommissionNode()` |

## Safety Constraints

- SLM Manager (.19) cannot be decommissioned (hardcoded block)
- Server-side preflight re-validation (never trust frontend alone)
- Type-to-confirm prevents accidental clicks
- Required roles must be migrated before decommission unlocks
- Backup enabled by default for data-bearing nodes
- Audit trail via Deployment record
- Decommissioned nodes stay in DB (soft-delete) for re-enrollment
