# Company OS project ↔ repo linkage (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a Company OS project attach an existing GitHub repo by linking it to a codebase-analytics `CodeSource` (which already handles clone + token + ChromaDB indexing), and surface the repo + workspace path + analytics grouping in the UI.

**Architecture:** Add one nullable `code_source_id` column to `LLCProject`. Extract a thin `create_github_source()` service from the existing sources HTTP handler (DRY) and reuse it from the LLC layer. New LLC endpoints attach/detach/list-with-repos. Frontend shows the linked repo, `clone_path`, sync status + attach/sync/detach actions; the analytics view groups sources by owning project. No new clone/index engine — reuse `CodeSource`.

**Tech Stack:** Python/FastAPI (autobot-backend), SQLAlchemy async + Alembic, Redis (analytics db) for source storage, pytest; Vue 3 + TS (autobot-frontend), vitest, vue-tsc.

## Global Constraints

- Worktree `.worktrees/issue-11129`, branch `issue-11129`. Base/PR target `Dev_new_gui`. Umbrella #11129.
- Python line length 120; functions ≤30 lines where reasonable; `encoding="utf-8"` explicit; logging via `get_logger(__name__)` (no print). New Python files: `# Copyright 2025-2026 mrveiss` + `# SPDX-License-Identifier: Apache-2.0`.
- Reuse — do NOT reimplement clone/token/index. The source is stored in Redis via `save_source`/`get_source`/`delete_source` (`api/codebase_analytics/source_storage.py`); GitHub sources sync via `_do_sync` (`api/codebase_analytics/endpoints/sources.py`).
- LLC endpoints use `session: AsyncSession = Depends(get_session)`, `_current_user: dict = Depends(get_current_user)`, `ctx: TenantContext = Depends(require_org_context)` (mirror existing handlers in `llc/api/sprints.py`).
- Frontend: no `console.*` (use `createLogger`); ApiClient returns parsed JSON directly.
- Commit format `<type>(scope): <desc> (#11129)`. Never `--no-verify`.

---

### Task 1: Add `code_source_id` to LLCProject (model + migration)

**Files:**
- Modify: `autobot-backend/llc/models/sprint.py` (LLCProject — add column)
- Create: `autobot-backend/migrations/versions/20260707_0XX_llc_project_code_source.py`
- Test: `autobot-backend/llc/tests/test_project_code_source_model.py`

**Interfaces:**
- Produces: `LLCProject.code_source_id: Optional[str]` (nullable, indexed).

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/llc/tests/test_project_code_source_model.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
from llc.models.sprint import LLCProject


def test_llcproject_has_code_source_id_column():
    assert "code_source_id" in LLCProject.__table__.columns
    col = LLCProject.__table__.columns["code_source_id"]
    assert col.nullable is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && PYTHONPATH=/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-11129:$PWD python3 -m pytest llc/tests/test_project_code_source_model.py -q`
Expected: FAIL — `code_source_id` not in columns.

- [ ] **Step 3: Add the column to `LLCProject`**

In `sprint.py`, in `class LLCProject`, after the `env` column add:

```python
    # Company OS project ↔ codebase-analytics CodeSource link (#11129).
    code_source_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
```

- [ ] **Step 4: Write the Alembic migration**

Find the latest revision: `ls autobot-backend/migrations/versions | sort | tail -1` and use its `revision` as this migration's `down_revision`. Create the file:

```python
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""llc project code_source link (#11129)."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260707_0XX"          # set to a new unique id following the dir convention
down_revision: Union[str, None] = "<LATEST>"   # set from the current head
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("llc_projects", sa.Column("code_source_id", sa.String(length=64), nullable=True))
    op.create_index("ix_llc_projects_code_source_id", "llc_projects", ["code_source_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_projects_code_source_id", table_name="llc_projects")
    op.drop_column("llc_projects", "code_source_id")
```

- [ ] **Step 5: Run the model test (passes) + commit**

Run: `cd autobot-backend && PYTHONPATH=…:$PWD python3 -m pytest llc/tests/test_project_code_source_model.py -q` → PASS.

```bash
git add autobot-backend/llc/models/sprint.py autobot-backend/migrations/versions/20260707_0XX_llc_project_code_source.py autobot-backend/llc/tests/test_project_code_source_model.py
git commit -m "feat(llc): add code_source_id link column to LLCProject (#11129)"
```

---

### Task 2: Extract `create_github_source()` service (DRY)

Reuse-from-both: the LLC layer must create a source without going through HTTP. Extract the create logic from the handler into a service function; re-point the handler.

**Files:**
- Create: `autobot-backend/api/codebase_analytics/source_service.py`
- Modify: `autobot-backend/api/codebase_analytics/endpoints/sources.py` (call the service)
- Test: `autobot-backend/api/codebase_analytics/source_service_test.py`

**Interfaces:**
- Produces: `async def create_github_source(*, name: str, repo: str, credential_id: str | None, branch: str = "main", owner_id: str | None = None, auto_sync: bool = True) -> CodeSource` — builds a github `CodeSource`, `save_source`s it, and (if `auto_sync`) kicks off the background sync; returns the source.
- Consumes: `CodeSource`, `save_source` (`source_storage.py`), `_do_sync` (`endpoints/sources.py`).

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/api/codebase_analytics/source_service_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import pytest

from api.codebase_analytics import source_service
from api.codebase_analytics.source_models import SourceType


@pytest.mark.asyncio
async def test_create_github_source_builds_and_saves(monkeypatch):
    saved = {}

    async def fake_save(src):
        saved["src"] = src
        return True

    monkeypatch.setattr(source_service, "save_source", fake_save)
    src = await source_service.create_github_source(
        name="acme/site", repo="acme/site", credential_id="cred1", branch="main", auto_sync=False
    )
    assert src.source_type == SourceType.GITHUB
    assert src.repo == "acme/site"
    assert src.credential_id == "cred1"
    assert saved["src"].id == src.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && PYTHONPATH=…:$PWD python3 -m pytest api/codebase_analytics/source_service_test.py -q`
Expected: FAIL — `source_service` module / `create_github_source` missing.

- [ ] **Step 3: Write the service**

Read `endpoints/sources.py::create_code_source` first to copy its exact `CodeSource(...)` construction (name/source_type/repo/branch/credential_id/access/owner_id) and its `_do_sync` kickoff. Then:

```python
# autobot-backend/api/codebase_analytics/source_service.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Service-layer helpers for CodeSource create/delete so non-HTTP callers
(the LLC project layer, #11129) can reuse the same logic as the sources API."""
from __future__ import annotations

import asyncio

from autobot_shared.logging_manager import get_logger

from .source_models import CodeSource, SourceAccess, SourceType
from .source_storage import save_source

logger = get_logger(__name__)


async def create_github_source(
    *,
    name: str,
    repo: str,
    credential_id: str | None,
    branch: str = "main",
    owner_id: str | None = None,
    access: SourceAccess = SourceAccess.PRIVATE,
    auto_sync: bool = True,
) -> CodeSource:
    """Create + persist a GitHub CodeSource and (optionally) kick off its sync."""
    source = CodeSource(
        name=name,
        source_type=SourceType.GITHUB,
        repo=repo,
        branch=branch,
        credential_id=credential_id,
        owner_id=owner_id,
        access=access,
    )
    await save_source(source)
    if auto_sync:
        # Import here to avoid a circular import with endpoints/sources.py.
        from .endpoints.sources import _do_sync

        asyncio.create_task(_do_sync(source))
    logger.info("Created github CodeSource %s for repo %s", source.id, repo)
    return source
```

(Confirm `SourceType.GITHUB` is the exact enum member name — `grep -n "class SourceType" -A6 api/codebase_analytics/source_models.py`. Use the real member.)

- [ ] **Step 4: Re-point the HTTP handler**

In `endpoints/sources.py::create_code_source`, replace the inline `CodeSource(...)` + `save_source` + `_do_sync` block with a call to `source_service.create_github_source(...)` for the github branch (keep the local-source branch as-is). Import `from api.codebase_analytics import source_service`.

- [ ] **Step 5: Run tests (service + existing sources tests) + commit**

Run: `cd autobot-backend && PYTHONPATH=…:$PWD python3 -m pytest api/codebase_analytics/source_service_test.py -q && python3 -m pytest api/codebase_analytics -k "source" -q`
Expected: PASS (service test + existing source tests still green).

```bash
git add autobot-backend/api/codebase_analytics/source_service.py autobot-backend/api/codebase_analytics/source_service_test.py autobot-backend/api/codebase_analytics/endpoints/sources.py
git commit -m "refactor(analytics): extract create_github_source service for reuse (#11129)"
```

---

### Task 3: LLC project ↔ repo endpoints

**Files:**
- Modify: `autobot-backend/llc/api/sprints.py` (add endpoints + `CodeSourceSummary`, extend `ProjectResponse`)
- Test: `autobot-backend/llc/tests/test_project_repo_api.py`

**Interfaces:**
- Consumes: `create_github_source` (Task 2); `get_source`/`delete_source` (`source_storage.py`); `LLCProject.code_source_id` (Task 1).
- Produces routes: `POST /api/llc/projects/{id}/repo`, `DELETE /api/llc/projects/{id}/repo`, `GET /api/llc/projects/with-repos`; `ProjectResponse.code_source_id: str | None` + `.code_source: CodeSourceSummary | None`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/llc/tests/test_project_repo_api.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import pytest
from httpx import ASGITransport, AsyncClient

# Mirror the app/fixtures used by the other llc/api tests (e.g. test_projects_api.py):
# reuse their conftest fixtures for the FastAPI app + auth/org overrides.


@pytest.mark.asyncio
async def test_attach_repo_sets_code_source(llc_client, a_project):  # fixtures from llc conftest
    r = await llc_client.post(
        f"/api/llc/projects/{a_project['id']}/repo",
        json={"repo": "acme/site", "credential_id": "cred1", "branch": "main"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["code_source_id"]
    assert body["code_source"]["repo"] == "acme/site"


@pytest.mark.asyncio
async def test_detach_repo_unlinks_but_keeps_source(llc_client, a_project_with_repo):
    r = await llc_client.delete(f"/api/llc/projects/{a_project_with_repo['id']}/repo")
    assert r.status_code == 200
    assert r.json()["code_source_id"] is None
```

(If the llc test suite lacks reusable `llc_client`/`a_project` fixtures, add them to `llc/tests/conftest.py` mirroring `test_projects_api.py`'s app setup — patch `create_github_source` + `get_source` to avoid real Redis/clone in these tests.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && PYTHONPATH=…:$PWD python3 -m pytest llc/tests/test_project_repo_api.py -q`
Expected: FAIL — routes 404 / attributes missing.

- [ ] **Step 3: Extend `ProjectResponse` + add `CodeSourceSummary`**

In `sprints.py`, near `ProjectResponse`:

```python
class CodeSourceSummary(BaseModel):
    id: str
    repo: Optional[str] = None
    branch: Optional[str] = None
    clone_path: Optional[str] = None
    status: Optional[str] = None
    error_message: Optional[str] = None
```

Add to `ProjectResponse`: `code_source_id: Optional[str] = None` and `code_source: Optional[CodeSourceSummary] = None`. A helper resolves the summary from the sources store:

```python
from api.codebase_analytics.source_storage import get_source, delete_source
from api.codebase_analytics import source_service

async def _project_source_summary(code_source_id: Optional[str]) -> Optional[CodeSourceSummary]:
    if not code_source_id:
        return None
    src = await get_source(code_source_id)
    if not src:
        return None
    return CodeSourceSummary(id=src.id, repo=src.repo, branch=src.branch,
                             clone_path=src.clone_path, status=str(src.status), error_message=src.error_message)
```

(Detail/list endpoints that return `ProjectResponse` should set `.code_source` via this helper. For list endpoints, keep it optional to avoid N+1 — populate only on the detail read + the new `with-repos` endpoint.)

- [ ] **Step 4: Add the endpoints**

```python
class AttachRepoRequest(BaseModel):
    repo: str = Field(..., pattern=r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
    credential_id: Optional[str] = None
    branch: str = "main"


@router.post("/projects/{project_id}/repo", response_model=ProjectResponse)
async def attach_project_repo(
    project_id: uuid.UUID,
    body: AttachRepoRequest,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
):
    project = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    # Re-attach: unlink the previous source link (source object is left intact).
    src = await source_service.create_github_source(
        name=f"{project.name} ({body.repo})", repo=body.repo,
        credential_id=body.credential_id, branch=body.branch,
        owner_id=str(_current_user.get("id") or _current_user.get("user_id") or ""),
    )
    project.code_source_id = src.id
    await session.commit()
    await session.refresh(project)
    resp = ProjectResponse.model_validate(project)
    resp.code_source = await _project_source_summary(project.code_source_id)
    return resp


@router.delete("/projects/{project_id}/repo", response_model=ProjectResponse)
async def detach_project_repo(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
):
    project = (await session.execute(select(LLCProject).where(LLCProject.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    project.code_source_id = None       # unlink only; source survives (deleted on disposal, Phase 2)
    await session.commit()
    await session.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("/projects/with-repos", response_model=List[ProjectResponse])
async def list_projects_with_repos(
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
):
    rows = (await session.execute(select(LLCProject).where(LLCProject.code_source_id.isnot(None)))).scalars().all()
    out: List[ProjectResponse] = []
    for p in rows:
        resp = ProjectResponse.model_validate(p)
        resp.code_source = await _project_source_summary(p.code_source_id)
        out.append(resp)
    return out
```

(Place `GET /projects/with-repos` BEFORE `GET /projects/{project_id}` in the file if FastAPI would otherwise match `with-repos` as a `{project_id}` — since `project_id` is typed `uuid.UUID`, `with-repos` won't parse as a UUID and is safe, but ordering it first is clearer.)

- [ ] **Step 4b: Run test to verify it passes**

Run: `cd autobot-backend && PYTHONPATH=…:$PWD python3 -m pytest llc/tests/test_project_repo_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/llc/api/sprints.py autobot-backend/llc/tests/test_project_repo_api.py autobot-backend/llc/tests/conftest.py
git commit -m "feat(llc): attach/detach project repo via CodeSource + with-repos endpoint (#11129)"
```

---

### Task 4: Frontend — project repo UI + analytics grouping

**Files:**
- Modify: `autobot-frontend/src/views/llc/ProjectBrowserView.vue` (show repo + clone_path + attach/sync/detach)
- Modify: the LLC project API composable/client used by that view (add `attachRepo`/`detachRepo`/`listWithRepos`)
- Modify: `autobot-frontend/src/components/analytics/CodebaseAnalytics.vue` (group/label sources by project)
- Test: `autobot-frontend/src/views/llc/__tests__/ProjectBrowserView.repo.test.ts`

**Interfaces:**
- Consumes: `POST /api/llc/projects/{id}/repo`, `DELETE …/repo`, `GET /api/llc/projects/with-repos`.

- [ ] **Step 1: Write the failing test**

```ts
// autobot-frontend/src/views/llc/__tests__/ProjectBrowserView.repo.test.ts
import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
// Mock the api client used by ProjectBrowserView (match how the existing enrichment test mocks it).
// Assert: a project with code_source shows its repo + clone_path; "Attach repo" calls POST …/repo.
describe('ProjectBrowserView repo linkage', () => {
  it('shows the linked repo + workspace path', async () => {
    // ...mount with a project fixture that has code_source {repo, clone_path, status}; assert text.
    expect(true).toBe(true) // replace with real assertions mirroring ProjectBrowserView.enrichment.test.ts
  })
})
```

(Model this file on the existing `ProjectBrowserView.enrichment.test.ts` — reuse its mount + api-mock setup so the fixtures/mocks match the real component.)

- [ ] **Step 2: Run test to verify it fails**, then implement:
- Read `ProjectBrowserView.enrichment.test.ts` + `ProjectBrowserView.vue` to match the api-call pattern (`api.get<...>('/api/llc/...')`).
- Add to the project card/detail: when `p.code_source` is set, show `code_source.repo` (link to `https://github.com/<repo>`), the `clone_path` (copyable), and `code_source.status`. Add an "Attach repo" control (inputs `owner/repo` + a credential picker sourced from the existing stored-GitHub-credentials list → `POST /api/llc/projects/{id}/repo`), a "Sync" button (calls the source sync endpoint `POST /api/analytics/... /sources/{id}/sync` — confirm the exact analytics sync route), and "Detach" (`DELETE …/repo`).
- In `CodebaseAnalytics.vue`, fetch `GET /api/llc/projects/with-repos` and label/group each analytics source by its owning project when present.

- [ ] **Step 3: Verify + commit**

Run: `cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json && npx vitest run src/views/llc/__tests__/ProjectBrowserView.repo.test.ts && npx eslint src/views/llc/ProjectBrowserView.vue`
Expected: 0 type errors, test passes, eslint clean.

```bash
git add autobot-frontend/src/views/llc/ProjectBrowserView.vue autobot-frontend/src/components/analytics/CodebaseAnalytics.vue autobot-frontend/src/views/llc/__tests__/ProjectBrowserView.repo.test.ts
git commit -m "feat(companyos): project repo linkage UI + analytics grouping (#11129)"
```

---

### Task 5: Verification + PR

- [ ] Backend: `cd autobot-backend && PYTHONPATH=/home/martins/AutoBot-Ai/AutoBot-AI/.worktrees/issue-11129:$PWD python3 -m pytest llc/tests/test_project_code_source_model.py llc/tests/test_project_repo_api.py api/codebase_analytics/source_service_test.py -q` → all pass; `python3 -m pytest api/codebase_analytics -k source -q` (regression) → pass.
- [ ] Frontend: `cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json` → 0 errors; vitest for the new test + `nav`/llc suites touched → pass; eslint clean on changed files.
- [ ] Rebase onto `origin/Dev_new_gui`, push, open PR: `feat(companyos): project ↔ GitHub repo linkage via CodeSource (Phase 1 of #11129)` with the standard headings; `Part of #11129`.

---

## Self-Review

**Spec coverage (Phase 1):** `code_source_id` link → Task 1; reuse CodeSource create → Task 2; attach/detach/with-repos + ProjectResponse summary → Task 3; frontend repo/clone_path display + attach/sync/detach + analytics grouping → Task 4; verification → Task 5. Phase 2 (lifecycle/disposal + SLM policy) is a separate plan (written after Phase 1 lands).

**Placeholder scan:** the `20260707_0XX`/`<LATEST>` migration ids and the "confirm exact enum member / sync route / mirror existing test fixtures" notes each include the exact command to resolve them — they are lookups against real code, not deferred logic. The Task-4 test body is explicitly "model on ProjectBrowserView.enrichment.test.ts" (a concrete existing file) rather than invented fixtures.

**Type consistency:** `CodeSourceSummary` fields match `CodeSource` (`id/repo/branch/clone_path/status/error_message`); `create_github_source(...)` signature identical in Task 2 (def) and Task 3 (call); `code_source_id: Optional[str]` consistent across model (Task 1), response (Task 3), and endpoints.
