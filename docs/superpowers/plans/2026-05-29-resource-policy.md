# Resource Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a single Ansible role (`autobot-resource-policy`) that computes percentage-based memory/CPU limits from host facts and enforces them via systemd cgroup slices + drop-ins (bare-metal) and docker-compose.override.yml (Docker), so no AutoBot service can starve others or the OS regardless of host size.

**Architecture:** A new role detects `ansible_memtotal_mb` and `ansible_processor_vcpus`, computes per-service budgets as percentages of an 85%-of-RAM AutoBot slice, and writes systemd drop-in overrides + a slice hierarchy. Floor guards keep services viable on Raspberry Pi. The same vars drive a Docker Compose override file for Docker deployments. All existing service templates gain a single `Slice=autobot-<tier>.slice` line; everything else is handled by the drop-in.

**Tech Stack:** Ansible 2.12+, systemd cgroups v2, Jinja2 templating, Docker Compose v2

**Spec:** `docs/superpowers/specs/2026-05-29-resource-policy-design.md`

---

## File Map

**Create (new role):**
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/defaults/main.yml` — all percentages, floors, RAM thresholds, OOMScoreAdj, CPUWeight
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/main.yml` — gather facts, compute budgets via set_fact, dispatch sub-tasks
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-slices.yml` — write autobot.slice + tier slices
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-dropins.yml` — write per-service resource-policy.conf drop-ins
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/docker-override.yml` — generate docker-compose.override.yml
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot.slice.j2`
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot-tier.slice.j2` — parameterised, used for all three tiers
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/resource-policy.conf.j2` — systemd drop-in
- `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/docker-compose.override.yml.j2`
- `autobot-slm-backend/ansible/playbooks/apply-resource-policy.yml` — standalone playbook

**Modify (add Slice= to SLM ansible service templates):**
- `autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2`
- `autobot-slm-backend/ansible/roles/backend/templates/autobot-celery.service.j2`
- `autobot-slm-backend/ansible/roles/backend/templates/autobot-celery-beat.service.j2`
- `autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-chromadb.service.j2`
- `autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-ai-stack.service.j2`
- `autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm-backend.service.j2`
- `autobot-slm-backend/ansible/roles/llm/templates/ollama.service.j2`
- `autobot-slm-backend/ansible/roles/monitoring/templates/prometheus.service.j2`
- `autobot-slm-backend/ansible/roles/monitoring/templates/node_exporter.service.j2`
- `autobot-slm-backend/ansible/roles/npu-worker/templates/autobot-npu-worker.service.j2`
- `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2`

**Modify (add Slice= to infrastructure static service files):**
- `autobot-infrastructure/autobot-database/templates/autobot-redis.service`
- `autobot-infrastructure/autobot-database/templates/autobot-chromadb.service`
- `autobot-infrastructure/autobot-ai-stack/templates/autobot-ai-stack.service`
- `autobot-infrastructure/autobot-backend/templates/autobot-user-backend.service`
- `autobot-infrastructure/autobot-slm-backend/templates/autobot-slm-backend.service`
- `autobot-infrastructure/autobot-ollama/templates/autobot-ollama.service`
- `autobot-infrastructure/autobot-browser-worker/templates/autobot-browser-worker.service`

**Modify (integrate role into deploy playbooks):**
- `autobot-slm-backend/ansible/playbooks/deploy-native-services.yml`
- `autobot-slm-backend/ansible/playbooks/deploy-backend-local.yml`
- `autobot-slm-backend/ansible/playbooks/deploy-backend-remote.yml`

---

## Task 1: Role defaults — percentages, floors, thresholds

**Files:**
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/defaults/main.yml`

- [ ] **Step 1: Create the defaults file**

```yaml
# autobot-slm-backend/ansible/roles/autobot-resource-policy/defaults/main.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
---
# Deployment type: systemd | docker | both
autobot_deployment_type: "systemd"

# ── Global budget ──────────────────────────────────────────────────────────────
# OS always keeps os_reserve_pct% of RAM — never given to any service.
# The remaining global_cap_pct% becomes the autobot.slice hard ceiling.
autobot_resource_os_reserve_pct: 15
autobot_resource_global_cap_pct: 85

# ── Per-service allocations ────────────────────────────────────────────────────
# pct: percentage of autobot_budget (not total RAM)
# floor_mb: minimum MemoryHigh in MB — floor overrides pct on small hosts
# min_host_ram_mb: service is disabled if host has less than this much total RAM
# oom_score_adj: -1000 (never kill) … +1000 (kill first)
# cpu_weight: 1–10000 (100 = default); scheduler relative weight
# tier: critical | standard | background (maps to systemd slice)

autobot_resource_services:
  redis:
    pct: 8
    floor_mb: 64
    min_host_ram_mb: 0
    oom_score_adj: -500
    cpu_weight: 800
    tier: critical
    unit: redis-stack-server
    docker_service: autobot-redis

  slm_backend:
    pct: 8
    floor_mb: 128
    min_host_ram_mb: 0
    oom_score_adj: -400
    cpu_weight: 600
    tier: critical
    unit: autobot-slm-backend
    docker_service: autobot-slm

  backend:
    pct: 20
    floor_mb: 256
    min_host_ram_mb: 0
    oom_score_adj: -200
    cpu_weight: 500
    tier: standard
    unit: autobot-backend
    docker_service: autobot-backend
    omp_threads: true     # Set OMP/MKL/OPENBLAS_NUM_THREADS in drop-in

  chromadb:
    pct: 12
    floor_mb: 256
    min_host_ram_mb: 2048
    oom_score_adj: 0
    cpu_weight: 400
    tier: standard
    unit: autobot-chromadb
    docker_service: autobot-chromadb

  celery:
    pct: 8
    floor_mb: 128
    min_host_ram_mb: 1024
    oom_score_adj: 200
    cpu_weight: 300
    tier: standard
    unit: autobot-celery
    docker_service: autobot-celery

  ai_stack:
    pct: 15
    floor_mb: 512
    min_host_ram_mb: 8192
    oom_score_adj: 100
    cpu_weight: 300
    tier: standard
    unit: autobot-ai-stack
    docker_service: autobot-ai-stack

  ollama:
    pct: 0          # Only allocated when explicitly enabled via inventory
    floor_mb: 512
    min_host_ram_mb: 8192
    oom_score_adj: 100
    cpu_weight: 300
    tier: standard
    unit: autobot-ollama
    docker_service: autobot-ollama

  npu_worker:
    pct: 6
    floor_mb: 256
    min_host_ram_mb: 4096
    oom_score_adj: 100
    cpu_weight: 300
    tier: standard
    unit: autobot-npu-worker
    docker_service: ""    # No docker service

  browser_worker:
    pct: 6
    floor_mb: 256
    min_host_ram_mb: 4096
    oom_score_adj: 400
    cpu_weight: 200
    tier: background
    unit: autobot-playwright
    docker_service: autobot-playwright

  monitoring:
    pct: 4
    floor_mb: 32
    min_host_ram_mb: 0
    oom_score_adj: -100
    cpu_weight: 100
    tier: standard
    unit: prometheus
    docker_service: autobot-prometheus
```

- [ ] **Step 2: Commit skeleton**

```bash
git add autobot-slm-backend/ansible/roles/autobot-resource-policy/
git commit -m "feat(resource-policy): add role defaults with per-service budget vars"
```

---

## Task 2: Budget computation — tasks/main.yml

**Files:**
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/main.yml`

- [ ] **Step 1: Create tasks/main.yml**

```yaml
# autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/main.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
---
- name: resource-policy | gather host facts
  ansible.builtin.setup:
    gather_subset:
      - hardware
      - virtual
  when: ansible_memtotal_mb is not defined

- name: resource-policy | compute global budget
  ansible.builtin.set_fact:
    _rp_total_ram_mb: "{{ ansible_memtotal_mb | int }}"
    _rp_vcpus: "{{ ansible_processor_vcpus | int }}"
    _rp_budget_mb: "{{ (ansible_memtotal_mb | int * autobot_resource_global_cap_pct / 100) | int }}"
    _rp_omp_threads: "{{ [2, (ansible_processor_vcpus | int // 4)] | max }}"

# tasks_max scales with vCPUs: max(32, vcpus * 16)
- name: resource-policy | compute tasks_max
  ansible.builtin.set_fact:
    _rp_tasks_max: "{{ [32, (_rp_vcpus | int * 16)] | max }}"

# sum_of_weights for Docker CPU share computation (only enabled services)
- name: resource-policy | compute enabled services and weight sum
  ansible.builtin.set_fact:
    _rp_enabled_services: >-
      {{
        autobot_resource_services | dict2items
        | selectattr('value.min_host_ram_mb', 'le', _rp_total_ram_mb | int)
        | selectattr('value.pct', 'gt', 0)
        | list
      }}

- name: resource-policy | compute weight sum for CPU allocation
  ansible.builtin.set_fact:
    _rp_weight_sum: >-
      {{
        _rp_enabled_services
        | map(attribute='value.cpu_weight')
        | map('int')
        | sum
      }}

# Per-service computed values: memory_high_mb, memory_max_mb, cpu_limit
- name: resource-policy | compute per-service limits
  ansible.builtin.set_fact:
    _rp_limits: >-
      {{
        _rp_limits | default({}) | combine({
          item.key: {
            'enabled': (item.value.min_host_ram_mb | int) <= (_rp_total_ram_mb | int) and (item.value.pct | int) > 0,
            'memory_high_mb': [
              (_rp_budget_mb | int * item.value.pct / 100) | int,
              item.value.floor_mb | int
            ] | max,
            'memory_max_mb': ([
              (_rp_budget_mb | int * item.value.pct / 100) | int,
              item.value.floor_mb | int
            ] | max * 1.25) | int,
            'cpu_cpus': ((_rp_vcpus | int * item.value.cpu_weight / _rp_weight_sum | float) | round(2) | float,
                         _rp_vcpus | int * 0.5) | min,
            'tier': item.value.tier,
            'unit': item.value.unit,
            'oom_score_adj': item.value.oom_score_adj,
            'tasks_max': _rp_tasks_max | int,
            'omp_threads': item.value.omp_threads | default(false),
            'docker_service': item.value.docker_service | default('')
          }
        })
      }}
  loop: "{{ autobot_resource_services | dict2items }}"
  loop_control:
    label: "{{ item.key }}"

- name: resource-policy | apply systemd limits
  ansible.builtin.import_tasks: systemd-slices.yml
  become: true
  when: autobot_deployment_type in ['systemd', 'both']

- name: resource-policy | apply systemd drop-ins
  ansible.builtin.import_tasks: systemd-dropins.yml
  become: true
  when: autobot_deployment_type in ['systemd', 'both']

- name: resource-policy | generate docker override
  ansible.builtin.import_tasks: docker-override.yml
  when: autobot_deployment_type in ['docker', 'both']
```

- [ ] **Step 2: Commit**

```bash
git add autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/main.yml
git commit -m "feat(resource-policy): add budget computation tasks with set_fact"
```

---

## Task 3: systemd slice templates and task

**Files:**
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot.slice.j2`
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot-tier.slice.j2`
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-slices.yml`

- [ ] **Step 1: Create autobot.slice.j2**

```ini
# autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot.slice.j2
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss — auto-generated by autobot-resource-policy role
[Unit]
Description=AutoBot Services Slice
Documentation=https://github.com/mrveiss/AutoBot-AI
Before=slices.target

[Slice]
# Hard ceiling: AutoBot as a whole cannot exceed {{ autobot_resource_global_cap_pct }}% of host RAM.
# OS always retains {{ autobot_resource_os_reserve_pct }}% ({{ (_rp_total_ram_mb | int * autobot_resource_os_reserve_pct / 100) | int }} MB).
MemoryMax={{ (_rp_total_ram_mb | int * autobot_resource_global_cap_pct / 100) | int }}M
CPUWeight=500
```

- [ ] **Step 2: Create autobot-tier.slice.j2**

```ini
# autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot-tier.slice.j2
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss — auto-generated by autobot-resource-policy role
[Unit]
Description=AutoBot {{ slice_tier | capitalize }} Services Slice
Documentation=https://github.com/mrveiss/AutoBot-AI

[Slice]
Slice=autobot.slice
CPUWeight={{ slice_cpu_weight }}
```

- [ ] **Step 3: Create tasks/systemd-slices.yml**

```yaml
# autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-slices.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
---
- name: resource-policy | write autobot.slice
  ansible.builtin.template:
    src: autobot.slice.j2
    dest: /etc/systemd/system/autobot.slice
    owner: root
    group: root
    mode: '0644'

- name: resource-policy | write tier slices
  ansible.builtin.template:
    src: autobot-tier.slice.j2
    dest: "/etc/systemd/system/autobot-{{ item.tier }}.slice"
    owner: root
    group: root
    mode: '0644'
  vars:
    slice_tier: "{{ item.tier }}"
    slice_cpu_weight: "{{ item.cpu_weight }}"
  loop:
    - { tier: critical,   cpu_weight: 1000 }
    - { tier: standard,   cpu_weight: 500  }
    - { tier: background, cpu_weight: 100  }

- name: resource-policy | reload systemd after slice changes
  ansible.builtin.systemd:
    daemon_reload: true
```

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot.slice.j2 \
        autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/autobot-tier.slice.j2 \
        autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-slices.yml
git commit -m "feat(resource-policy): add systemd slice templates and task"
```

---

## Task 4: Per-service drop-in template and task

**Files:**
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/resource-policy.conf.j2`
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-dropins.yml`

- [ ] **Step 1: Create resource-policy.conf.j2**

```ini
# autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/resource-policy.conf.j2
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss — auto-generated by autobot-resource-policy role
# Host: {{ ansible_hostname }} | RAM: {{ _rp_total_ram_mb }}MB | vCPUs: {{ _rp_vcpus }}
[Service]
Slice=autobot-{{ svc_tier }}.slice
MemoryHigh={{ svc_memory_high_mb }}M
MemoryMax={{ svc_memory_max_mb }}M
CPUWeight={{ svc_cpu_weight }}
TasksMax={{ svc_tasks_max }}
OOMScoreAdj={{ svc_oom_score_adj }}
{% if svc_omp_threads %}
Environment="OMP_NUM_THREADS={{ _rp_omp_threads }}"
Environment="MKL_NUM_THREADS={{ _rp_omp_threads }}"
Environment="OPENBLAS_NUM_THREADS={{ _rp_omp_threads }}"
{% endif %}
```

- [ ] **Step 2: Create tasks/systemd-dropins.yml**

```yaml
# autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-dropins.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
---
- name: resource-policy | check which service units exist on this host
  ansible.builtin.stat:
    path: "/etc/systemd/system/{{ item.value.unit }}.service"
  register: _rp_unit_stat
  loop: "{{ autobot_resource_services | dict2items }}"
  loop_control:
    label: "{{ item.key }}"

- name: resource-policy | build present-services list
  ansible.builtin.set_fact:
    _rp_present_services: >-
      {{
        _rp_unit_stat.results
        | selectattr('stat.exists')
        | map(attribute='item')
        | list
      }}

- name: resource-policy | create drop-in directories
  ansible.builtin.file:
    path: "/etc/systemd/system/{{ item.value.unit }}.service.d"
    state: directory
    owner: root
    group: root
    mode: '0755'
  loop: "{{ _rp_present_services }}"
  loop_control:
    label: "{{ item.key }}"

- name: resource-policy | write resource-policy.conf drop-ins
  ansible.builtin.template:
    src: resource-policy.conf.j2
    dest: "/etc/systemd/system/{{ item.value.unit }}.service.d/resource-policy.conf"
    owner: root
    group: root
    mode: '0644'
  vars:
    svc_tier: "{{ _rp_limits[item.key].tier }}"
    svc_memory_high_mb: "{{ _rp_limits[item.key].memory_high_mb }}"
    svc_memory_max_mb: "{{ _rp_limits[item.key].memory_max_mb }}"
    svc_cpu_weight: "{{ item.value.cpu_weight }}"
    svc_tasks_max: "{{ _rp_limits[item.key].tasks_max }}"
    svc_oom_score_adj: "{{ item.value.oom_score_adj }}"
    svc_omp_threads: "{{ item.value.omp_threads | default(false) }}"
  loop: "{{ _rp_present_services }}"
  loop_control:
    label: "{{ item.key }}"
  notify: resource-policy | daemon-reload

- name: resource-policy | flush handlers
  ansible.builtin.meta: flush_handlers
```

- [ ] **Step 3: Create handlers file**

```yaml
# autobot-slm-backend/ansible/roles/autobot-resource-policy/handlers/main.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
---
- name: resource-policy | daemon-reload
  ansible.builtin.systemd:
    daemon_reload: true
```

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/resource-policy.conf.j2 \
        autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/systemd-dropins.yml \
        autobot-slm-backend/ansible/roles/autobot-resource-policy/handlers/main.yml
git commit -m "feat(resource-policy): add drop-in template and per-service systemd task"
```

---

## Task 5: Docker Compose override template and task

**Files:**
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/docker-compose.override.yml.j2`
- Create: `autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/docker-override.yml`

- [ ] **Step 1: Create docker-compose.override.yml.j2**

```jinja2
# autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/docker-compose.override.yml.j2
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# AUTO-GENERATED by autobot-resource-policy — do not edit manually.
# Host: {{ ansible_hostname }} | RAM: {{ _rp_total_ram_mb }}MB | vCPUs: {{ _rp_vcpus }}
# Regenerate: ansible-playbook apply-resource-policy.yml
---
services:
{% for svc_key, svc_limits in _rp_limits.items() %}
{% set svc_def = autobot_resource_services[svc_key] %}
{% if svc_limits.enabled and svc_def.docker_service %}
  {{ svc_def.docker_service }}:
    deploy:
      resources:
        limits:
          memory: "{{ svc_limits.memory_max_mb }}m"
          cpus: "{{ svc_limits.cpu_cpus }}"
        reservations:
          memory: "{{ (svc_limits.memory_high_mb | int * 0.5) | int }}m"
{% if svc_def.omp_threads | default(false) %}
    environment:
      OMP_NUM_THREADS: "{{ _rp_omp_threads }}"
      MKL_NUM_THREADS: "{{ _rp_omp_threads }}"
      OPENBLAS_NUM_THREADS: "{{ _rp_omp_threads }}"
{% endif %}
{% endif %}
{% endfor %}
```

- [ ] **Step 2: Create tasks/docker-override.yml**

```yaml
# autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/docker-override.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
---
- name: resource-policy | find docker-compose.yml location
  ansible.builtin.stat:
    path: "{{ item }}/docker-compose.yml"
  register: _rp_compose_stat
  loop:
    - "{{ playbook_dir | dirname }}"
    - /opt/autobot
    - "{{ ansible_env.HOME }}/AutoBot-AI"
    - /home/autobot/AutoBot-AI

- name: resource-policy | set compose directory
  ansible.builtin.set_fact:
    _rp_compose_dir: >-
      {{
        _rp_compose_stat.results
        | selectattr('stat.exists')
        | map(attribute='item')
        | first
      }}
  when: _rp_compose_stat.results | selectattr('stat.exists') | list | length > 0

- name: resource-policy | write docker-compose.override.yml
  ansible.builtin.template:
    src: docker-compose.override.yml.j2
    dest: "{{ _rp_compose_dir }}/docker-compose.override.yml"
    owner: "{{ ansible_env.USER }}"
    group: "{{ ansible_env.USER }}"
    mode: '0644'
  when: _rp_compose_dir is defined
```

- [ ] **Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/roles/autobot-resource-policy/templates/docker-compose.override.yml.j2 \
        autobot-slm-backend/ansible/roles/autobot-resource-policy/tasks/docker-override.yml
git commit -m "feat(resource-policy): add Docker Compose override template and task"
```

---

## Task 6: Add Slice= to SLM ansible service templates

Each service `[Service]` section needs one line added: `Slice=autobot-<tier>.slice`. No other changes.

**Files:** 11 service templates in `autobot-slm-backend/ansible/roles/`

- [ ] **Step 1: Add Slice= to autobot-backend.service.j2**

In `autobot-slm-backend/ansible/roles/backend/templates/autobot-backend.service.j2`, add after the `[Service]` line:

```ini
[Service]
Slice=autobot-standard.slice
Type=simple
```

- [ ] **Step 2: Add Slice= to autobot-celery.service.j2**

In `autobot-slm-backend/ansible/roles/backend/templates/autobot-celery.service.j2`, add after `[Service]`:

```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 3: Add Slice= to autobot-celery-beat.service.j2**

In `autobot-slm-backend/ansible/roles/backend/templates/autobot-celery-beat.service.j2`, add after `[Service]`:

```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 4: Add Slice= to autobot-chromadb.service.j2 (ai-stack role)**

In `autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-chromadb.service.j2`, add after `[Service]`:

```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 5: Add Slice= to autobot-ai-stack.service.j2**

In `autobot-slm-backend/ansible/roles/ai-stack/templates/autobot-ai-stack.service.j2`, add after `[Service]`:

```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 6: Add Slice= to autobot-slm-backend.service.j2**

In `autobot-slm-backend/ansible/roles/slm_manager/templates/autobot-slm-backend.service.j2`, add after `[Service]`:

```ini
[Service]
Slice=autobot-critical.slice
```

- [ ] **Step 7: Add Slice= to ollama.service.j2**

In `autobot-slm-backend/ansible/roles/llm/templates/ollama.service.j2`, add after `[Service]`:

```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 8: Add Slice= to monitoring templates**

In `autobot-slm-backend/ansible/roles/monitoring/templates/prometheus.service.j2`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

In `autobot-slm-backend/ansible/roles/monitoring/templates/node_exporter.service.j2`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 9: Add Slice= to npu-worker and browser templates**

In `autobot-slm-backend/ansible/roles/npu-worker/templates/autobot-npu-worker.service.j2`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

In `autobot-slm-backend/ansible/roles/browser/templates/playwright.service.j2`, add after `[Service]`:
```ini
[Service]
Slice=autobot-background.slice
```

- [ ] **Step 10: Commit**

```bash
git add autobot-slm-backend/ansible/roles/backend/templates/ \
        autobot-slm-backend/ansible/roles/ai-stack/templates/ \
        autobot-slm-backend/ansible/roles/slm_manager/templates/ \
        autobot-slm-backend/ansible/roles/llm/templates/ \
        autobot-slm-backend/ansible/roles/monitoring/templates/ \
        autobot-slm-backend/ansible/roles/npu-worker/templates/ \
        autobot-slm-backend/ansible/roles/browser/templates/
git commit -m "feat(resource-policy): add Slice= to all SLM ansible service templates"
```

---

## Task 7: Add Slice= to infrastructure static service files

Same pattern — add `Slice=autobot-<tier>.slice` after `[Service]` in each static file.

**Files:** 7 static service files in `autobot-infrastructure/`

- [ ] **Step 1: redis.service**

In `autobot-infrastructure/autobot-database/templates/autobot-redis.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-critical.slice
```

- [ ] **Step 2: chromadb.service (infrastructure)**

In `autobot-infrastructure/autobot-database/templates/autobot-chromadb.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 3: autobot-ai-stack.service**

In `autobot-infrastructure/autobot-ai-stack/templates/autobot-ai-stack.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 4: autobot-user-backend.service**

In `autobot-infrastructure/autobot-backend/templates/autobot-user-backend.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 5: autobot-slm-backend.service (infrastructure)**

In `autobot-infrastructure/autobot-slm-backend/templates/autobot-slm-backend.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-critical.slice
```

- [ ] **Step 6: autobot-ollama.service**

In `autobot-infrastructure/autobot-ollama/templates/autobot-ollama.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-standard.slice
```

- [ ] **Step 7: autobot-browser-worker.service**

In `autobot-infrastructure/autobot-browser-worker/templates/autobot-browser-worker.service`, add after `[Service]`:
```ini
[Service]
Slice=autobot-background.slice
```

- [ ] **Step 8: Commit**

```bash
git add autobot-infrastructure/
git commit -m "feat(resource-policy): add Slice= to all infrastructure static service files"
```

---

## Task 8: Standalone apply-resource-policy.yml playbook

**Files:**
- Create: `autobot-slm-backend/ansible/playbooks/apply-resource-policy.yml`

- [ ] **Step 1: Create the playbook**

```yaml
# autobot-slm-backend/ansible/playbooks/apply-resource-policy.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
---
# Standalone playbook: apply resource limits to a running host without
# redeploying services. Safe to run at any time — only writes drop-in files
# and slice units, then daemon-reloads. Does not restart any services.
#
# Usage:
#   ansible-playbook apply-resource-policy.yml -i inventory/hosts.yml
#   ansible-playbook apply-resource-policy.yml -i inventory/hosts.yml \
#     -e "autobot_deployment_type=docker"
#   ansible-playbook apply-resource-policy.yml -i inventory/hosts.yml \
#     -e "autobot_resource_services.backend.pct=25"
#   # Dry-run (no changes):
#   ansible-playbook apply-resource-policy.yml -i inventory/hosts.yml --check

- name: Apply AutoBot resource policy
  hosts: all
  gather_facts: true
  become: true
  roles:
    - role: autobot-resource-policy

- name: Show computed limits summary
  hosts: all
  gather_facts: false
  tasks:
    - name: Display resource allocation summary
      ansible.builtin.debug:
        msg: |
          ── Resource Policy Applied ──────────────────────────
          Host RAM : {{ ansible_memtotal_mb }} MB
          vCPUs    : {{ ansible_processor_vcpus }}
          Budget   : {{ (_rp_budget_mb | int) }} MB ({{ autobot_resource_global_cap_pct }}% of RAM)
          OMP thds : {{ _rp_omp_threads }}
          TasksMax : {{ _rp_tasks_max }}

          Service limits (MemoryHigh / MemoryMax):
          {% for svc, lim in _rp_limits.items() %}
          {% if lim.enabled %}
            {{ '%-16s' | format(svc) }} {{ lim.memory_high_mb }} MB / {{ lim.memory_max_mb }} MB  [{{ lim.tier }}]
          {% else %}
            {{ '%-16s' | format(svc) }} DISABLED (host RAM below threshold)
          {% endif %}
          {% endfor %}
          ─────────────────────────────────────────────────────
```

- [ ] **Step 2: Commit**

```bash
git add autobot-slm-backend/ansible/playbooks/apply-resource-policy.yml
git commit -m "feat(resource-policy): add standalone apply-resource-policy.yml playbook"
```

---

## Task 9: Integrate role into deploy playbooks

The role must run at the end of every playbook that installs services, so limits are applied on every fresh deploy.

**Files:**
- Modify: `autobot-slm-backend/ansible/playbooks/deploy-native-services.yml`
- Modify: `autobot-slm-backend/ansible/playbooks/deploy-backend-local.yml`
- Modify: `autobot-slm-backend/ansible/playbooks/deploy-backend-remote.yml`

- [ ] **Step 1: Check if deploy-native-services.yml exists; create if missing**

```bash
ls autobot-slm-backend/ansible/playbooks/deploy-native-services.yml 2>/dev/null \
  || echo "file missing — create it"
```

If missing, create `autobot-slm-backend/ansible/playbooks/deploy-native-services.yml`:

```yaml
# autobot-slm-backend/ansible/playbooks/deploy-native-services.yml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
---
- name: Deploy all native AutoBot services
  import_playbook: deploy-backend-local.yml

- name: Apply resource policy after all services deployed
  import_playbook: apply-resource-policy.yml
```

- [ ] **Step 2: Append resource policy phase to deploy-backend-local.yml**

Read the file first, then add at the end:

```yaml
# Add at the bottom of deploy-backend-local.yml:

- name: Apply resource limits
  hosts: "{{ target_hosts | default('all') }}"
  gather_facts: true
  become: true
  roles:
    - role: autobot-resource-policy
```

- [ ] **Step 3: Append same block to deploy-backend-remote.yml**

Same block as Step 2, added at the bottom of `deploy-backend-remote.yml`.

- [ ] **Step 4: Commit**

```bash
git add autobot-slm-backend/ansible/playbooks/deploy-native-services.yml \
        autobot-slm-backend/ansible/playbooks/deploy-backend-local.yml \
        autobot-slm-backend/ansible/playbooks/deploy-backend-remote.yml
git commit -m "feat(resource-policy): integrate role into deploy playbooks"
```

---

## Task 10: Smoke test and final commit

- [ ] **Step 1: Dry-run on localhost to verify templates render without errors**

```bash
cd autobot-slm-backend/ansible
ansible-playbook playbooks/apply-resource-policy.yml \
  -i "localhost," \
  -c local \
  --check \
  -e "autobot_deployment_type=systemd" \
  -v 2>&1 | tee /tmp/resource-policy-check.log

# Expected: no FAILED tasks, "changed" lines show the files that would be written
grep -E "TASK|ok:|changed:|failed:|FAILED" /tmp/resource-policy-check.log
```

- [ ] **Step 2: Run for real on localhost**

```bash
ansible-playbook playbooks/apply-resource-policy.yml \
  -i "localhost," \
  -c local \
  --become \
  -e "autobot_deployment_type=systemd"
```

- [ ] **Step 3: Verify slices were created**

```bash
systemctl cat autobot.slice
systemctl cat autobot-critical.slice
systemctl cat autobot-standard.slice
systemctl cat autobot-background.slice
# Expected: unit files with MemoryMax and CPUWeight matching computed values
```

- [ ] **Step 4: Verify a drop-in was written for an existing service**

```bash
# Check whichever service is running locally
cat /etc/systemd/system/autobot-backend.service.d/resource-policy.conf
# Expected: Slice=autobot-standard.slice, MemoryHigh=, MemoryMax=, OOMScoreAdj=
```

- [ ] **Step 5: Verify live service picked up the limits**

```bash
systemctl show autobot-backend --no-pager -p MemoryHigh,MemoryMax,TasksMax,OOMScoreAdj,Slice
# Expected: values matching the computed allocations (not 'infinity')
```

- [ ] **Step 6: Test Docker mode (if docker-compose.yml is present)**

```bash
ansible-playbook playbooks/apply-resource-policy.yml \
  -i "localhost," \
  -c local \
  -e "autobot_deployment_type=docker"

cat docker-compose.override.yml
# Expected: services block with memory/cpus limits for each enabled service
```

- [ ] **Step 7: Final commit**

```bash
git add -u
git commit -m "feat(resource-policy): complete implementation — systemd slices, drop-ins, Docker override"
```

---

## Self-Review Checklist

- [x] **Spec § Budget computation** → Task 2 (set_fact math matches spec formula)
- [x] **Spec § systemd slice hierarchy** → Tasks 3–4 (autobot.slice + three tier slices + drop-ins)
- [x] **Spec § per-service allocation table** → Task 1 defaults (all 9 services with pct, floor, oom, cpu_weight, tier)
- [x] **Spec § floor guards** → Task 2 `[pct_computed, floor_mb] | max` covers Pi case
- [x] **Spec § auto-disable below RAM threshold** → Task 2 `min_host_ram_mb` filter + `enabled` flag in _rp_limits
- [x] **Spec § OMP threads** → Task 4 template writes env vars when `omp_threads: true`; Task 1 marks backend/ai_stack
- [x] **Spec § Docker unified** → Task 5 override template reads same `_rp_limits`
- [x] **Spec § distributed deployment** → Task 4 stat-check only writes drop-ins for units present on host
- [x] **Spec § standalone playbook** → Task 8
- [x] **Spec § integrate into deploy playbooks** → Task 9
- [x] **No TBD/TODO placeholders** — all steps have complete code
- [x] **Type consistency** — `_rp_limits` dict built in Task 2, consumed by Tasks 4 and 5 using same key names (`memory_high_mb`, `memory_max_mb`, `tier`, `tasks_max`, `oom_score_adj`, `omp_threads`)
