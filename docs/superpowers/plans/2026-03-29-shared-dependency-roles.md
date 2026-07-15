# Shared Dependency Roles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract shared infrastructure installs (nginx, Python 3.14, Node.js) into dedicated Ansible roles with a dependency resolution phase, so single-host and multi-host provisioning both work without conflicts.

**Architecture:** Three new dependency roles (`nginx`, `python312`, `nodejs`) run in a new Phase 0 of the provisioning playbook. A static `ROLE_DEPENDENCIES` map in `role_registry.py` drives automatic dependency resolution. Service roles stop installing these packages themselves. Orphan detection and guarded removal via the nodes API.

**Tech Stack:** Ansible roles (YAML), Python (FastAPI backend), existing `role_registry.py` and `setup_wizard.py`

**Spec:** `docs/superpowers/specs/2026-03-29-shared-dependency-roles-design.md`

---

### Task 1: Add ROLE_DEPENDENCIES map to role_registry.py

**Files:**
- Modify: `autobot-slm-backend/services/role_registry.py` (after `ROLE_ANSIBLE_GROUPS` ~line 376)

- [ ] **Step 1: Add the dependency map**

Add after `ROLE_ANSIBLE_GROUPS` dict (around line 376):

```python
# Static dependency map: role -> infrastructure packages required.
# Used by setup_wizard.py to compute node_dependencies for provisioning Phase 0.
# Dependencies are Ansible role names: nginx, python312, nodejs, postgresql.
ROLE_DEPENDENCIES: Dict[str, List[str]] = {
    # SLM roles
    "slm-backend": ["python312", "nginx"],
    "slm-frontend": ["nodejs", "nginx"],
    "slm-database": ["postgresql"],
    "slm-monitoring": [],
    # Service roles
    "backend": ["python312", "nginx"],
    "celery": ["python312"],
    "frontend": ["nodejs", "nginx"],
    "redis": [],
    "ai-stack": ["python312"],
    "chromadb": ["python312"],
    "browser-service": ["nodejs"],
    "npu-worker": ["python312"],
    "tts-worker": ["python312"],
    "vnc": [],
    "slm-agent": [],
}
```

- [ ] **Step 2: Verify import exists**

Ensure `List` is imported from `typing` at the top of the file (it should already be there alongside `Dict`).

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/services/role_registry.py
git commit -m "feat(roles): add ROLE_DEPENDENCIES map for shared dependency resolution (#2747)"
```

---

### Task 2: Compute node_dependencies in dynamic inventory

**Files:**
- Modify: `autobot-slm-backend/api/setup_wizard.py` (~line 219, after node_roles computation)

- [ ] **Step 1: Add dependency resolution after node_roles computation**

In `_generate_dynamic_inventory()`, after the block that sets `hosts[inv_name]["node_roles"]` (around line 226), add:

```python
        # Resolve dependencies for Phase 0 (#2747)
        from services.role_registry import ROLE_DEPENDENCIES

        for node in db_nodes:
            inv_name = node.ansible_target
            if inv_name not in hosts:
                continue
            roles = hosts[inv_name].get("node_roles", [])
            deps: set[str] = set()
            for role in roles:
                deps.update(ROLE_DEPENDENCIES.get(role, []))
            hosts[inv_name]["node_dependencies"] = sorted(deps)

            # Pending removals from extra_data
            extra = node.extra_data or {}
            pending = extra.get("pending_dep_removals", [])
            if pending:
                hosts[inv_name]["pending_dep_removals"] = pending
```

- [ ] **Step 2: Verify by checking a generated inventory**

Run manually in Python shell or add a temporary log line to confirm `node_dependencies` appears in the generated YAML.

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/api/setup_wizard.py
git commit -m "feat(setup): compute node_dependencies from ROLE_DEPENDENCIES map (#2747)"
```

---

### Task 3: Create roles/nginx Ansible role

**Files:**
- Create: `autobot-slm-backend/ansible/roles/nginx/tasks/main.yml`
- Create: `autobot-slm-backend/ansible/roles/nginx/defaults/main.yml`
- Create: `autobot-slm-backend/ansible/roles/nginx/handlers/main.yml`

- [ ] **Step 1: Create defaults**

```yaml
# autobot-slm-backend/ansible/roles/nginx/defaults/main.yml
---
nginx_worker_processes: auto
nginx_worker_connections: 1024
```

- [ ] **Step 2: Create handlers**

```yaml
# autobot-slm-backend/ansible/roles/nginx/handlers/main.yml
---
- name: Reload nginx
  ansible.builtin.systemd:
    name: nginx
    state: reloaded
  become: true

- name: Restart nginx
  ansible.builtin.systemd:
    name: nginx
    state: restarted
  become: true
```

- [ ] **Step 3: Create main tasks**

```yaml
# autobot-slm-backend/ansible/roles/nginx/tasks/main.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Shared dependency role: nginx
# Installs nginx and ensures service is running.
# Vhost configuration stays in service roles (slm_manager, backend, frontend).
---

- name: "nginx | Install nginx"
  ansible.builtin.apt:
    name: nginx
    state: present
    update_cache: true
  become: true
  tags: ['deps', 'nginx']

- name: "nginx | Ensure service is enabled and running"
  ansible.builtin.systemd:
    name: nginx
    enabled: true
    state: started
  become: true
  tags: ['deps', 'nginx']
```

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/nginx/
git commit -m "feat(ansible): create shared nginx dependency role (#2747)"
```

---

### Task 4: Create roles/python312 Ansible role

**Files:**
- Create: `autobot-slm-backend/ansible/roles/python312/tasks/main.yml`
- Create: `autobot-slm-backend/ansible/roles/python312/defaults/main.yml`

- [ ] **Step 1: Create defaults**

```yaml
# autobot-slm-backend/ansible/roles/python312/defaults/main.yml
---
python312_packages:
  - python3.14
  - python3.14-venv
  - python3.14-dev
```

- [ ] **Step 2: Create main tasks**

```yaml
# autobot-slm-backend/ansible/roles/python312/tasks/main.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Shared dependency role: Python 3.14 (deadsnakes PPA)
# Installs Python 3.14 interpreter and venv support.
# Venv creation and pip installs stay in service roles.
---

- name: "python312 | Check if Python 3.14 is available"
  ansible.builtin.command:
    cmd: python3.14 --version
  register: _py312_check
  changed_when: false
  failed_when: false
  tags: ['deps', 'python312']

- name: "python312 | Install software-properties-common"
  ansible.builtin.apt:
    name: software-properties-common
    state: present
  become: true
  when: _py312_check.rc != 0
  tags: ['deps', 'python312']

- name: "python312 | Add deadsnakes PPA"
  ansible.builtin.apt_repository:
    repo: ppa:deadsnakes/ppa
    state: present
  become: true
  when: _py312_check.rc != 0
  tags: ['deps', 'python312']

- name: "python312 | Install Python 3.14"
  ansible.builtin.apt:
    name: "{{ python312_packages }}"
    state: present
    update_cache: true
  become: true
  when: _py312_check.rc != 0
  tags: ['deps', 'python312']

- name: "python312 | Verify Python 3.14 is available"
  ansible.builtin.command:
    cmd: python3.14 --version
  changed_when: false
  tags: ['deps', 'python312']
```

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/roles/python312/
git commit -m "feat(ansible): create shared python312 dependency role (#2747)"
```

---

### Task 5: Create roles/nodejs Ansible role

**Files:**
- Create: `autobot-slm-backend/ansible/roles/nodejs/tasks/main.yml`
- Create: `autobot-slm-backend/ansible/roles/nodejs/defaults/main.yml`

- [ ] **Step 1: Create defaults**

```yaml
# autobot-slm-backend/ansible/roles/nodejs/defaults/main.yml
---
nodejs_major_version: "20"
```

- [ ] **Step 2: Create main tasks**

```yaml
# autobot-slm-backend/ansible/roles/nodejs/tasks/main.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Shared dependency role: Node.js (NodeSource)
# Installs Node.js and npm.
# npm install / npm build stays in service roles.
---

- name: "nodejs | Check if Node.js is already installed"
  ansible.builtin.command:
    cmd: node --version
  register: _node_check
  changed_when: false
  failed_when: false
  tags: ['deps', 'nodejs']

- name: "nodejs | Install prerequisites"
  ansible.builtin.apt:
    name:
      - curl
      - gnupg
      - ca-certificates
    state: present
  become: true
  when: _node_check.rc != 0
  tags: ['deps', 'nodejs']

- name: "nodejs | Check if NodeSource repo exists"
  ansible.builtin.stat:
    path: /etc/apt/sources.list.d/nodesource.list
  register: _nodesource_repo
  tags: ['deps', 'nodejs']

- name: "nodejs | Add NodeSource repository"
  ansible.builtin.shell: |
    curl -fsSL https://deb.nodesource.com/setup_{{ nodejs_major_version }}.x | bash -
  become: true
  when:
    - _node_check.rc != 0
    - not _nodesource_repo.stat.exists
  tags: ['deps', 'nodejs']

- name: "nodejs | Install Node.js"
  ansible.builtin.apt:
    name: nodejs
    state: present
    update_cache: true
  become: true
  tags: ['deps', 'nodejs']

- name: "nodejs | Verify Node.js is available"
  ansible.builtin.command:
    cmd: node --version
  changed_when: false
  tags: ['deps', 'nodejs']
```

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/roles/nodejs/
git commit -m "feat(ansible): create shared nodejs dependency role (#2747)"
```

---

### Task 6: Add Phase 0 to provision-fleet-roles.yml

**Files:**
- Modify: `autobot-slm-backend/ansible/playbooks/provision-fleet-roles.yml` (add before Phase 1)

- [ ] **Step 1: Read the current file to find exact insertion point**

Find the line with `Phase 1: Common Baseline` and add the new phase before it.

- [ ] **Step 2: Add Phase 0 block**

Insert before Phase 1:

```yaml
# -------------------------------------------------------------------
# Phase 0: Shared Dependencies (nginx, python312, nodejs)
# Resolved from ROLE_DEPENDENCIES map via node_dependencies host var.
# -------------------------------------------------------------------
- name: "Provision Phase 0: Shared Dependencies"
  hosts: all
  become: true
  gather_facts: true

  tasks:
    - name: "Deps | Install nginx"
      ansible.builtin.include_role:
        name: nginx
      when: "'nginx' in (node_dependencies | default([]))"
      tags: ['deps', 'nginx']

    - name: "Deps | Install Python 3.14"
      ansible.builtin.include_role:
        name: python312
      when: "'python312' in (node_dependencies | default([]))"
      tags: ['deps', 'python312']

    - name: "Deps | Install Node.js"
      ansible.builtin.include_role:
        name: nodejs
      when: "'nodejs' in (node_dependencies | default([]))"
      tags: ['deps', 'nodejs']

    # Orphan removals (admin-approved only)
    - name: "Deps | Remove nginx if marked for removal"
      ansible.builtin.apt:
        name: nginx
        state: absent
        purge: true
      when: "'nginx' in (pending_dep_removals | default([]))"
      tags: ['deps', 'removal']

    - name: "Deps | Remove Python 3.14 if marked for removal"
      ansible.builtin.apt:
        name:
          - python3.14
          - python3.14-venv
          - python3.14-dev
        state: absent
        purge: true
      when: "'python312' in (pending_dep_removals | default([]))"
      tags: ['deps', 'removal']

    - name: "Deps | Remove Node.js if marked for removal"
      ansible.builtin.apt:
        name: nodejs
        state: absent
        purge: true
      when: "'nodejs' in (pending_dep_removals | default([]))"
      tags: ['deps', 'removal']
```

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/playbooks/provision-fleet-roles.yml
git commit -m "feat(ansible): add Phase 0 shared dependency resolution to provisioning (#2747)"
```

---

### Task 7: Remove nginx install from slm_manager role

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml`

- [ ] **Step 1: Read current file and identify install tasks to remove**

Remove the following from the prerequisites apt task (lines 19-34):
- Remove `nginx` from the `name:` list (keep other packages like curl, gnupg, openssl, etc.)

Remove Python 3.14 tasks (lines 37-61):
- "Check if Python 3.14 is available"
- "Add deadsnakes PPA for Python 3.14"
- "Install Python 3.14"

Remove Node.js tasks (lines 79-96):
- "Check if NodeSource repo exists"
- "Add NodeSource repository for Node.js 20.x"
- "Install Node.js (includes npm)"

Keep Ansible PPA tasks (lines 66-77) — Ansible is not a shared dependency.

- [ ] **Step 2: Apply edits**

Remove `nginx` from the prerequisites list. Remove the 6 Python 3.14 and Node.js task blocks entirely.

- [ ] **Step 3: Verify no broken references**

Grep for `_py312_check`, `slm_nodesource_repo`, `_node_check` in the same file — ensure nothing else references these removed register variables.

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/slm_manager/tasks/main.yml
git commit -m "refactor(ansible): remove nginx/python312/nodejs installs from slm_manager (#2747)"
```

---

### Task 8: Remove Python 3.14 and nginx install from backend role

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/backend/tasks/main.yml`

- [ ] **Step 1: Read current file and identify install tasks to remove**

Remove these task blocks:
- "Install software-properties-common for PPA support" (lines 55-59)
- "Add deadsnakes PPA for Python 3.14" (lines 61-65)
- "Install Python 3.14 and build dependencies" (lines 67-103) — **NOTE:** this also installs build-essential, ffmpeg, tesseract, GUI/audio libs. These are backend-specific, not shared deps. Move them to a new task that installs only the non-Python packages.
- "Backend nginx | Install nginx" (line 377-382)

- [ ] **Step 2: Replace the large Python 3.14 install with backend-specific deps only**

Replace the removed "Install Python 3.14 and build dependencies" block with:

```yaml
- name: "Backend | Install backend-specific system dependencies"
  ansible.builtin.apt:
    name:
      - build-essential
      - libssl-dev
      - zlib1g-dev
      - libbz2-dev
      - libreadline-dev
      - libsqlite3-dev
      - libncursesw5-dev
      - xz-utils
      - tk-dev
      - libxml2-dev
      - libxmlsec1-dev
      - libffi-dev
      - liblzma-dev
      - git
      - curl
      # GUI / display (VNC, xvfb headless, GUI automation)
      - xvfb
      - x11-utils
      - x11-apps
      # Audio / voice processing (PyAudio, librosa, Whisper)
      - ffmpeg
      - libsndfile1
      - libsndfile1-dev
      - portaudio19-dev
      # OCR / CAPTCHA solver (tesseract, Issue #206)
      - tesseract-ocr
      - libtesseract-dev
      # Matplotlib GUI backend
      - python3-tk
    state: present
    update_cache: true
  tags: ['backend', 'packages']
```

- [ ] **Step 3: Remove the nginx install task**

Delete the "Backend nginx | Install nginx" block. Keep all nginx configuration tasks (vhost template, enable site, etc.).

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/backend/tasks/main.yml
git commit -m "refactor(ansible): remove python312/nginx installs from backend role (#2747)"
```

---

### Task 9: Remove Node.js and nginx install from frontend role

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/frontend/tasks/main.yml`

- [ ] **Step 1: Read current file and identify install tasks to remove**

Remove these task blocks:
- "Check if Node.js is already installed" (lines 49-55)
- "Install Node.js prerequisites" (lines 57-66)
- "Check if NodeSource repo exists" (lines 68-72)
- "Add NodeSource repository for Node.js" (lines 74-81)
- "Install Node.js and nginx" (lines 83-93)
- "Ensure nginx is installed" (lines 95-101)

- [ ] **Step 2: Apply edits**

Remove all 6 task blocks. The frontend role now assumes Node.js and nginx are already installed by Phase 0.

- [ ] **Step 3: Verify no broken references**

Grep for `_node_check`, `_nodesource_repo` in the same file — ensure nothing else references these removed register variables.

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/frontend/tasks/main.yml
git commit -m "refactor(ansible): remove nodejs/nginx installs from frontend role (#2747)"
```

---

### Task 10: Remove Node.js install from browser role

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/browser/tasks/main.yml`

- [ ] **Step 1: Read current file and identify install tasks to remove**

Remove these task blocks:
- "Check if Node.js is already installed" (lines 73-79)
- "Install Node.js from NodeSource" (lines 81-89)

Keep: "Install Playwright system dependencies" (lines 91-111) — those are browser-specific.

- [ ] **Step 2: Apply edits**

Remove the 2 Node.js task blocks.

- [ ] **Step 3: Verify no broken references**

Grep for `node_check` in the same file — ensure nothing else references this removed register variable.

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/browser/tasks/main.yml
git commit -m "refactor(ansible): remove nodejs install from browser role (#2747)"
```

---

### Task 11: Remove Python install from ai-stack role

**Files:**
- Modify: `autobot-slm-backend/ansible/roles/ai-stack/tasks/main.yml`

- [ ] **Step 1: Read current file and identify install tasks to remove**

Remove this task block:
- "Install AI stack dependencies" (lines 59-67) — installs python3, python3-pip, python3-venv, build-essential

Keep `build-essential` if it's the only place it's installed for ai-stack. If so, replace with:

```yaml
- name: "AI Stack | Install build dependencies"
  ansible.builtin.apt:
    name:
      - build-essential
    state: present
    update_cache: true
  tags: ['ai-stack', 'packages']
```

- [ ] **Step 2: Apply edits**

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/roles/ai-stack/tasks/main.yml
git commit -m "refactor(ansible): remove python install from ai-stack role (#2747)"
```

---

### Task 12: Add orphan detection to nodes API

**Files:**
- Modify: `autobot-slm-backend/api/nodes.py`

- [ ] **Step 1: Read the role unassign endpoint**

Find the endpoint that removes/unassigns a role from a node. Read the full function.

- [ ] **Step 2: Add orphan detection after role removal**

After a role is unassigned, add:

```python
from services.role_registry import ROLE_DEPENDENCIES

def _detect_orphaned_dependencies(
    active_roles: list[str], removed_role: str
) -> list[str]:
    """Return dependencies that are no longer needed after removing a role."""
    removed_deps = set(ROLE_DEPENDENCIES.get(removed_role, []))
    if not removed_deps:
        return []
    # Check if any remaining role still needs each dependency
    still_needed: set[str] = set()
    for role in active_roles:
        still_needed.update(ROLE_DEPENDENCIES.get(role, []))
    return sorted(removed_deps - still_needed)
```

Include `orphaned_dependencies` in the response when a role is unassigned.

- [ ] **Step 3: Add dependency removal endpoint**

```python
@router.delete("/{node_id}/dependencies/{dep_name}")
async def mark_dependency_for_removal(
    node_id: str,
    dep_name: str,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
):
    """Mark an orphaned dependency for removal on next provisioning run."""
    node = await _get_node_or_404(db, node_id)

    # Guard: check no active role needs this dependency
    active_roles = [
        nr.role_name
        for nr in await _get_active_node_roles(db, node_id)
    ]
    for role in active_roles:
        if dep_name in ROLE_DEPENDENCIES.get(role, []):
            raise HTTPException(
                status_code=409,
                detail=f"Cannot remove {dep_name}: still required by role '{role}'",
            )

    # Add to pending removals in extra_data
    extra = node.extra_data or {}
    pending = extra.get("pending_dep_removals", [])
    if dep_name not in pending:
        pending.append(dep_name)
    extra["pending_dep_removals"] = pending
    node.extra_data = extra
    await db.commit()

    return {"status": "marked_for_removal", "dependency": dep_name}
```

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/api/nodes.py
git commit -m "feat(api): add orphan detection and dependency removal guard (#2747)"
```

---

### Task 13: Deploy and test full provisioning

- [ ] **Step 1: Sync code to deployed copy**

Run the SLM deploy playbook to sync all changes:

```bash
cd /opt/autobot/code_source/autobot-slm-backend/ansible && \
ansible-playbook -i inventory/localhost.yml playbooks/deploy-slm-manager.yml --skip-tags seed,provision
```

- [ ] **Step 2: Run provisioning from setup wizard**

Open `https://<host>/slm/setup` and trigger provisioning. Verify:
- Phase 0 runs and installs nginx, python312, nodejs
- Phase 1-6 run without installing these packages themselves
- No duplicate installs or conflicts

- [ ] **Step 3: Verify services**

```bash
systemctl status nginx
python3.14 --version
node --version
systemctl status autobot-slm-backend
systemctl status redis-stack-server
```

- [ ] **Step 4: Commit any fixes discovered during testing**

```bash
git add -u
git commit -m "fix(ansible): address issues found during provisioning test (#2747)"
```
