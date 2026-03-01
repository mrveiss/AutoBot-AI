# System Updates Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real `apt update`/`apt upgrade` package discovery and management to the SLM System Updates tab, with combined sidebar/tab badges.

**Architecture:** Ansible-only pipeline — new `check-system-updates.yml` playbook discovers packages, backend parses output and stores in `UpdateInfo` table, frontend polls and displays. Sidebar badge combines system update count + code sync outdated count.

**Tech Stack:** Python/FastAPI (backend), Ansible (fleet orchestration), Vue 3/TypeScript (frontend), SQLAlchemy (ORM), axios (HTTP client)

**Design doc:** `docs/plans/2026-02-27-system-updates-design.md`

---

## Task 1: Ansible Playbook — check-system-updates.yml

**Files:**
- Create: `autobot-slm-backend/ansible/check-system-updates.yml`

**Step 1: Create the playbook**

Create `autobot-slm-backend/ansible/check-system-updates.yml`:

```yaml
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
#
# Check System Updates Playbook
# Discovers available apt package updates on fleet nodes.
# Output is parsed by the SLM backend to populate UpdateInfo records.
---

- name: Check System Updates
  hosts: "{{ target_hosts | default('all') }}"
  become: true
  gather_facts: true

  tasks:
    - name: Update apt cache
      ansible.builtin.apt:
        update_cache: true
        cache_valid_time: 0
      when: ansible_os_family == "Debian"

    - name: Get list of upgradable packages
      ansible.builtin.shell: |
        apt list --upgradable 2>/dev/null | grep -v '^Listing' | head -500
      register: upgradable_raw
      changed_when: false
      when: ansible_os_family == "Debian"

    - name: Get held packages
      ansible.builtin.shell: |
        apt-mark showhold 2>/dev/null || true
      register: held_packages
      changed_when: false
      when: ansible_os_family == "Debian"

    - name: Get security sources
      ansible.builtin.shell: |
        grep -l security /etc/apt/sources.list /etc/apt/sources.list.d/*.list 2>/dev/null | head -1 || echo ""
      register: security_source
      changed_when: false
      when: ansible_os_family == "Debian"

    - name: Check security updates separately
      ansible.builtin.shell: |
        apt list --upgradable 2>/dev/null | grep -i security | head -200 || true
      register: security_updates_raw
      changed_when: false
      when: ansible_os_family == "Debian"

    - name: Parse upgradable packages into JSON
      ansible.builtin.set_fact:
        parsed_packages: >-
          {{
            upgradable_raw.stdout_lines | default([])
            | map('regex_replace', '^([^ /]+)/\S+ (\S+) \S+ \[upgradable from: ([^\]]+)\]$', '{"p":"\1","a":"\2","c":"\3"}')
            | select('match', '^\{')
            | list
          }}
        held_list: "{{ (held_packages.stdout_lines | default([])) }}"
        security_pkgs: >-
          {{
            security_updates_raw.stdout_lines | default([])
            | map('regex_replace', '^([^ /]+)/.*', '\1')
            | list
          }}
      when: ansible_os_family == "Debian"

    - name: Output discovered packages as JSON
      ansible.builtin.debug:
        msg: >-
          AUTOBOT_UPDATES_JSON:{{ {
            'hostname': ansible_hostname,
            'ip_address': ansible_default_ipv4.address | default('unknown'),
            'os_family': ansible_os_family,
            'packages': parsed_packages | default([]),
            'held': held_list | default([]),
            'security_packages': security_pkgs | default([]),
            'total': (parsed_packages | default([])) | length
          } | to_json }}
```

**Step 2: Verify playbook syntax**

Run: `cd /home/kali/Desktop/AutoBot/autobot-slm-backend/ansible && ansible-playbook --syntax-check check-system-updates.yml 2>&1 || echo "syntax check requires inventory"`

Expected: No syntax errors (may warn about missing inventory, that's OK).

**Step 3: Commit**

```bash
git add autobot-slm-backend/ansible/check-system-updates.yml
git commit -m "feat(updates): add check-system-updates.yml Ansible playbook

Discovers available apt packages on fleet nodes via apt update + apt list --upgradable.
Outputs AUTOBOT_UPDATES_JSON markers for backend parsing.
Handles held packages and security update classification."
```

---

## Task 2: Backend Schemas — New Request/Response Models

**Files:**
- Modify: `autobot-slm-backend/models/schemas.py` (after line 545)

**Step 1: Add new schemas**

Add after the `FleetUpdateSummaryResponse` class (line 545) in `autobot-slm-backend/models/schemas.py`:

```python
class UpdateDiscoverRequest(BaseModel):
    """Request to discover available system updates on fleet nodes."""

    node_ids: Optional[List[str]] = None  # None = all nodes
    role: Optional[str] = None  # Filter by role


class UpdateDiscoverResponse(BaseModel):
    """Response from triggering update discovery."""

    success: bool
    message: str
    job_id: str


class UpdateDiscoverStatus(BaseModel):
    """Status of an update discovery job."""

    job_id: str
    status: str  # pending, running, completed, failed
    progress: int = 0
    message: Optional[str] = None
    nodes_checked: int = 0
    total_nodes: int = 0
    packages_found: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class UpdateSummaryResponse(BaseModel):
    """Lightweight summary for sidebar badge polling."""

    system_update_count: int = 0
    security_update_count: int = 0
    nodes_with_updates: int = 0
    last_checked: Optional[datetime] = None


class UpdatePackagesResponse(BaseModel):
    """Paginated list of discovered packages."""

    packages: List[UpdateInfoResponse]
    total: int
    by_node: Dict[str, int] = Field(default_factory=dict)


class UpdateApplyAllRequest(BaseModel):
    """Request to upgrade all packages on a node."""

    node_id: str
    upgrade_all: bool = False  # True = apt upgrade all
    update_ids: List[str] = Field(default_factory=list)
```

**Step 2: Verify import**

Run: `cd /home/kali/Desktop/AutoBot/autobot-slm-backend && python3 -c "from models.schemas import UpdateDiscoverRequest, UpdateSummaryResponse; print('OK')"`

Expected: `OK`

**Step 3: Commit**

```bash
git add autobot-slm-backend/models/schemas.py
git commit -m "feat(updates): add schemas for system update discovery and summary"
```

---

## Task 3: Backend — Discover Endpoint + Background Job

**Files:**
- Modify: `autobot-slm-backend/api/updates.py`

This is the largest backend task. It adds:
1. `POST /api/updates/discover` — trigger package discovery
2. `GET /api/updates/discover/{job_id}` — poll discovery status
3. Background job that runs Ansible and parses output
4. Helper to parse `AUTOBOT_UPDATES_JSON:` markers from Ansible stdout

**Step 1: Add imports and in-memory job tracking**

At the top of `autobot-slm-backend/api/updates.py`, add to imports (after existing imports):

```python
import json
import re
from collections import defaultdict
```

Add after the existing `_running_jobs` dict (line 47):

```python
# Track running discovery jobs (in-memory, transient)
_discover_jobs: Dict[str, dict] = {}
```

**Step 2: Add the discover helper functions**

Add before the first route (`@router.get("/check")`, line 276):

```python
def _parse_discover_output(output: str) -> List[dict]:
    """Parse AUTOBOT_UPDATES_JSON markers from Ansible playbook output.

    Each marker line contains JSON with hostname, packages, etc.
    Returns list of per-host result dicts.
    """
    results = []
    for line in output.split("\n"):
        # Ansible debug output wraps in "msg": "..."
        marker = "AUTOBOT_UPDATES_JSON:"
        idx = line.find(marker)
        if idx == -1:
            continue
        json_str = line[idx + len(marker):].strip()
        # Remove trailing quotes/punctuation from Ansible formatting
        json_str = json_str.rstrip('"').rstrip("'")
        try:
            data = json.loads(json_str)
            results.append(data)
        except json.JSONDecodeError:
            logger.warning("Failed to parse discover JSON: %.200s", json_str)
    return results


async def _resolve_hostname_to_node(
    db: AsyncSession, hostname: str
) -> Optional[str]:
    """Map an Ansible hostname back to a node_id."""
    result = await db.execute(
        select(Node).where(Node.hostname == hostname)
    )
    node = result.scalar_one_or_none()
    return node.node_id if node else None


def _classify_severity(
    pkg_name: str, security_packages: List[str]
) -> str:
    """Classify package update severity."""
    if pkg_name in security_packages:
        return "security"
    return "standard"


async def _upsert_update_info(
    db: AsyncSession,
    node_id: str,
    pkg: dict,
    severity: str,
) -> None:
    """Insert or update an UpdateInfo record (dedup by node+package)."""
    # Check for existing record
    existing = await db.execute(
        select(UpdateInfo).where(
            UpdateInfo.node_id == node_id,
            UpdateInfo.package_name == pkg["p"],
            UpdateInfo.is_applied.is_(False),
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.available_version = pkg["a"]
        record.current_version = pkg["c"]
        record.severity = severity
    else:
        new_record = UpdateInfo(
            update_id=str(uuid.uuid4())[:16],
            node_id=node_id,
            package_name=pkg["p"],
            current_version=pkg["c"],
            available_version=pkg["a"],
            severity=severity,
            is_applied=False,
        )
        db.add(new_record)


async def _run_discover_job(
    job_id: str, node_ids: Optional[List[str]], role: Optional[str]
) -> None:
    """Background task: run check-system-updates.yml and parse results."""
    from services.database import db_service

    job = _discover_jobs.get(job_id)
    if not job:
        return

    job["status"] = "running"
    job["started_at"] = datetime.utcnow().isoformat()

    try:
        # Build playbook params
        executor = get_playbook_executor()
        extra_vars = {}
        limit = None

        async with db_service.session() as db:
            if node_ids:
                # Resolve node_ids to hostnames for Ansible limit
                result = await db.execute(
                    select(Node).where(Node.node_id.in_(node_ids))
                )
                nodes = result.scalars().all()
                limit = [n.hostname for n in nodes]
                job["total_nodes"] = len(limit)
            elif role:
                extra_vars["target_hosts"] = role
                # Count nodes in role
                result = await db.execute(select(Node))
                all_nodes = result.scalars().all()
                job["total_nodes"] = len(all_nodes)
            else:
                result = await db.execute(select(Node))
                all_nodes = result.scalars().all()
                job["total_nodes"] = len(all_nodes)

        job["message"] = "Running apt update on fleet nodes..."
        job["progress"] = 10

        await _broadcast_job_update(
            job_id, "running", 10, job["message"]
        )

        # Execute the playbook
        result = await executor.execute_playbook(
            playbook_name="check-system-updates.yml",
            limit=limit,
            extra_vars=extra_vars if extra_vars else None,
        )

        job["progress"] = 70
        job["message"] = "Parsing discovered packages..."

        # Parse results
        host_results = _parse_discover_output(result["output"])

        if not result["success"] and not host_results:
            job["status"] = "failed"
            job["message"] = f"Playbook failed: {result['output'][:500]}"
            job["completed_at"] = datetime.utcnow().isoformat()
            return

        # Store results in DB
        total_packages = 0
        async with db_service.session() as db:
            # Clear old unapplied updates for checked nodes
            for host_data in host_results:
                hostname = host_data.get("hostname", "")
                node_id = await _resolve_hostname_to_node(
                    db, hostname
                )
                if not node_id:
                    logger.warning(
                        "Unknown hostname from Ansible: %s", hostname
                    )
                    continue

                # Remove stale unapplied updates for this node
                await db.execute(
                    UpdateInfo.__table__.delete().where(
                        UpdateInfo.node_id == node_id,
                        UpdateInfo.is_applied.is_(False),
                    )
                )

                # Insert new updates
                packages = host_data.get("packages", [])
                security_pkgs = host_data.get(
                    "security_packages", []
                )
                held = host_data.get("held", [])

                for pkg_json in packages:
                    if isinstance(pkg_json, str):
                        try:
                            pkg = json.loads(pkg_json)
                        except json.JSONDecodeError:
                            continue
                    else:
                        pkg = pkg_json

                    if not isinstance(pkg, dict):
                        continue
                    if pkg.get("p") in held:
                        continue

                    severity = _classify_severity(
                        pkg["p"], security_pkgs
                    )
                    await _upsert_update_info(
                        db, node_id, pkg, severity
                    )
                    total_packages += 1

                job["nodes_checked"] = (
                    job.get("nodes_checked", 0) + 1
                )

            await db.commit()

        job["status"] = "completed"
        job["progress"] = 100
        job["packages_found"] = total_packages
        job["message"] = (
            f"Found {total_packages} upgradable packages "
            f"across {job['nodes_checked']} nodes"
        )
        job["completed_at"] = datetime.utcnow().isoformat()

        await _broadcast_job_update(
            job_id, "completed", 100, job["message"]
        )

    except Exception as e:
        logger.exception("Discover job failed: %s", job_id)
        job["status"] = "failed"
        job["message"] = str(e)
        job["completed_at"] = datetime.utcnow().isoformat()
        await _broadcast_job_update(
            job_id, "failed", job.get("progress", 0), str(e)
        )
```

**Step 3: Add the discover endpoints**

Add after the helper functions (before the existing `@router.get("/check")` on line 276):

```python
@router.post("/discover", response_model=UpdateDiscoverResponse)
async def discover_updates(
    request: UpdateDiscoverRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateDiscoverResponse:
    """Trigger package discovery on fleet nodes via Ansible."""
    job_id = str(uuid.uuid4())[:16]

    _discover_jobs[job_id] = {
        "job_id": job_id,
        "status": "pending",
        "progress": 0,
        "message": "Queued for discovery...",
        "nodes_checked": 0,
        "total_nodes": 0,
        "packages_found": 0,
        "started_at": None,
        "completed_at": None,
    }

    asyncio.create_task(
        _run_discover_job(job_id, request.node_ids, request.role)
    )

    logger.info("Discover job created: %s", job_id)
    return UpdateDiscoverResponse(
        success=True,
        message="Update discovery started",
        job_id=job_id,
    )


@router.get(
    "/discover/{job_id}", response_model=UpdateDiscoverStatus
)
async def get_discover_status(
    job_id: str,
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateDiscoverStatus:
    """Poll status of an update discovery job."""
    job = _discover_jobs.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Discovery job not found",
        )
    return UpdateDiscoverStatus(**job)
```

**Step 4: Add summary and packages endpoints**

Add after the discover endpoints:

```python
@router.get("/summary", response_model=UpdateSummaryResponse)
async def get_update_summary(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateSummaryResponse:
    """Lightweight summary for sidebar badge polling."""
    # Count unapplied updates
    total_result = await db.execute(
        select(UpdateInfo).where(UpdateInfo.is_applied.is_(False))
    )
    all_updates = total_result.scalars().all()

    security_count = sum(
        1 for u in all_updates if u.severity == "security"
    )
    nodes_with = len(set(u.node_id for u in all_updates if u.node_id))

    # Last checked = most recent created_at of unapplied updates
    last_checked = None
    if all_updates:
        last_checked = max(u.created_at for u in all_updates)

    return UpdateSummaryResponse(
        system_update_count=len(all_updates),
        security_update_count=security_count,
        nodes_with_updates=nodes_with,
        last_checked=last_checked,
    )


@router.get("/packages", response_model=UpdatePackagesResponse)
async def list_packages(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
    node_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=1000),
) -> UpdatePackagesResponse:
    """List discovered upgradable packages with optional filters."""
    query = select(UpdateInfo).where(UpdateInfo.is_applied.is_(False))

    if node_id:
        query = query.where(UpdateInfo.node_id == node_id)
    if severity:
        query = query.where(UpdateInfo.severity == severity)

    query = query.order_by(
        UpdateInfo.severity.desc(), UpdateInfo.package_name
    ).limit(limit)

    result = await db.execute(query)
    packages = result.scalars().all()

    # Build by_node counts
    by_node: Dict[str, int] = defaultdict(int)
    for pkg in packages:
        if pkg.node_id:
            by_node[pkg.node_id] += 1

    return UpdatePackagesResponse(
        packages=[
            UpdateInfoResponse.model_validate(p) for p in packages
        ],
        total=len(packages),
        by_node=dict(by_node),
    )
```

**Step 5: Update the apply endpoint to support upgrade_all**

Modify the existing `apply_updates` endpoint (line 432) to also accept `UpdateApplyAllRequest`. Add a new endpoint:

```python
@router.post("/apply-all")
async def apply_all_updates(
    request: UpdateApplyAllRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[dict, Depends(get_current_user)],
) -> UpdateApplyResponse:
    """Apply all available updates on a node (apt upgrade)."""
    result = await db.execute(
        select(Node).where(Node.node_id == request.node_id)
    )
    node = result.scalar_one_or_none()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Node not found",
        )

    job_id = str(uuid.uuid4())[:16]
    job = UpdateJob(
        job_id=job_id,
        node_id=request.node_id,
        status=UpdateJobStatus.PENDING.value,
        update_ids=[],
        total_steps=1,
    )
    db.add(job)
    await db.commit()

    async def _run_upgrade_all(jid: str, nid: str) -> None:
        from services.database import db_service

        async with db_service.session() as sess:
            res = await sess.execute(
                select(UpdateJob).where(UpdateJob.job_id == jid)
            )
            j = res.scalar_one_or_none()
            if not j:
                return
            n_res = await sess.execute(
                select(Node).where(Node.node_id == nid)
            )
            n = n_res.scalar_one_or_none()
            if not n:
                j.status = UpdateJobStatus.FAILED.value
                j.error = "Node not found"
                j.completed_at = datetime.utcnow()
                await sess.commit()
                return

            j.status = UpdateJobStatus.RUNNING.value
            j.started_at = datetime.utcnow()
            j.current_step = "Running apt upgrade on node"
            await sess.commit()
            await _broadcast_job_update(
                jid, "running", 10, j.current_step
            )

            try:
                executor = get_playbook_executor()
                r = await executor.execute_playbook(
                    playbook_name="apply-system-updates.yml",
                    limit=[n.hostname],
                    extra_vars={
                        "update_type": "all",
                        "dry_run": "false",
                        "auto_reboot": "false",
                    },
                )
                if r["success"]:
                    j.status = UpdateJobStatus.COMPLETED.value
                    j.progress = 100
                    j.output = r["output"]
                    # Mark all updates for this node as applied
                    await sess.execute(
                        UpdateInfo.__table__.update()
                        .where(
                            UpdateInfo.node_id == nid,
                            UpdateInfo.is_applied.is_(False),
                        )
                        .values(
                            is_applied=True,
                            applied_at=datetime.utcnow(),
                        )
                    )
                else:
                    j.status = UpdateJobStatus.FAILED.value
                    j.error = r["output"][:500]
                    j.output = r["output"]
                j.completed_at = datetime.utcnow()
                await sess.commit()
                await _broadcast_job_update(
                    jid, j.status, j.progress, j.current_step
                )
            except Exception as e:
                logger.exception(
                    "Upgrade all failed: %s", jid
                )
                j.status = UpdateJobStatus.FAILED.value
                j.error = str(e)
                j.completed_at = datetime.utcnow()
                await sess.commit()

    task = asyncio.create_task(
        _run_upgrade_all(job_id, request.node_id)
    )
    _running_jobs[job_id] = task

    return UpdateApplyResponse(
        success=True,
        message="Upgrade all started",
        job_id=job_id,
    )
```

**Step 6: Add new schema imports**

At the top of `updates.py`, add to the schema imports:

```python
from models.schemas import (
    ...existing imports...,
    UpdateApplyAllRequest,
    UpdateDiscoverRequest,
    UpdateDiscoverResponse,
    UpdateDiscoverStatus,
    UpdatePackagesResponse,
    UpdateSummaryResponse,
)
```

**Step 7: Verify backend starts**

Run: `cd /home/kali/Desktop/AutoBot/autobot-slm-backend && python3 -c "from api.updates import router; print('Endpoints:', len(router.routes))"`

Expected: More endpoints than before (was 6, should be ~10+).

**Step 8: Commit**

```bash
git add autobot-slm-backend/api/updates.py autobot-slm-backend/models/schemas.py
git commit -m "feat(updates): add discover, summary, packages, apply-all endpoints

- POST /api/updates/discover: triggers Ansible check-system-updates.yml
- GET /api/updates/discover/{job_id}: poll discovery progress
- GET /api/updates/summary: lightweight badge count endpoint
- GET /api/updates/packages: list upgradable packages with filters
- POST /api/updates/apply-all: apt upgrade all on a node
- Parses AUTOBOT_UPDATES_JSON markers from Ansible stdout
- Dedup by node_id + package_name, clears stale on re-check"
```

---

## Task 4: Frontend Composable — useSystemUpdates.ts

**Files:**
- Create: `autobot-slm-frontend/src/composables/useSystemUpdates.ts`

**Step 1: Create the composable**

Follow the same pattern as `useCodeSync.ts`:

```typescript
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * System Updates Composable
 *
 * Provides reactive state and methods for system package update
 * discovery and management across the SLM fleet.
 */

import { ref, computed, readonly } from 'vue'
import axios, { type AxiosInstance } from 'axios'

const API_BASE = '/api'

// =============================================================================
// Type Definitions
// =============================================================================

export interface UpdateSummary {
  system_update_count: number
  security_update_count: number
  nodes_with_updates: number
  last_checked: string | null
}

export interface UpdatePackage {
  update_id: string
  node_id: string | null
  package_name: string
  current_version: string | null
  available_version: string
  severity: string
  description: string | null
  is_applied: boolean
  applied_at: string | null
  created_at: string
}

export interface PackagesResponse {
  packages: UpdatePackage[]
  total: number
  by_node: Record<string, number>
}

export interface DiscoverResponse {
  success: boolean
  message: string
  job_id: string
}

export interface DiscoverStatus {
  job_id: string
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message: string | null
  nodes_checked: number
  total_nodes: number
  packages_found: number
  started_at: string | null
  completed_at: string | null
}

export interface UpdateJob {
  job_id: string
  node_id: string
  status: string
  progress: number
  current_step: string | null
  total_steps: number
  completed_steps: number
  error: string | null
  output: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string
}

// =============================================================================
// Composable
// =============================================================================

export function useSystemUpdates() {
  const client: AxiosInstance = axios.create({
    baseURL: API_BASE,
    headers: { 'Content-Type': 'application/json' },
  })

  client.interceptors.request.use((config) => {
    const token = localStorage.getItem('slm_access_token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // ===========================================================================
  // Reactive State
  // ===========================================================================

  const summary = ref<UpdateSummary | null>(null)
  const packages = ref<UpdatePackage[]>([])
  const packagesByNode = ref<Record<string, number>>({})
  const jobs = ref<UpdateJob[]>([])
  const discoverStatus = ref<DiscoverStatus | null>(null)
  const loading = ref(false)
  const discovering = ref(false)
  const error = ref<string | null>(null)

  // ===========================================================================
  // Computed Properties
  // ===========================================================================

  const updateCount = computed(() => summary.value?.system_update_count ?? 0)

  const securityCount = computed(
    () => summary.value?.security_update_count ?? 0,
  )

  const nodesWithUpdates = computed(
    () => summary.value?.nodes_with_updates ?? 0,
  )

  const hasUpdates = computed(() => updateCount.value > 0)

  const lastChecked = computed(() => summary.value?.last_checked ?? null)

  const isDiscovering = computed(
    () =>
      discovering.value ||
      (discoverStatus.value?.status === 'running' ||
        discoverStatus.value?.status === 'pending'),
  )

  const hasRunningJobs = computed(() =>
    jobs.value.some(
      (j) => j.status === 'pending' || j.status === 'running',
    ),
  )

  // ===========================================================================
  // API Methods
  // ===========================================================================

  async function fetchSummary(): Promise<UpdateSummary | null> {
    try {
      const response = await client.get<UpdateSummary>(
        '/updates/summary',
      )
      summary.value = response.data
      return response.data
    } catch (e) {
      // Silent fail for badge polling — don't overwrite error
      return null
    }
  }

  async function fetchPackages(
    nodeId?: string,
    severity?: string,
  ): Promise<UpdatePackage[]> {
    loading.value = true
    error.value = null
    try {
      const params: Record<string, string> = {}
      if (nodeId) params.node_id = nodeId
      if (severity) params.severity = severity
      const response = await client.get<PackagesResponse>(
        '/updates/packages',
        { params },
      )
      packages.value = response.data.packages
      packagesByNode.value = response.data.by_node
      return response.data.packages
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to fetch packages'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return []
    } finally {
      loading.value = false
    }
  }

  async function discoverUpdates(
    nodeIds?: string[],
    role?: string,
  ): Promise<string | null> {
    discovering.value = true
    error.value = null
    try {
      const response = await client.post<DiscoverResponse>(
        '/updates/discover',
        { node_ids: nodeIds || null, role: role || null },
      )
      if (response.data.success) {
        discoverStatus.value = {
          job_id: response.data.job_id,
          status: 'pending',
          progress: 0,
          message: 'Starting discovery...',
          nodes_checked: 0,
          total_nodes: 0,
          packages_found: 0,
          started_at: null,
          completed_at: null,
        }
        return response.data.job_id
      }
      error.value = response.data.message
      return null
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to start discovery'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return null
    } finally {
      discovering.value = false
    }
  }

  async function pollDiscoverStatus(
    jobId: string,
  ): Promise<DiscoverStatus | null> {
    try {
      const response = await client.get<DiscoverStatus>(
        `/updates/discover/${jobId}`,
      )
      discoverStatus.value = response.data
      return response.data
    } catch (e) {
      return null
    }
  }

  async function fetchJobs(limit = 20): Promise<UpdateJob[]> {
    try {
      const response = await client.get<{
        jobs: UpdateJob[]
        total: number
      }>('/updates/jobs', { params: { limit } })
      jobs.value = response.data.jobs
      return response.data.jobs
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to fetch jobs'
      return []
    }
  }

  async function applyUpdates(
    nodeId: string,
    updateIds: string[],
  ): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response = await client.post('/updates/apply', {
        node_id: nodeId,
        update_ids: updateIds,
      })
      if (response.data.success) {
        await fetchJobs()
        return true
      }
      error.value = response.data.message
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to apply updates'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function upgradeAll(nodeId: string): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const response = await client.post('/updates/apply-all', {
        node_id: nodeId,
        upgrade_all: true,
      })
      if (response.data.success) {
        await fetchJobs()
        return true
      }
      error.value = response.data.message
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to upgrade all'
      if (axios.isAxiosError(e) && e.response?.data?.detail) {
        error.value = e.response.data.detail
      }
      return false
    } finally {
      loading.value = false
    }
  }

  async function cancelJob(jobId: string): Promise<boolean> {
    try {
      const response = await client.post(
        `/updates/jobs/${jobId}/cancel`,
      )
      if (response.data.success) {
        await fetchJobs()
        return true
      }
      return false
    } catch (e) {
      error.value =
        e instanceof Error ? e.message : 'Failed to cancel job'
      return false
    }
  }

  function clearError(): void {
    error.value = null
  }

  // ===========================================================================
  // Return Public API
  // ===========================================================================

  return {
    // State (readonly)
    summary: readonly(summary),
    packages: readonly(packages),
    packagesByNode: readonly(packagesByNode),
    jobs: readonly(jobs),
    discoverStatus: readonly(discoverStatus),
    loading: readonly(loading),
    discovering: readonly(discovering),
    error: readonly(error),

    // Computed
    updateCount,
    securityCount,
    nodesWithUpdates,
    hasUpdates,
    lastChecked,
    isDiscovering,
    hasRunningJobs,

    // Methods
    fetchSummary,
    fetchPackages,
    discoverUpdates,
    pollDiscoverStatus,
    fetchJobs,
    applyUpdates,
    upgradeAll,
    cancelJob,
    clearError,
  }
}
```

**Step 2: Commit**

```bash
git add autobot-slm-frontend/src/composables/useSystemUpdates.ts
git commit -m "feat(updates): add useSystemUpdates composable

Provides reactive state and methods for system package discovery,
listing, applying, and badge polling. Follows useCodeSync pattern."
```

---

## Task 5: Frontend — SystemUpdatesTab.vue Redesign

**Files:**
- Modify: `autobot-slm-frontend/src/views/SystemUpdatesTab.vue` (full rewrite — 382 lines)

**Step 1: Rewrite SystemUpdatesTab.vue**

Replace entire file with the redesigned component. Key sections:
1. Action bar with "Check for Updates" button + node filter
2. Discovery progress bar
3. Summary stats cards (total, security, nodes, last checked)
4. Available packages table with checkboxes, grouped by node
5. Upgrade jobs table (kept from original)

The component uses `useSystemUpdates()` composable and `useFleetStore()`.

Key behaviors:
- On mount: fetch packages + jobs + summary
- "Check for Updates": calls `discoverUpdates()`, starts polling `pollDiscoverStatus()` every 3s
- When discovery completes: refresh packages list
- Package selection: checkboxes, "Upgrade Selected" button
- Per-node "Upgrade All" button
- Job polling every 10s when jobs are running

**Step 2: Verify build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-slm-frontend && npx vue-tsc --noEmit 2>&1 | head -20`

Expected: No type errors in SystemUpdatesTab.vue

**Step 3: Commit**

```bash
git add autobot-slm-frontend/src/views/SystemUpdatesTab.vue
git commit -m "feat(updates): redesign SystemUpdatesTab with package discovery

- Action bar with Check for Updates button and node filter
- Discovery progress bar with per-node status
- Summary stats cards (total, security, nodes, last checked)
- Available packages table with multi-select and severity badges
- Upgrade Selected / Upgrade All per-node actions
- Existing job tracking table preserved"
```

---

## Task 6: Frontend — Tab Badge + Sidebar Combined Badge

**Files:**
- Modify: `autobot-slm-frontend/src/views/UpdatesView.vue` (87 lines)
- Modify: `autobot-slm-frontend/src/components/common/Sidebar.vue` (362 lines)

**Step 1: Add system updates badge to UpdatesView.vue tabs**

In `UpdatesView.vue`:
- Import `useSystemUpdates` composable
- Add orange badge to System Updates tab showing `systemUpdates.updateCount.value`
- Keep existing Code Sync badge

Changes to `UpdatesView.vue`:
```typescript
// Add import
import { useSystemUpdates } from '@/composables/useSystemUpdates'

// Add in setup
const systemUpdates = useSystemUpdates()
```

In template, add badge to the system tab button (alongside existing code-sync badge):
```html
<!-- System updates badge -->
<span
  v-if="tab.id === 'system' && systemUpdates.updateCount.value > 0"
  class="ml-2 inline-flex items-center justify-center
         min-w-[20px] h-5 px-1 text-xs font-bold
         text-white bg-orange-500 rounded-full"
>
  {{ systemUpdates.updateCount.value }}
</span>
```

**Step 2: Update Sidebar.vue for combined badge**

In `Sidebar.vue`:
- Import `useSystemUpdates` composable
- Modify the badge display to show combined count (system + code sync)
- Poll system updates summary alongside code sync

Changes to `Sidebar.vue`:
```typescript
// Add import
import { useSystemUpdates } from '@/composables/useSystemUpdates'

// Add in setup
const systemUpdates = useSystemUpdates()
```

Modify `onMounted` to also poll system updates:
```typescript
onMounted(async () => {
  if (!authStore.isAuthenticated) return
  await Promise.all([
    refreshCodeSyncStatus(),
    systemUpdates.fetchSummary(),
  ])
  codeSyncPollTimer = setInterval(() => {
    refreshCodeSyncStatus()
    systemUpdates.fetchSummary()
  }, CODE_SYNC_POLL_INTERVAL)
})
```

Modify the badge in template to show combined count:
```html
<span
  v-if="item.showBadge && (
    codeSync.hasOutdatedNodes.value ||
    systemUpdates.hasUpdates.value
  )"
  :class="[
    'nav-badge',
    systemUpdates.hasUpdates.value ? 'nav-badge--system' : ''
  ]"
  :aria-label="`${
    (systemUpdates.updateCount.value || 0) +
    (codeSync.outdatedCount.value || 0)
  } updates available`"
  role="status"
>
  {{
    (systemUpdates.updateCount.value || 0) +
    (codeSync.outdatedCount.value || 0)
  }}
</span>
```

Add style for system update badge color:
```css
.nav-badge--system {
  background: #f97316; /* orange-500 for system updates */
}
```

**Step 3: Verify build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-slm-frontend && npx vue-tsc --noEmit 2>&1 | head -20`

Expected: No type errors.

**Step 4: Commit**

```bash
git add autobot-slm-frontend/src/views/UpdatesView.vue autobot-slm-frontend/src/components/common/Sidebar.vue
git commit -m "feat(updates): add combined sidebar badge and per-tab indicators

- Sidebar badge shows combined count (system updates + code sync)
- Orange when system updates present, amber for code sync only
- System Updates tab shows orange badge with package count
- Code Sync tab badge unchanged
- Sidebar polls system update summary every 60s"
```

---

## Task 7: Final Build + Verification

**Step 1: Full frontend build**

Run: `cd /home/kali/Desktop/AutoBot/autobot-slm-frontend && npm run build`

Expected: Build succeeds with no errors.

**Step 2: Backend lint check**

Run: `cd /home/kali/Desktop/AutoBot && flake8 autobot-slm-backend/api/updates.py --max-line-length=100`

Expected: No lint errors (or only pre-existing ones).

**Step 3: Verify all files**

Run: `git diff --stat HEAD~6` (or however many commits made)

Expected: Shows all changed files matching the plan.
