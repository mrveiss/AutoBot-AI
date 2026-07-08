# Company OS Project Archive→Dispose Lifecycle — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Company OS (LLC) projects an `active → archived → pending_disposal → disposed` lifecycle (replacing hard-delete), governed by an SLM-configurable disposal policy (retention period + optional second-pair-of-eyes approval; default immediate), where disposal also deletes the linked codebase-analytics `CodeSource` (clone + index) but never the GitHub repo.

**Architecture:** A new nullable `lifecycle_state` column on `LLCProject` (orthogonal to the existing work-status `status` enum). Archive/restore/dispose endpoints on the projects router. A `project_disposal` service performs the cascade delete (work-items → sprints → project → linked non-shared `CodeSource`). A `disposal_policy` reader fetches `{retention_days, require_approval}` from the SLM settings store over HTTP with safe defaults. A Celery-beat sweep disposes due, approved `pending_disposal` projects. A small SLM-frontend panel edits the policy; Company OS frontend gains archive/delete/restore affordances.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (async, Postgres), Alembic, Celery (beat), Pydantic v2, Vue 3 + TS (autobot-frontend + autobot-slm-frontend), pytest, vitest.

## Global Constraints

- **Branch target:** `Dev_new_gui`. Worktree `.worktrees/issue-11129-p2`, branch `issue-11129-p2`.
- **Commit format:** `<type>(scope): <description> (#11129)`. **NO commit trailers** (no Co-Authored-By / Generated-with) — mrveiss is sole author.
- **Copyright header** on every new file: `# Copyright 2025-2026 mrveiss` + `# SPDX-License-Identifier: Apache-2.0`.
- **≤30-line functions**; no `_v2`/`_fix`/`Enhanced`/`Unified` suffix names.
- **Async-first** — never add sync calls to async paths; lazy-import heavy `codebase_analytics` modules inside functions (avoids circular + heavy `__init__`, per Phase 1).
- **Route prefix gotcha:** the LLC router is mounted at `/api/llc`; routes in `sprints.py` use bare paths (e.g. `/projects/{id}/archive` → served at `/api/llc/projects/{id}/archive`). Do NOT add an `/api` prefix inside the router.
- **NEVER delete the GitHub repo** on disposal — only local AutoBot data + the linked `CodeSource` clone/index (and only when that source is not `shared_with` others; else unlink).
- **Logging:** `logging.getLogger(__name__)` / `createLogger('Name')` — no `print()`/`console.*`.
- **Encoding:** always `encoding='utf-8'` explicitly in Python file I/O.
- **Frontend user-facing strings (autobot-frontend / Company OS):** i18n keys added to ALL 11 locale files — no hardcoded UI strings. SLM-frontend panel: follow the SLM console's existing string convention (operator console; match `GeneralSettings.vue`).
- **Disposal policy defaults when unset/unreadable:** `{retention_days: 0, require_approval: false}` (immediate, no approval, no retention).

---

## File Structure

**Backend — new:**
- `autobot-backend/migrations/versions/20260708_067_llc_project_lifecycle.py` — lifecycle columns + `PROJECT_DISPOSAL` enum value.
- `autobot-backend/llc/services/project_disposal.py` — `dispose(project, session)` cascade.
- `autobot-backend/llc/services/disposal_policy.py` — `get_disposal_policy()` (SLM read + defaults) + `DisposalPolicy` dataclass.
- `autobot-backend/llc/scheduler/project_disposal_sweep.py` — Celery-beat sweep task.

**Backend — modified:**
- `autobot-backend/llc/models/sprint.py` — `LLCProject`: add `lifecycle_state`, `archived_at`, `disposal_scheduled_at`, `disposal_approval_id`.
- `autobot-backend/llc/models/enums.py` — `ApprovalType.PROJECT_DISPOSAL`.
- `autobot-backend/api/codebase_analytics/source_service.py` — extract `delete_source_and_cleanup(source_id)`.
- `autobot-backend/api/codebase_analytics/endpoints/sources.py` — repoint DELETE handler to the service.
- `autobot-backend/llc/api/sprints.py` — `ProjectResponse` lifecycle fields; `POST …/archive`, `POST …/restore`, `POST …/dispose`; reroute `DELETE /projects/{id}` through disposal.
- `autobot-backend/celery_app.py` — register the sweep task in `beat_schedule` + explicit import.

**Frontend — modified/new:**
- `autobot-slm-frontend/src/views/settings/DisposalPolicySettings.vue` (new) + its route/nav entry.
- `autobot-frontend/src/views/llc/ProjectBrowserView.vue` — archive/delete/restore actions + lifecycle badge.
- 11 locale files under `autobot-frontend/src/locales/` — new i18n keys.

---

## Task 1: Model + migration (lifecycle columns + PROJECT_DISPOSAL enum)

**Files:**
- Modify: `autobot-backend/llc/models/sprint.py` (`LLCProject`, after `code_source_id` at line 137)
- Modify: `autobot-backend/llc/models/enums.py` (`ApprovalType`, after `SPRINT_CLOSE`)
- Create: `autobot-backend/migrations/versions/20260708_067_llc_project_lifecycle.py`
- Test: `autobot-backend/llc/tests/test_project_lifecycle_model.py`

**Interfaces:**
- Produces: `LLCProject.lifecycle_state: Optional[str]` (values `active|archived|pending_disposal|disposed`, default `active`), `LLCProject.archived_at: Optional[datetime]`, `LLCProject.disposal_scheduled_at: Optional[datetime]`, `LLCProject.disposal_approval_id: Optional[uuid.UUID]`; `ApprovalType.PROJECT_DISPOSAL = "project_disposal"`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/llc/tests/test_project_lifecycle_model.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Model contract for the project archive→dispose lifecycle (#11129 P2)."""
from llc.models.enums import ApprovalType
from llc.models.sprint import LLCProject


def test_project_has_lifecycle_columns():
    cols = LLCProject.__table__.columns
    assert "lifecycle_state" in cols
    assert "archived_at" in cols
    assert "disposal_scheduled_at" in cols
    assert "disposal_approval_id" in cols
    assert cols["lifecycle_state"].default.arg == "active"


def test_approval_type_has_project_disposal():
    assert ApprovalType.PROJECT_DISPOSAL.value == "project_disposal"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_lifecycle_model.py -v`
Expected: FAIL (no `lifecycle_state`; no `PROJECT_DISPOSAL`).

- [ ] **Step 3: Add the enum value**

In `llc/models/enums.py`, `ApprovalType` (currently `HIRE`/`STRATEGY`/`BUDGET_OVERRIDE`/`SPRINT_CLOSE`), append:

```python
    PROJECT_DISPOSAL = "project_disposal"
```

- [ ] **Step 4: Add the columns**

In `llc/models/sprint.py`, `LLCProject`, immediately after the `code_source_id` column (line 137), add:

```python
    # Archive→dispose lifecycle, orthogonal to work-status `status` (#11129 P2).
    lifecycle_state: Mapped[str] = mapped_column(
        sa.Enum(
            "active",
            "archived",
            "pending_disposal",
            "disposed",
            name="projectlifecyclestate",
            create_type=True,
        ),
        nullable=False,
        server_default="active",
        default="active",
        index=True,
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disposal_scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    disposal_approval_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
```

- [ ] **Step 5: Write the migration**

```python
# autobot-backend/migrations/versions/20260708_067_llc_project_lifecycle.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add project archive→dispose lifecycle columns + PROJECT_DISPOSAL approval type (#11129 P2)."""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260708_067"
down_revision: Union[str, None] = "20260707_066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LIFECYCLE = sa.Enum(
    "active", "archived", "pending_disposal", "disposed", name="projectlifecyclestate"
)


def upgrade() -> None:
    bind = op.get_bind()
    _LIFECYCLE.create(bind, checkfirst=True)
    op.add_column(
        "llc_projects",
        sa.Column("lifecycle_state", _LIFECYCLE, nullable=False, server_default="active"),
    )
    op.create_index("ix_llc_projects_lifecycle_state", "llc_projects", ["lifecycle_state"])
    op.add_column("llc_projects", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "llc_projects", sa.Column("disposal_scheduled_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "llc_projects",
        sa.Column("disposal_approval_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE approvaltype ADD VALUE IF NOT EXISTS 'project_disposal'")


def downgrade() -> None:
    op.drop_index("ix_llc_projects_lifecycle_state", table_name="llc_projects")
    op.drop_column("llc_projects", "disposal_approval_id")
    op.drop_column("llc_projects", "disposal_scheduled_at")
    op.drop_column("llc_projects", "archived_at")
    op.drop_column("llc_projects", "lifecycle_state")
    _LIFECYCLE.drop(op.get_bind(), checkfirst=True)
    # Note: Postgres cannot drop an enum value; 'project_disposal' remains on approvaltype (harmless).
```

- [ ] **Step 6: Run the model test to verify it passes**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_lifecycle_model.py -v`
Expected: PASS.

- [ ] **Step 7: Verify migration chains cleanly (offline)**

Run: `cd autobot-backend && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; s=ScriptDirectory.from_config(Config('alembic.ini')); print(s.get_revision('head').revision)"`
Expected: prints `20260708_067` (single head, no branch).

- [ ] **Step 8: Commit**

```bash
git add autobot-backend/llc/models/sprint.py autobot-backend/llc/models/enums.py \
        autobot-backend/migrations/versions/20260708_067_llc_project_lifecycle.py \
        autobot-backend/llc/tests/test_project_lifecycle_model.py
git commit -m "feat(companyos): project lifecycle_state columns + PROJECT_DISPOSAL approval type (#11129)"
```

---

## Task 2: Extract `delete_source_and_cleanup` service

**Files:**
- Modify: `autobot-backend/api/codebase_analytics/source_service.py` (add function)
- Modify: `autobot-backend/api/codebase_analytics/endpoints/sources.py` (`delete_code_source` handler → call service)
- Test: `autobot-backend/api/codebase_analytics/source_delete_service_test.py`

**Interfaces:**
- Produces: `async def delete_source_and_cleanup(source_id: str) -> bool` — removes clone dir (only under `CODE_SOURCES_BASE`), purges ChromaDB docs for the source, deletes the Redis record; returns the Redis-delete bool. Returns `False` if the source is missing (idempotent).
- Consumes: `get_source`, `delete_source` (source_storage), `CODE_SOURCES_BASE` (source_paths), ChromaDB `_delete_source_documents`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/api/codebase_analytics/source_delete_service_test.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""delete_source_and_cleanup removes clone dir + index + record (#11129 P2)."""
import ast
from pathlib import Path

_SVC = Path(__file__).parent / "source_service.py"
_SOURCES = Path(__file__).parent / "endpoints" / "sources.py"


def test_service_exposes_delete_and_cleanup():
    tree = ast.parse(_SVC.read_text(encoding="utf-8"))
    names = {n.name for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef)}
    assert "delete_source_and_cleanup" in names


def test_delete_handler_delegates_to_service():
    src = _SOURCES.read_text(encoding="utf-8")
    assert "delete_source_and_cleanup" in src, "DELETE handler must call the extracted service"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest api/codebase_analytics/source_delete_service_test.py -v`
Expected: FAIL.

- [ ] **Step 3: Add the service function**

In `api/codebase_analytics/source_service.py`, add (mirror the current `endpoints/sources.py::delete_code_source` body — clone removal guarded by `CODE_SOURCES_BASE`, ChromaDB purge, Redis delete):

```python
async def delete_source_and_cleanup(source_id: str) -> bool:
    """Delete a CodeSource: its clone dir (only under CODE_SOURCES_BASE), its
    ChromaDB documents, and its Redis record. Idempotent; returns Redis-delete result."""
    import shutil  # noqa: PLC0415
    from pathlib import Path  # noqa: PLC0415

    from .source_paths import CODE_SOURCES_BASE  # noqa: PLC0415
    from .source_storage import delete_source, get_source  # noqa: PLC0415

    source = await get_source(source_id)
    if source is None:
        return False
    if source.clone_path and Path(source.clone_path).exists():
        clone = Path(source.clone_path).resolve()
        if clone.is_relative_to(CODE_SOURCES_BASE):
            shutil.rmtree(source.clone_path, ignore_errors=True)
    await _purge_source_index(source_id)
    ok = await delete_source(source_id)
    logger.info("Deleted code source %s (clone+index+record)", source_id)
    return ok


async def _purge_source_index(source_id: str) -> None:
    """Best-effort ChromaDB document removal for a source; never raises."""
    try:
        from .chromadb_storage import get_code_collection, _delete_source_documents  # noqa: PLC0415

        collection = await get_code_collection()
        if collection is not None:
            await _delete_source_documents(collection, task_id="dispose", source_id=source_id)
    except Exception as exc:  # noqa: BLE001 — index cleanup is best-effort
        logger.warning("ChromaDB purge for source %s failed: %s", source_id, exc)
```

> Implementer note: verify the exact accessor for the code collection in `chromadb_storage.py` (e.g. `get_code_collection`); if the name differs, use the real one and keep the try/except best-effort. Ensure `logger` exists in `source_service.py` (add `logger = logging.getLogger(__name__)` if missing).

- [ ] **Step 4: Repoint the HTTP handler**

In `endpoints/sources.py`, replace the body of `delete_code_source` so it delegates:

```python
@router.delete("/sources/{source_id}")
@with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="delete_source", error_code_prefix="CODEBASE")
async def delete_code_source(source_id: str):
    """Delete a code source and remove its clone directory + index if present."""
    from ..source_service import delete_source_and_cleanup  # noqa: PLC0415

    source = await get_source(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")
    ok = await delete_source_and_cleanup(source_id)
    return JSONResponse({"success": ok, "source_id": source_id})
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd autobot-backend && python -m pytest api/codebase_analytics/source_delete_service_test.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/api/codebase_analytics/source_service.py \
        autobot-backend/api/codebase_analytics/endpoints/sources.py \
        autobot-backend/api/codebase_analytics/source_delete_service_test.py
git commit -m "refactor(analytics): extract delete_source_and_cleanup service for reuse (#11129)"
```

---

## Task 3: Project disposal service

**Files:**
- Create: `autobot-backend/llc/services/project_disposal.py`
- Test: `autobot-backend/llc/tests/test_project_disposal_service.py`

**Interfaces:**
- Consumes: `LLCProject`, `LLCSprint`, `LLCWorkItem`; `delete_source_and_cleanup` (Task 2); `get_source`.
- Produces: `async def dispose(project: LLCProject, session: AsyncSession) -> None` — deletes work-items (by `project_id`) → sprints (by `project_id`) → project; then, if `project.code_source_id` set and the source is **not** `shared_with` others, calls `delete_source_and_cleanup`; else leaves the source (unlink). Sets `lifecycle_state='disposed'` is N/A (row deleted). Idempotent (missing project/source is a no-op). Never touches GitHub.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/llc/tests/test_project_disposal_service.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Disposal cascade: work-items→sprints→project→linked non-shared source (#11129 P2)."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.services.project_disposal import dispose


def _project(code_source_id=None):
    return SimpleNamespace(id=uuid.uuid4(), company_id=uuid.uuid4(), code_source_id=code_source_id)


@pytest.mark.asyncio
async def test_dispose_deletes_children_then_project_and_source():
    project = _project(code_source_id="src-1")
    session = AsyncMock()
    session.execute = AsyncMock()
    shared_source = SimpleNamespace(id="src-1", shared_with=[])
    with patch("llc.services.project_disposal.get_source", AsyncMock(return_value=shared_source)), patch(
        "llc.services.project_disposal.delete_source_and_cleanup", AsyncMock(return_value=True)
    ) as del_src:
        await dispose(project, session)
    del_src.assert_awaited_once_with("src-1")
    # work-items + sprints deleted via bulk delete statements, then project.
    assert session.execute.await_count >= 2


@pytest.mark.asyncio
async def test_dispose_keeps_shared_source():
    project = _project(code_source_id="src-2")
    session = AsyncMock()
    session.execute = AsyncMock()
    shared = SimpleNamespace(id="src-2", shared_with=["someone-else"])
    with patch("llc.services.project_disposal.get_source", AsyncMock(return_value=shared)), patch(
        "llc.services.project_disposal.delete_source_and_cleanup", AsyncMock()
    ) as del_src:
        await dispose(project, session)
    del_src.assert_not_awaited()


@pytest.mark.asyncio
async def test_dispose_no_source_is_noop_on_source():
    project = _project(code_source_id=None)
    session = AsyncMock()
    session.execute = AsyncMock()
    with patch("llc.services.project_disposal.delete_source_and_cleanup", AsyncMock()) as del_src:
        await dispose(project, session)
    del_src.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_disposal_service.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement the service**

```python
# autobot-backend/llc/services/project_disposal.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Project disposal: cascade-delete AutoBot data + linked non-shared CodeSource (#11129 P2).

NEVER deletes the GitHub repo. A source shared with other users is unlinked, not deleted.
"""
import logging

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.sprint import LLCProject, LLCSprint
from llc.models.work_item import LLCWorkItem

logger = logging.getLogger(__name__)


async def dispose(project: LLCProject, session: AsyncSession) -> None:
    """Delete the project's work-items, sprints, the project row, and — when the
    linked CodeSource is not shared with other users — that source's clone + index.
    Idempotent; caller owns the surrounding transaction/commit."""
    project_id = project.id
    code_source_id = project.code_source_id

    await session.execute(delete(LLCWorkItem).where(LLCWorkItem.project_id == project_id))
    await session.execute(delete(LLCSprint).where(LLCSprint.project_id == project_id))
    await session.execute(delete(LLCProject).where(LLCProject.id == project_id))

    if code_source_id:
        await _dispose_source(code_source_id)
    logger.info("Disposed project %s (source=%s)", project_id, code_source_id)


async def _dispose_source(code_source_id: str) -> None:
    """Delete the linked source's clone+index only when it is not shared with others."""
    from api.codebase_analytics.source_service import delete_source_and_cleanup  # noqa: PLC0415
    from api.codebase_analytics.source_storage import get_source  # noqa: PLC0415

    source = await get_source(code_source_id)
    if source is None:
        return
    if getattr(source, "shared_with", None):
        logger.info("Source %s is shared; unlinking only (not deleting)", code_source_id)
        return
    await delete_source_and_cleanup(code_source_id)
```

> The test patches `get_source` and `delete_source_and_cleanup` as attributes of `project_disposal`. Because they are lazy-imported inside `_dispose_source`, add module-level re-exports so the patch targets resolve: at import time the names must exist on the module. Implementer: add near the top, after the logger, guarded re-exports OR change the test patch target — prefer making the lazy imports patchable by importing them at module top only if that does not reintroduce the heavy-import/circular problem. If top-level import is unsafe, instead patch `api.codebase_analytics.source_service.delete_source_and_cleanup` and `api.codebase_analytics.source_storage.get_source` in the test. **Adjust the test's patch targets to whichever import strategy you choose so the three tests pass.**

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_disposal_service.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/llc/services/project_disposal.py \
        autobot-backend/llc/tests/test_project_disposal_service.py
git commit -m "feat(companyos): project disposal cascade service (#11129)"
```

---

## Task 4: Disposal-policy reader (SLM settings)

**Files:**
- Create: `autobot-backend/llc/services/disposal_policy.py`
- Test: `autobot-backend/llc/tests/test_disposal_policy.py`

**Interfaces:**
- Produces: `@dataclass(frozen=True) class DisposalPolicy: retention_days: int = 0; require_approval: bool = False`; `async def get_disposal_policy() -> DisposalPolicy` — reads SLM setting key `llc.project_disposal_policy` (JSON) via the `SLMClient`; returns defaults on missing/unreadable/malformed.
- Constant: `POLICY_SETTING_KEY = "llc.project_disposal_policy"`.

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/llc/tests/test_disposal_policy.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""SLM-configurable disposal policy read + safe defaults (#11129 P2)."""
from unittest.mock import AsyncMock, patch

import pytest

from llc.services.disposal_policy import DisposalPolicy, get_disposal_policy


@pytest.mark.asyncio
async def test_defaults_when_no_slm_client():
    with patch("llc.services.disposal_policy.get_slm_client", return_value=None):
        policy = await get_disposal_policy()
    assert policy == DisposalPolicy(retention_days=0, require_approval=False)


@pytest.mark.asyncio
async def test_parses_policy_from_slm():
    with patch(
        "llc.services.disposal_policy._fetch_policy_json",
        AsyncMock(return_value={"retention_days": 30, "require_approval": True}),
    ):
        policy = await get_disposal_policy()
    assert policy.retention_days == 30
    assert policy.require_approval is True


@pytest.mark.asyncio
async def test_defaults_on_malformed():
    with patch("llc.services.disposal_policy._fetch_policy_json", AsyncMock(return_value={"bad": "x"})):
        policy = await get_disposal_policy()
    assert policy == DisposalPolicy(retention_days=0, require_approval=False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest llc/tests/test_disposal_policy.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the reader**

```python
# autobot-backend/llc/services/disposal_policy.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Read the SLM-configured project disposal policy with safe defaults (#11129 P2)."""
import json
import logging
from dataclasses import dataclass
from typing import Optional

from services.slm_client import get_slm_client

logger = logging.getLogger(__name__)

POLICY_SETTING_KEY = "llc.project_disposal_policy"


@dataclass(frozen=True)
class DisposalPolicy:
    retention_days: int = 0
    require_approval: bool = False


async def _fetch_policy_json() -> Optional[dict]:
    """GET the policy setting from the SLM settings API; None on any failure."""
    client = get_slm_client()
    if client is None:
        return None
    try:
        session = await client._get_session()
        url = f"{client.slm_url}/api/settings/{POLICY_SETTING_KEY}"
        async with session.get(url) as response:
            if response.status != 200:
                return None
            setting = await response.json()
            raw = setting.get("value")
            return json.loads(raw) if raw else None
    except Exception as exc:  # noqa: BLE001 — policy read is best-effort
        logger.warning("Disposal policy read failed: %s", exc)
        return None


async def get_disposal_policy() -> DisposalPolicy:
    """Return the configured policy, or safe defaults (immediate/no-approval)."""
    data = await _fetch_policy_json()
    if not isinstance(data, dict):
        return DisposalPolicy()
    try:
        return DisposalPolicy(
            retention_days=max(0, int(data["retention_days"])),
            require_approval=bool(data["require_approval"]),
        )
    except (KeyError, TypeError, ValueError):
        return DisposalPolicy()
```

> Implementer: confirm `services.slm_client.get_slm_client` and the `client.slm_url` / `client._get_session()` accessors exist (they do per exploration). If the SLM client exposes a public GET helper, prefer it over `_get_session()`.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd autobot-backend && python -m pytest llc/tests/test_disposal_policy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add autobot-backend/llc/services/disposal_policy.py \
        autobot-backend/llc/tests/test_disposal_policy.py
git commit -m "feat(companyos): SLM disposal-policy reader with safe defaults (#11129)"
```

---

## Task 5: Lifecycle endpoints (archive / restore / dispose / DELETE reroute)

**Files:**
- Modify: `autobot-backend/llc/api/sprints.py` (`ProjectResponse`; new endpoints; `delete_project`)
- Test: `autobot-backend/llc/tests/test_project_lifecycle_api.py`

**Interfaces:**
- Consumes: `dispose` (Task 3), `get_disposal_policy`/`DisposalPolicy` (Task 4), `ApprovalService.request_approval` + `ApprovalType.PROJECT_DISPOSAL` (Task 1), `get_session`/`get_current_user`/`require_org_context`.
- Produces routes (served under `/api/llc`): `POST /projects/{id}/archive`, `POST /projects/{id}/restore`, `POST /projects/{id}/dispose`, and a rerouted `DELETE /projects/{id}`. `ProjectResponse` gains `lifecycle_state`, `archived_at`, `disposal_scheduled_at`, `disposal_approval_id`.

- [ ] **Step 1: Add lifecycle fields to `ProjectResponse`**

In `sprints.py`, `ProjectResponse` (after `code_source`), add:

```python
    lifecycle_state: str = "active"
    archived_at: Optional[datetime] = None
    disposal_scheduled_at: Optional[datetime] = None
    disposal_approval_id: Optional[uuid.UUID] = None
```

- [ ] **Step 2: Write the failing tests**

```python
# autobot-backend/llc/tests/test_project_lifecycle_api.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Archive→dispose lifecycle endpoints (#11129 P2)."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from user_management.services import TenantContext

_USER = uuid.UUID("77777777-7777-7777-7777-777777777777")


def _mk_client(project):
    from api.user_management.dependencies import get_current_user, require_org_context  # noqa: PLC0415
    from llc.api.sprints import router  # noqa: PLC0415
    from llc.deps import get_session  # noqa: PLC0415

    app = FastAPI()
    app.include_router(router)
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = project
    session.execute = AsyncMock(return_value=result)
    session.commit = AsyncMock()

    async def _sess():
        yield session

    app.dependency_overrides[get_session] = _sess
    app.dependency_overrides[get_current_user] = lambda: {"id": str(_USER)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=project.company_id, user_id=_USER, is_platform_admin=False
    )
    return TestClient(app), session


def _project(lifecycle="active"):
    org = uuid.uuid4()
    p = MagicMock()
    p.id = uuid.uuid4()
    p.company_id = org
    p.lifecycle_state = lifecycle
    p.code_source_id = None
    return p


def test_archive_sets_state():
    p = _project("active")
    client, _ = _mk_client(p)
    resp = client.post(f"/projects/{p.id}/archive")
    assert resp.status_code == 200
    assert p.lifecycle_state == "archived"


def test_dispose_requires_archived():
    p = _project("active")
    client, _ = _mk_client(p)
    resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 409


def test_delete_requires_archived():
    p = _project("active")
    client, _ = _mk_client(p)
    resp = client.request("DELETE", f"/projects/{p.id}")
    assert resp.status_code == 409


def test_dispose_immediate_when_policy_default():
    p = _project("archived")
    client, _ = _mk_client(p)
    with patch("llc.api.sprints.get_disposal_policy", AsyncMock(return_value=_policy(0, False))), patch(
        "llc.api.sprints.dispose", AsyncMock()
    ) as disp:
        resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 200
    disp.assert_awaited_once()
    assert resp.json()["result"] == "disposed"


def test_dispose_schedules_when_retention():
    p = _project("archived")
    client, _ = _mk_client(p)
    with patch("llc.api.sprints.get_disposal_policy", AsyncMock(return_value=_policy(7, False))), patch(
        "llc.api.sprints.dispose", AsyncMock()
    ) as disp:
        resp = client.post(f"/projects/{p.id}/dispose")
    assert resp.status_code == 200
    disp.assert_not_awaited()
    assert resp.json()["result"] == "scheduled"
    assert p.lifecycle_state == "pending_disposal"


def _policy(days, approval):
    from llc.services.disposal_policy import DisposalPolicy  # noqa: PLC0415

    return DisposalPolicy(retention_days=days, require_approval=approval)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_lifecycle_api.py -v`
Expected: FAIL (routes 404 / missing patch targets).

- [ ] **Step 4: Implement the endpoints**

Add to `sprints.py` (near the other `/projects` handlers). Import at module top (or lazy where heavy): `from datetime import datetime, timezone`, `from llc.services.project_disposal import dispose`, `from llc.services.disposal_policy import get_disposal_policy`, `from llc.services.approval import ApprovalService`, `from llc.models.enums import ApprovalType`.

```python
async def _load_owned_project(project_id, session, ctx):
    result = await session.execute(select(LLCProject).where(LLCProject.id == project_id))
    project = result.scalar_one_or_none()
    if project is None or str(project.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/projects/{project_id}/archive", response_model=ProjectResponse)
async def archive_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProjectResponse:
    project = await _load_owned_project(project_id, session, ctx)
    project.lifecycle_state = "archived"
    project.archived_at = datetime.now(timezone.utc)
    await session.commit()
    return ProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/restore", response_model=ProjectResponse)
async def restore_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProjectResponse:
    project = await _load_owned_project(project_id, session, ctx)
    if project.lifecycle_state not in ("archived", "pending_disposal"):
        raise HTTPException(status_code=409, detail="Project is not archived")
    project.lifecycle_state = "active"
    project.archived_at = None
    project.disposal_scheduled_at = None
    project.disposal_approval_id = None
    await session.commit()
    return ProjectResponse.model_validate(project)


@router.post("/projects/{project_id}/dispose")
async def dispose_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> dict:
    project = await _load_owned_project(project_id, session, ctx)
    if project.lifecycle_state != "archived":
        raise HTTPException(status_code=409, detail="Project must be archived before disposal")
    return await _apply_disposal(project, session, ctx, current_user)


async def _apply_disposal(project, session, ctx, current_user) -> dict:
    """Consult SLM policy and dispose now / schedule / gate on approval."""
    policy = await get_disposal_policy()
    if policy.require_approval:
        approval = await ApprovalService().request_approval(
            session,
            company_id=ctx.org_id,
            gate_type=ApprovalType.PROJECT_DISPOSAL,
            payload={"project_id": str(project.id)},
            requested_by=uuid.UUID(str(current_user["id"])),
        )
        project.lifecycle_state = "pending_disposal"
        project.disposal_approval_id = approval.id
        if policy.retention_days > 0:
            project.disposal_scheduled_at = datetime.now(timezone.utc) + timedelta(days=policy.retention_days)
        await session.commit()
        return {"result": "pending_approval", "approval_id": str(approval.id)}
    if policy.retention_days > 0:
        project.lifecycle_state = "pending_disposal"
        project.disposal_scheduled_at = datetime.now(timezone.utc) + timedelta(days=policy.retention_days)
        await session.commit()
        return {"result": "scheduled", "disposal_scheduled_at": project.disposal_scheduled_at.isoformat()}
    await dispose(project, session)
    await session.commit()
    return {"result": "disposed"}
```

Add `from datetime import timedelta` to the imports. Then **replace** `delete_project` so it reroutes:

```python
@router.delete("/projects/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    project = await _load_owned_project(project_id, session, ctx)
    if project.lifecycle_state != "archived":
        raise HTTPException(status_code=409, detail="Archive the project before deleting")
    await _apply_disposal(project, session, ctx, current_user)
```

> Note: `DELETE` now returns 204 with no body on success; when policy schedules/gates, the row still exists (that is intended — delete "requests" disposal per the configured workflow). The 409-before-archived guard is the two-step gate.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_lifecycle_api.py -v`
Expected: PASS (6 tests). Then run the Phase-1 enrichment test to confirm no regression: `python -m pytest llc/tests/test_sprints_enrichment.py -v` (pin `lifecycle_state`/`archived_at`/`disposal_*` on the `_project()` mock if `model_validate` now reads them — set `m.lifecycle_state="active"`, the three others `= None`).

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/llc/api/sprints.py autobot-backend/llc/tests/test_project_lifecycle_api.py \
        autobot-backend/llc/tests/test_sprints_enrichment.py
git commit -m "feat(companyos): archive/restore/dispose endpoints + DELETE reroute (#11129)"
```

---

## Task 6: Celery-beat disposal sweep

**Files:**
- Create: `autobot-backend/llc/scheduler/project_disposal_sweep.py`
- Modify: `autobot-backend/celery_app.py` (beat schedule + import)
- Test: `autobot-backend/llc/tests/test_project_disposal_sweep.py`

**Interfaces:**
- Consumes: `dispose` (Task 3); `LLCProject`; `LLCApproval` + `ApprovalStatus` (to confirm granted approvals); `get_async_session_factory`.
- Produces: `@shared_task(name="llc.scheduler.project_disposal_sweep.run_disposal_sweep")` sync entry + `async def _async_sweep() -> int` (returns disposed count). Selects `lifecycle_state == "pending_disposal"` AND `disposal_scheduled_at <= now` AND (`disposal_approval_id IS NULL` OR its `LLCApproval.status == APPROVED`).

- [ ] **Step 1: Write the failing test**

```python
# autobot-backend/llc/tests/test_project_disposal_sweep.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Beat sweep disposes only due + approved pending_disposal projects (#11129 P2)."""
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llc.scheduler.project_disposal_sweep import _async_sweep


@pytest.mark.asyncio
async def test_sweep_disposes_due_projects():
    due = [SimpleNamespace(id=uuid.uuid4(), code_source_id=None, disposal_approval_id=None)]
    session = AsyncMock()
    scal = MagicMock()
    scal.scalars.return_value.all.return_value = due
    session.execute = AsyncMock(return_value=scal)
    session.commit = AsyncMock()

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return session

        async def __aexit__(self, *a):
            return False

    with patch("llc.scheduler.project_disposal_sweep.get_async_session_factory", return_value=_Factory()), patch(
        "llc.scheduler.project_disposal_sweep.dispose", AsyncMock()
    ) as disp, patch(
        "llc.scheduler.project_disposal_sweep._is_disposal_allowed", AsyncMock(return_value=True)
    ):
        count = await _async_sweep()
    assert count == 1
    disp.assert_awaited_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_disposal_sweep.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement the sweep**

```python
# autobot-backend/llc/scheduler/project_disposal_sweep.py
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Celery-beat sweep: dispose due + approved pending_disposal projects (#11129 P2)."""
import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task
from sqlalchemy import select

from llc.models.enums import ApprovalStatus
from llc.models.approval import LLCApproval
from llc.models.sprint import LLCProject
from llc.services.project_disposal import dispose
from user_management.database import get_async_session_factory

logger = logging.getLogger(__name__)


@shared_task(name="llc.scheduler.project_disposal_sweep.run_disposal_sweep", bind=True, max_retries=3)
def run_disposal_sweep(self: object) -> dict:
    """Sync Celery entry point — disposes projects whose retention has elapsed."""
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    disposed = loop.run_until_complete(_async_sweep())
    return {"disposed": disposed}


async def _async_sweep() -> int:
    factory = get_async_session_factory()
    disposed = 0
    async with factory() as session:
        result = await session.execute(
            select(LLCProject).where(
                LLCProject.lifecycle_state == "pending_disposal",
                LLCProject.disposal_scheduled_at <= datetime.now(timezone.utc),
            )
        )
        for project in result.scalars().all():
            if not await _is_disposal_allowed(project, session):
                continue
            await dispose(project, session)
            disposed += 1
        await session.commit()
    logger.info("Disposal sweep disposed %d project(s)", disposed)
    return disposed


async def _is_disposal_allowed(project: LLCProject, session) -> bool:
    """Approval-gated projects dispose only once their LLCApproval is APPROVED."""
    if project.disposal_approval_id is None:
        return True
    result = await session.execute(
        select(LLCApproval).where(LLCApproval.id == project.disposal_approval_id)
    )
    approval = result.scalar_one_or_none()
    return approval is not None and approval.status == ApprovalStatus.APPROVED.value
```

- [ ] **Step 4: Register in the beat schedule**

In `celery_app.py`, add to `celery_app.conf.beat_schedule` (near `llc-sprint-autoclose-daily`):

```python
    "llc-project-disposal-sweep": {
        "task": "llc.scheduler.project_disposal_sweep.run_disposal_sweep",
        "schedule": crontab(hour=1, minute=0),
    },
```

And ensure the task module is imported (add near the other explicit imports, e.g. after `import tasks.knowledge_retention`):

```python
import llc.scheduler.project_disposal_sweep  # noqa: F401 — register beat task
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd autobot-backend && python -m pytest llc/tests/test_project_disposal_sweep.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add autobot-backend/llc/scheduler/project_disposal_sweep.py autobot-backend/celery_app.py \
        autobot-backend/llc/tests/test_project_disposal_sweep.py
git commit -m "feat(companyos): celery-beat disposal sweep for due projects (#11129)"
```

---

## Task 7: SLM-frontend disposal-policy panel

**Files:**
- Create: `autobot-slm-frontend/src/views/settings/DisposalPolicySettings.vue`
- Modify: the SLM router + settings nav (find where `GeneralSettings.vue` is routed — likely `src/router/index.ts` and a settings nav list)
- Test: `autobot-slm-frontend/src/views/settings/DisposalPolicySettings.test.ts`

**Interfaces:**
- Reads/writes SLM setting key `llc.project_disposal_policy` as a JSON string via `GET/PUT/POST /api/settings/llc.project_disposal_policy` using `authStore.getApiUrl()` + `authStore.getAuthHeaders()` (mirror `GeneralSettings.vue`).

- [ ] **Step 1: Write the failing test**

```typescript
// autobot-slm-frontend/src/views/settings/DisposalPolicySettings.test.ts
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import DisposalPolicySettings from './DisposalPolicySettings.vue'

vi.mock('@/stores/auth', () => ({
  useAuthStore: () => ({
    getApiUrl: () => '',
    getAuthHeaders: () => ({}),
  }),
}))

describe('DisposalPolicySettings', () => {
  beforeEach(() => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ value: JSON.stringify({ retention_days: 14, require_approval: true }) }),
    })) as unknown as typeof fetch
  })

  it('loads the current policy on mount', async () => {
    const wrapper = mount(DisposalPolicySettings)
    await flushPromises()
    const number = wrapper.find('input[type="number"]').element as HTMLInputElement
    expect(number.value).toBe('14')
  })

  it('PUTs the policy as JSON on save', async () => {
    const wrapper = mount(DisposalPolicySettings)
    await flushPromises()
    await wrapper.find('button[data-test="save-policy"]').trigger('click')
    await flushPromises()
    const putCall = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.find((c) => c[1]?.method === 'PUT')
    expect(putCall).toBeTruthy()
    expect(putCall![0]).toContain('/api/settings/llc.project_disposal_policy')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd autobot-slm-frontend && npx vitest run src/views/settings/DisposalPolicySettings.test.ts`
Expected: FAIL (component missing).

- [ ] **Step 3: Implement the component** (mirror `GeneralSettings.vue` card + save pattern)

```vue
<!-- autobot-slm-frontend/src/views/settings/DisposalPolicySettings.vue -->
<!-- Copyright 2025-2026 mrveiss -->
<!-- SPDX-License-Identifier: Apache-2.0 -->
<template>
  <div class="bg-white rounded-lg shadow-xs border border-gray-200 p-6">
    <h2 class="text-lg font-semibold text-gray-900 mb-4">Project Disposal Policy</h2>
    <p class="text-sm text-gray-500 mb-4">
      Controls how Company OS projects are disposed after archiving. Default: immediate, no approval.
    </p>
    <div class="flex items-center gap-3 mb-4">
      <label class="w-56 text-sm text-gray-700">Retention period (days)</label>
      <input
        v-model.number="policy.retention_days"
        type="number"
        min="0"
        class="w-32 px-3 py-2 border border-gray-300 rounded-md"
      />
    </div>
    <div class="flex items-center gap-3 mb-6">
      <label class="w-56 text-sm text-gray-700">Require second-pair-of-eyes approval</label>
      <input v-model="policy.require_approval" type="checkbox" class="h-4 w-4" />
    </div>
    <button
      data-test="save-policy"
      :disabled="saving"
      class="px-4 py-2 bg-indigo-600 text-white rounded-md disabled:opacity-50"
      @click="save"
    >
      {{ saving ? 'Saving…' : 'Save policy' }}
    </button>
    <span v-if="saved" class="ml-3 text-sm text-green-600">Saved</span>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const KEY = 'llc.project_disposal_policy'
const authStore = useAuthStore()
const policy = reactive({ retention_days: 0, require_approval: false })
const saving = ref(false)
const saved = ref(false)

async function load(): Promise<void> {
  const res = await fetch(`${authStore.getApiUrl()}/api/settings/${KEY}`, {
    headers: authStore.getAuthHeaders(),
  })
  if (res.ok) {
    const setting = await res.json()
    const parsed = setting.value ? JSON.parse(setting.value) : {}
    policy.retention_days = Number(parsed.retention_days ?? 0)
    policy.require_approval = Boolean(parsed.require_approval ?? false)
  }
}

async function save(): Promise<void> {
  saving.value = true
  saved.value = false
  const body = JSON.stringify({
    value: JSON.stringify({ retention_days: policy.retention_days, require_approval: policy.require_approval }),
    description: 'Company OS project disposal policy',
  })
  const url = `${authStore.getApiUrl()}/api/settings/${KEY}`
  const headers = { ...authStore.getAuthHeaders(), 'Content-Type': 'application/json' }
  let res = await fetch(url, { method: 'PUT', headers, body })
  if (res.status === 404) res = await fetch(url, { method: 'POST', headers, body })
  saving.value = false
  saved.value = res.ok
}

onMounted(load)
</script>
```

- [ ] **Step 4: Route + nav**

Add a route for `DisposalPolicySettings.vue` alongside the existing settings routes, and a settings-nav entry labelled "Disposal Policy" (match how `GeneralSettings` is registered). Implementer: read the SLM router + settings nav to place it consistently.

- [ ] **Step 5: Run the test + build**

Run: `cd autobot-slm-frontend && npx vitest run src/views/settings/DisposalPolicySettings.test.ts`
Expected: PASS (2 tests).
Run: `cd autobot-slm-frontend && npm run build:slm`
Expected: build succeeds (VITE_API_URL is set by the script).

- [ ] **Step 6: Commit**

```bash
git add autobot-slm-frontend/src/views/settings/DisposalPolicySettings.vue \
        autobot-slm-frontend/src/views/settings/DisposalPolicySettings.test.ts \
        autobot-slm-frontend/src/router
git commit -m "feat(slm): project disposal policy settings panel (#11129)"
```

---

## Task 8: Company OS frontend — archive / delete / restore

**Files:**
- Modify: `autobot-frontend/src/views/llc/ProjectBrowserView.vue`
- Modify: all 11 locale files under `autobot-frontend/src/locales/` (add i18n keys)
- Test: `autobot-frontend/src/views/llc/ProjectBrowserView.lifecycle.test.ts`

**Interfaces:**
- Calls `POST /api/llc/projects/{id}/archive`, `POST …/restore`, `POST …/dispose` via the app's `ApiClient` (parsed-JSON return, no envelope). Shows a lifecycle badge from `project.lifecycle_state`; "Archive" on active projects, "Delete" (→ confirm → dispose) + "Restore" on archived/pending. All button labels + confirm text via `t('...')` i18n keys.

- [ ] **Step 1: Add i18n keys (English first)**

In `autobot-frontend/src/locales/en.json` (or the LLC namespace file used by this view), add keys such as:

```json
"llc": {
  "project": {
    "archive": "Archive",
    "restore": "Restore",
    "delete": "Delete",
    "confirmDelete": "Delete this archived project and its sprints? This cannot be undone.",
    "lifecycle": {
      "active": "Active",
      "archived": "Archived",
      "pending_disposal": "Pending disposal",
      "disposed": "Disposed"
    }
  }
}
```

Mirror the same keys into the other 10 locale files (translated where a translation exists; English fallback otherwise) — no hardcoded strings in the template.

- [ ] **Step 2: Write the failing test**

```typescript
// autobot-frontend/src/views/llc/ProjectBrowserView.lifecycle.test.ts
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from 'vitest'
// Mount ProjectBrowserView with a stubbed ApiClient + i18n; assert an archived
// project renders a Restore action and calls POST …/dispose on confirmed delete,
// and an active project renders an Archive action calling POST …/archive.
// (Follow the existing ProjectBrowserView.repo.test.ts harness from Phase 1.)
```

Implementer: model this on the Phase-1 `ProjectBrowserView.repo.test.ts` (same mount/stub harness). Assert: (a) active project shows Archive → click calls `ApiClient` POST `.../archive`; (b) archived project shows Delete + Restore → confirmed Delete calls POST `.../dispose`, Restore calls POST `.../restore`.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd autobot-frontend && npx vitest run src/views/llc/ProjectBrowserView.lifecycle.test.ts`
Expected: FAIL.

- [ ] **Step 4: Implement the UI**

Add to `ProjectBrowserView.vue`: a lifecycle badge (`t('llc.project.lifecycle.' + project.lifecycle_state)`); conditional actions — Archive when `lifecycle_state === 'active'`; Delete (window-confirm with `t('llc.project.confirmDelete')`, then `POST …/dispose`) and Restore (`POST …/restore`) when `archived`/`pending_disposal`; refresh the list after each. Use the existing `ApiClient`/composable already used for repo attach in Phase 1.

- [ ] **Step 5: Run test + typecheck + lint**

Run: `cd autobot-frontend && npx vitest run src/views/llc/ProjectBrowserView.lifecycle.test.ts`
Expected: PASS.
Run: `cd autobot-frontend && npx vue-tsc --noEmit -p tsconfig.app.json && npx eslint src/views/llc/ProjectBrowserView.vue --max-warnings 0`
Expected: 0 errors, 0 warnings.

- [ ] **Step 6: Commit**

```bash
git add autobot-frontend/src/views/llc/ProjectBrowserView.vue \
        autobot-frontend/src/views/llc/ProjectBrowserView.lifecycle.test.ts \
        autobot-frontend/src/locales
git commit -m "feat(companyos): project archive/delete/restore UI + i18n (#11129)"
```

---

## Self-Review Checklist (run before final review)

1. **Spec coverage:** lifecycle states ✔ (Task 1/5), archive→dispose two-step ✔ (Task 5 DELETE 409-gate), SLM policy retention+approval ✔ (Task 4/5/6/7), disposal deletes linked non-shared source, never GitHub ✔ (Task 2/3), analytics reuse ✔ (Phase 1). 
2. **Type consistency:** `lifecycle_state` string values identical across model enum, endpoints, sweep, frontend badge (`active|archived|pending_disposal|disposed`); `DisposalPolicy` fields identical across Task 4/5/6/7.
3. **No placeholders:** every code step has real code; the two frontend test bodies reference the concrete Phase-1 harness to copy.
4. **Migration head:** `20260708_067` chains onto `20260707_066`; single head.
5. **Global constraints:** no commit trailers, copyright headers, ≤30-line funcs, i18n all 11 locales, no `/api` double-prefix.
