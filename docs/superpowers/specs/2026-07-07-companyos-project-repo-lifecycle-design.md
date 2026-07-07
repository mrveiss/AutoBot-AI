# Company OS project ↔ repo linkage, workspace, and archive→dispose lifecycle — design

**Date:** 2026-07-07 (revised: reuse codebase-analytics `CodeSource`)
**Umbrella:** #11129
**Status:** design — decisions captured; ready for writing-plans

## Goal

Company OS (LLC) projects can attach a GitHub repo (surfaced in the UI, with its managed workspace path,
and analyzable in codebase analytics), and follow an **archive → dispose** lifecycle instead of a hard
delete, governed by an **SLM-configurable disposal policy** (retention period + optional
second-pair-of-eyes approval; default immediate).

## Key reuse decision

The codebase-analytics **`CodeSource`** system (`autobot-backend/api/codebase_analytics/`) already does
everything the repo/workspace/analytics part needs, so we **link a project to a `CodeSource`** rather than
build a parallel clone/workspace service:

- `CodeSource` (`source_models.py`): `id`, `name`, `source_type` (github/local), `repo` ("owner/repo"),
  `branch`, `credential_id` (→ secrets store token), `clone_path`
  (`/opt/autobot/data/code-sources/<id>/`), `status`, `error_message`, `owner_id`, `access`, `shared_with`.
- Sources API (`endpoints/sources.py`): `POST /sources` (create + background clone/index via `_do_sync`
  + `_trigger_indexing`), `GET /sources`, `GET/PATCH/DELETE /sources/{id}`, `POST /sources/{id}/sync`.
- The source **is** the analytics unit (cloned to `clone_path`, indexed into ChromaDB).

So: **attach repo = create/link a github `CodeSource`; workspace = its `clone_path`; analytics already
analyzes it; disposal deletes the linked `CodeSource`.** The GitHub repo itself is never deleted.

## Decisions (brainstorm 2026-07-07)

- **Repo/workspace/analytics** = reuse `CodeSource`. Project gains `code_source_id` (FK-ish string,
  nullable, references `CodeSource.id`).
- **Attach** = attach an EXISTING repo by `owner/repo` + a `credential_id` (GitHub token from the secrets
  store), one per project → create a github `CodeSource` (or link an existing one) → set
  `project.code_source_id` → trigger sync (clone + index). Re-attach replaces the link.
- **Workspace path** shown in the UI = the linked source's `clone_path`.
- **Codebase analytics** already indexes the source; the analytics view groups/labels sources by their
  owning project (via `code_source_id`), and the project view links to its source's analytics.
- **Lifecycle**: `active → archived → pending_disposal → disposed`; `DELETE /projects/{id}` routes through
  this flow.
- **Disposal scope**: delete AutoBot data (project + its sprints/work-items) + the linked `CodeSource`
  (which removes its `clone_path` clone + ChromaDB index) — **only if that source isn't `shared_with`
  other users** (else just unlink). **NEVER** delete the GitHub repo.
- **Disposal policy** (SLM-configurable): `{ retention_days:int = 0, require_approval:bool = false }`;
  default immediate/no-approval/no-retention. Approval via existing `LLCApproval`; retention via a
  Celery-beat sweep.

## Scope / phases

- **Phase 1** — project ↔ `CodeSource` linkage (attach/detach) + surface repo/workspace + analytics
  grouping by project.
- **Phase 2** — archive→dispose lifecycle + SLM-configurable disposal (retention + approval); disposal
  deletes the linked `CodeSource`.
- **Phase 3 (own spec, deferred, YAGNI here)** — analytics findings → project work items agents pick up.

Out of scope: creating new GitHub repos; multiple repos per project; deleting the GitHub repo on disposal;
per-project retention overrides (policy is global from SLM); building any new clone/index engine.

---

## Phase 1 — Project ↔ CodeSource linkage

### Model (`llc/models/sprint.py` — `LLCProject`)
Add one nullable column (+ Alembic migration): `code_source_id: str | None` (references
`CodeSource.id`; the source holds repo/branch/clone_path/status). Index it.

### API (`llc/api/sprints.py`, extends the projects router)
Reuse the sources service — do NOT reimplement clone/token/index.
- `POST /api/llc/projects/{id}/repo` `{ repo: "owner/repo", credential_id: str, branch?: str = "main" }`
  → call the existing source-create path (`create_code_source`-equivalent service function) to make a
  github `CodeSource` named after the project, set `project.code_source_id`, and trigger sync. Returns the
  project + a `CodeSourceSummary` (`{ id, repo, branch, clone_path, status, error_message }`). If the
  project already has a `code_source_id`, unlink first (per re-attach).
- `DELETE /api/llc/projects/{id}/repo` → clear `code_source_id` (unlink only; the source is left intact
  for reuse/sharing — it is only deleted on project disposal, see Phase 2).
- `GET /api/llc/projects/with-repos` → `[{ project_id, name, company_id, code_source_id, repo, clone_path,
  status }]` for projects with a `code_source_id` (joins the source) — feeds the analytics grouping.
- `ProjectResponse` gains `code_source_id` + an embedded `CodeSourceSummary | None` (resolved from the
  sources store).

The source-create/get/delete must be reachable as **service functions** (not only HTTP handlers). If
`endpoints/sources.py` only exposes handlers, extract the create/get/delete logic into
`api/codebase_analytics/source_service.py` (thin, behavior-preserving) and have both the HTTP handlers and
the LLC layer call it — a targeted improvement that keeps this DRY.

### Frontend (`autobot-frontend`)
- `ProjectBrowserView.vue` + project detail: show the linked repo (`owner/repo`, GitHub link), the
  `clone_path` (copyable), sync status; an "Attach repo" action (input `owner/repo` + pick a stored
  GitHub credential → `POST …/repo`), a "Sync" action (calls the source sync), and "Detach".
- Codebase Analytics view: label/group its source list by owning project (from
  `GET /api/llc/projects/with-repos` or the source's new project link), so project repos are visible there.

---

## Phase 2 — Lifecycle + configurable disposal

### Model additions (`LLCProject`)
Extend `status` enum with `archived`; add `archived_at`, `disposal_scheduled_at`,
`disposal_approval_id` (nullable, references `llc_approvals.id`). Migration adds the enum value + columns.

### Endpoints (`llc/api/sprints.py`)
- `POST /api/llc/projects/{id}/archive` → `archived` + `archived_at=now` (reversible).
- `POST /api/llc/projects/{id}/restore` → archived/pending → `active` (clears disposal fields).
- `POST /api/llc/projects/{id}/dispose` → **only when `archived`** (else `409`); reads the SLM disposal
  policy and:
  - `require_approval` → create an `LLCApproval` (type `project_disposal`), `status=pending_disposal`,
    set `disposal_approval_id`; proceeds only after approval.
  - `retention_days > 0` → `status=pending_disposal`, `disposal_scheduled_at = now + retention` (sweep
    disposes when due; restorable until then).
  - else → dispose now.
- `DELETE /api/llc/projects/{id}` → no longer hard-deletes; `409` unless `archived`; when archived,
  delegates to the dispose flow (real two-step archive→delete).

### Disposal execution (`llc/services/project_disposal.py`, new)
- `async dispose(project, session)` — in a transaction: delete the project + its sprints + work-items;
  then if `project.code_source_id` set and that source is **not** `shared_with` others, call the source
  delete service (removes `clone_path` clone + ChromaDB index); else just unlink. **Never** call the
  GitHub API. Idempotent + logged.
- **Celery-beat sweep** `dispose_due_projects` (register in `celery_app.py` beat schedule with an
  env-driven interval) — selects `pending_disposal` projects where `disposal_scheduled_at <= now` AND
  (no approval required OR its `LLCApproval` is `granted`), and disposes them.

### SLM disposal policy
- Persist `{ retention_days, require_approval }` via the SLM settings mechanism
  (`autobot-slm-backend/api/settings.py`), key `llc.project_disposal_policy`; backend reads it at dispose
  time with safe defaults `{0, false}` when unset. Small SLM-frontend settings panel (retention days +
  require-approval toggle). Verified locally (npm works; SLM CI gate #10494).

### Frontend (Company OS)
- Project detail/browser: "Archive" (active→archived); on archived, "Delete" → confirm → `dispose`,
  showing the resulting state (done / pending approval / scheduled for a date) + a "Restore" affordance
  while pending.

---

## Data flow

Attach: enter `owner/repo` + credential → create github `CodeSource` (clone + index in background) →
`project.code_source_id` set → repo/`clone_path`/status surfaced → source appears in codebase analytics
grouped under the project. Lifecycle: Archive → (later) Delete → `dispose` consults SLM policy →
immediate | approval-gated | retention-scheduled → sweep/immediate deletes project+sprints+work-items and
the linked `CodeSource` (clone + index), repo untouched.

## Error handling

- Attach with bad repo / missing credential / clone failure → the `CodeSource` records `status=error` +
  `error_message` (sanitized, tokens stripped — already done by the sources layer); project link still
  set so the UI can show + retry sync, or the attach can roll back the link on immediate failure (choose
  rollback: if create/sync fails synchronously, do not set `code_source_id`).
- `dispose` on non-archived → `409`. Approval rejected → stays archived, disposal cleared.
- Disposal only deletes a `CodeSource` that is not `shared_with` others; shared → unlink only.
- SLM policy unreadable → safe defaults.

## Testing

- API: attach (creates/links source, sets `code_source_id`) + bad repo/credential rollback; detach
  (unlink only, source survives); `with-repos` listing; `ProjectResponse` includes source summary.
- Lifecycle: archive/restore; dispose immediate vs retention vs approval-gated (`409` on non-archived);
  `DELETE` requires archived.
- Disposal service: deletes project+sprints+work-items; deletes the linked non-shared source; leaves a
  shared source (unlink only); never the GitHub repo; idempotent.
- Sweep: disposes only due + approved `pending_disposal`.
- SLM policy: read + defaults; frontend panel round-trips.
- Frontend: attach/sync/detach flow, repo + clone_path display, analytics grouping, archive/delete/restore
  states.
- If `source_service.py` is extracted, add a regression test that the existing sources HTTP endpoints
  still behave (create/get/delete) via the service.
