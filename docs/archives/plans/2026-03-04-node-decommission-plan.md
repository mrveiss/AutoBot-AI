# Node Decommission Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a full "Decommission Node" action to SLM that safely removes all AutoBot software from a fleet node, with preflight migration gate for required roles.

**Architecture:** Backend-first. Ansible playbooks first (can be tested standalone), then backend API endpoints, then frontend modal. Each layer commits independently.

**Tech Stack:** Ansible YAML, Python/FastAPI (async, SQLAlchemy), Vue 3/TypeScript, Tailwind CSS.

**Issue:** #1369
**Design:** `docs/plans/2026-03-04-node-decommission-design.md`
**Branch:** `Dev_new_gui`

---

## Task 1: Add DECOMMISSIONED to NodeStatus enum

**Files:**
- Modify: `autobot-slm-backend/models/database.py:34-43`
- Modify: `autobot-slm-frontend/src/components/fleet/NodeCard.vue:28-40`

**Step 1:** Add `DECOMMISSIONED = "decommissioned"` after MAINTENANCE in NodeStatus enum.

**Step 2:** Add `case 'decommissioned': return 'bg-gray-300'` to NodeCard statusClass.

**Step 3:** Commit: `feat(slm): add DECOMMISSIONED node status (#1369)`

---

## Task 2: Add disk cleanup to remove-role.yml

**Files:**
- Modify: `autobot-slm-backend/ansible/playbooks/remove-role.yml`
- Modify: `autobot-slm-backend/api/nodes.py:902-932`

**Step 1:** Add DISK CLEANUP section to remove-role.yml after STOP AND REMOVE SERVICE, before SUMMARY. Three tasks: remove role_target_dir, clean .local/lib, clean .cache/pip.

**Step 2:** Replace `_get_role_service_name` with `_get_role_service_and_path` returning tuple of (service_name, target_path).

**Step 3:** Update `_run_role_removal` to accept `target_path` param and pass as `role_target_dir` extra var.

**Step 4:** Update caller in `remove_role_from_node` to use new function signature.

**Step 5:** Verify: `cd autobot-slm-backend/ansible && ansible-playbook playbooks/remove-role.yml --syntax-check`

**Step 6:** Commit: `feat(slm): add disk cleanup to remove-role playbook (#1369)`

---

## Task 3: Create decommission-node.yml playbook

**Files:**
- Create: `autobot-slm-backend/ansible/playbooks/decommission-node.yml`

6-phase playbook:
1. Optional backup (archive all_data_dirs to /opt/autobot/backups/decommission-timestamp/)
2. Stop all autobot/slm-agent/redis/ollama services
3. Remove systemd unit files + daemon-reload
4. Remove /opt/autobot/* (preserve backups dir)
5. Remove /var/lib/autobot, /var/log/autobot, /etc/autobot
6. Clean ~/.local/lib/python*, ~/.cache/pip, ~/.cache/huggingface in all home dirs

Optional var: backup_before_decommission (default false).

**Step 1:** Write full playbook.

**Step 2:** Verify: `cd autobot-slm-backend/ansible && ansible-playbook playbooks/decommission-node.yml --syntax-check`

**Step 3:** Commit: `feat(slm): add decommission-node Ansible playbook (#1369)`

---

## Task 4: Add backend preflight + decommission endpoints

**Files:**
- Modify: `autobot-slm-backend/models/schemas.py`
- Modify: `autobot-slm-backend/api/nodes.py`

**Step 1:** Add Pydantic schemas to schemas.py: DecommissionRequest (backup bool, confirm_node_id str), DecommissionRoleInfo (role_name, display_name, reason), DecommissionPreflightResponse (can_proceed, must_migrate, should_migrate, safe_to_remove).

**Step 2:** Add `GET /{node_id}/decommission/preflight` endpoint to nodes.py. Insert after _parse_backup_path (~line 943), before delete_node. Logic: block SLM Manager, fetch node roles, for each role check Role.required and degraded_without against other active NodeRole records. Return classification.

**Step 3:** Add `POST /{node_id}/decommission` endpoint. Validate confirm_node_id match, block SLM Manager, re-run preflight server-side, create Deployment audit record, execute decommission-node.yml via PlaybookExecutor, on success delete NodeRole + NodeCodeVersion records, set status DECOMMISSIONED.

**Step 4:** Add imports: DecommissionRequest from models.schemas, NodeCodeVersion from models.database.

**Step 5:** Verify: `cd autobot-slm-backend && python -c "from api.nodes import router; print('OK')"`

**Step 6:** Commit: `feat(slm): add decommission preflight + execute endpoints (#1369)`

---

## Task 5: Add decommission functions to useRoles.ts

**Files:**
- Modify: `autobot-slm-frontend/src/composables/useRoles.ts`

**Step 1:** Add interfaces after line 104: DecommissionRoleInfo (role_name, display_name, reason), DecommissionPreflight (can_proceed, must_migrate, should_migrate, safe_to_remove).

**Step 2:** Add functions before return reactive: decommissionPreflight(nodeId) -> GET /api/nodes/{id}/decommission/preflight, decommissionNode(nodeId, backup, confirmNodeId) -> POST /api/nodes/{id}/decommission.

**Step 3:** Expose both in return reactive object.

**Step 4:** Commit: `feat(slm): add decommission API functions to useRoles (#1369)`

---

## Task 6: Create DecommissionModal.vue

**Files:**
- Create: `autobot-slm-frontend/src/components/fleet/DecommissionModal.vue`

Props: node (SLMNode with node_id, hostname, ip_address). Emits: close, decommissioned.

States: loading (preflight fetch), blocked (must_migrate present), ready (confirm input), running (playbook executing), complete, failed.

UI Layout:
- Fixed overlay + centered white card (match RoleManagementModal pattern)
- Red warning banner: "This will permanently remove all AutoBot software"
- Three role sections with colored left borders (border-l-4):
  - Red (must_migrate): "Must migrate first" with [Migrate] buttons
  - Yellow (should_migrate): "Recommended to migrate" with [Migrate] [Skip] buttons
  - Green (safe_to_remove): "Safe to remove" - info only
- Backup checkbox (default on)
- Type-to-confirm input: "Type {node_id} to confirm"
- Red Decommission button (disabled until must_migrate empty + confirm matches)
- Gray Cancel button
- Loading spinner during preflight
- Progress indicator during execution

**Step 1:** Write full component.

**Step 2:** Type-check: `cd autobot-slm-frontend && npx vue-tsc --noEmit`

**Step 3:** Commit: `feat(slm): add DecommissionModal component (#1369)`

---

## Task 7: Wire decommission into NodeCard + FleetOverview

**Files:**
- Modify: `autobot-slm-frontend/src/components/fleet/NodeCard.vue:205-211`
- Modify: `autobot-slm-frontend/src/views/FleetOverview.vue`

**Step 1:** Add Decommission button to NodeCard dropdown before existing hr + Delete button. Red text (text-red-600), circle-slash SVG icon. v-if: not decommissioned and not SLM Manager.

**Step 2:** In FleetOverview: import DecommissionModal, add showDecommissionModal ref, add 'decommission' case to handleNodeAction switch, add handleDecommissioned and closeDecommissionModal handlers, add modal to template.

**Step 3:** Verify: `cd autobot-slm-frontend && npm run build`

**Step 4:** Commit: `feat(slm): wire decommission action into fleet UI (#1369)`

---

## Task 8: Sync, build, and verify end-to-end

**Step 1:** Sync backend to .19: `sync-to-vm.sh 19 autobot-slm-backend /opt/autobot/autobot-slm-backend`
**Step 2:** Restart: `ssh autobot@172.16.168.19 "sudo systemctl restart autobot-slm-backend"`
**Step 3:** Verify playbook exists on .19
**Step 4:** Sync frontend to .21 + build
**Step 5:** Test preflight: `curl -sk .../api/nodes/04-NPU-Worker/decommission/preflight`
**Step 6:** Test SLM Manager block: expect 403
**Step 7:** Test UI in browser
**Step 8:** Commit any fixes

---

## Task 9: Close issue

Add closing comment summarizing changes. Run `gh issue close 1369`.
