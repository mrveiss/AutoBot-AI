# Company OS project ↔ repo linkage, workspace, and archive→dispose lifecycle — design

**Date:** 2026-07-07
**Umbrella:** #11129
**Status:** design — decisions captured; ready for user review → writing-plans

## Goal

Company OS (LLC) projects can attach a GitHub repo (cloned into a persistent per-project workspace,
surfaced in the UI and as a Codebase Analytics target), and follow an **archive → dispose** lifecycle
instead of a hard delete, governed by an **SLM-configurable disposal policy** (retention period +
optional second-pair-of-eyes approval; default immediate).

## Decisions (brainstorm 2026-07-07)

- **Workspace** = persistent `<projects_root>/<company-slug>/<project-slug>` (root is config/env-driven,
  never hardcoded). Attaching a repo clones into it; the path is shown in the UI; disposal removes it.
- **Repo** = attach an EXISTING repo by URL, **one per project**, cloned with AutoBot's connected GitHub
  credentials. Re-attach to change.
- **Codebase analytics** consumes the workspace: each project `workspace_path` is a first-class analytics
  target; the analytics view gets a "Project repos" selector driving the existing indexing endpoint.
- **Lifecycle**: `active → archived → pending_disposal → disposed`. `DELETE /projects/{id}` stops
  hard-deleting; deletion routes through this flow.
- **Disposal scope**: delete AutoBot data (project + its sprints/work-items) + the local workspace folder.
  **NEVER** delete the GitHub repo — only unlink.
- **Disposal policy** (SLM-configurable): `{ retention_days:int = 0, require_approval:bool = false }`.
  Default = immediate disposal, no approval, no retention. Approval via the existing `LLCApproval`;
  retention via a Celery-beat sweep.

## Scope

- **Phase 1** — repo linkage + workspace + codebase-analytics integration.
- **Phase 2** — archive→dispose lifecycle + SLM-configurable disposal (retention + approval).
- **Phase 3 (own spec, deferred, YAGNI here)** — codebase-analytics findings → project work items that
  agents pick up.

Out of scope: creating new GitHub repos; multiple repos per project; deleting the GitHub repo on
disposal; per-project retention overrides (policy is global from SLM).

---

## Phase 1 — Repo linkage + workspace + analytics

### Model (`llc/models/sprint.py` — `LLCProject`)
Add nullable columns (+ Alembic migration):
- `github_repo: str | None` — canonical `owner/repo` (or full URL, normalized to `owner/repo`).
- `workspace_path: str | None` — absolute path to the cloned workspace, once cloned.
- `repo_attached_at: datetime | None`.
- `repo_clone_status: str | None` — `pending | cloning | ready | failed` (drives the UI spinner/error);
  `repo_clone_error: str | None` for the failure message.

### Workspace service (`llc/services/project_workspace.py`, new — one clear responsibility)
- `projects_root()` → `config`-driven base dir (env var, module-level constant per project convention;
  e.g. `LLC_PROJECTS_ROOT`, default under `config.path.data_path / "llc-projects"`).
- `workspace_dir(company_slug, project_slug) -> Path` — deterministic `<root>/<company-slug>/<project-slug>`.
- `async clone_repo(project, repo_url) -> Path` — validate URL (reuse the strict GitHub URL parsing in
  `llc/api/github_webhooks.py:validate_github_pr_url`-style helpers; here validate `owner/repo`), clone
  with AutoBot's connected GitHub credentials (reuse the provider-auth / git-credential mechanism the
  agents already use), into `workspace_dir`. Idempotent: if the dir exists, `git remote set-url` +
  `git fetch` rather than re-clone. Returns the path.
- `remove_workspace(project)` — `rmtree` guarded to be strictly inside `projects_root()` (never escape).

### API (`llc/api/sprints.py`, extends the projects router)
- `POST /api/llc/projects/{id}/repo` `{ repo_url }` → validate, clone (async; the endpoint returns
  `202` with a clone status the UI polls, OR runs inline with a bounded timeout — see Data flow), set
  `github_repo` + `workspace_path` + `repo_attached_at`, return the updated project.
- `DELETE /api/llc/projects/{id}/repo` → unlink (`github_repo=None`); keep the folder unless the project
  is later disposed.
- `GET /api/llc/projects/with-repos` → `[{ project_id, name, company_id, company_slug, github_repo,
  workspace_path, status }]` for all projects that have a `workspace_path` — feeds the analytics selector.
- Existing `ProjectResponse` gains `github_repo` + `workspace_path`.

### Codebase-analytics integration
- The analytics view (`autobot-frontend/src/components/analytics/CodebaseAnalytics.vue`) gains a
  "Project repos" selector populated from `GET /api/llc/projects/with-repos`. Selecting one calls the
  existing `POST /api/analytics/code/index` with `target_path = workspace_path`, and the status/quality
  panels operate on it. No new analysis engine — the workspace path IS the target the analytics already
  accepts (`analytics_code.py` `target_path`, validated by `validate_path`).

### Frontend (`ProjectBrowserView.vue` + project detail)
- Show the linked repo (`owner/repo`, link out to GitHub) + the `workspace_path` (copyable) + an
  "Attach repo" action (input repo URL → POST). Clone status/spinner while cloning.

---

## Phase 2 — Lifecycle + configurable disposal

### Model additions (`LLCProject`)
- Extend the `status` enum with `archived` (keep existing values). Add:
  `archived_at: datetime | None`, `disposal_scheduled_at: datetime | None`,
  `disposal_approval_id: uuid | None` (FK to `llc_approvals.id`, SET NULL).
- Migration adds the enum value + columns.

### Endpoints (`llc/api/sprints.py`)
- `POST /api/llc/projects/{id}/archive` → `status=archived`, `archived_at=now` (reversible).
- `POST /api/llc/projects/{id}/restore` → archived → `active` (clears disposal fields if pending).
- `POST /api/llc/projects/{id}/dispose` → **only allowed when `archived`** (else `409`). Reads the SLM
  disposal policy and:
  - `require_approval` → create an `LLCApproval` (type = project_disposal), set
    `status=pending_disposal` + `disposal_approval_id`; disposal proceeds only after approval.
  - `retention_days > 0` → `status=pending_disposal`, `disposal_scheduled_at = now + retention` (a
    Celery-beat sweep disposes it when due; restorable until then).
  - else (immediate, no approval) → dispose now.
- `DELETE /api/llc/projects/{id}` → **no longer hard-deletes**; returns `409` unless already `archived`,
  and when archived delegates to the dispose flow (so the UI's delete = "archive then delete" is a real
  two-step: you must archive first, then dispose).

### Disposal execution (`llc/services/project_disposal.py`, new)
- `async dispose(project)` — delete the project + its sprints + work-items (DB, in a transaction) and
  `remove_workspace(project)`. **Never** call the GitHub API to delete the repo. Idempotent + audited
  (log + optional LLC audit entry).
- **Celery-beat sweep** `dispose_due_projects` — periodically selects `pending_disposal` projects whose
  `disposal_scheduled_at <= now` AND (no approval required OR approval `granted`), and disposes them.
  Registered in `celery_app.py` beat schedule with the interval from a module-level constant/env.

### Approval integration
- Reuse `LLCApproval` (models/approval.py). A `project_disposal` approval references the project; on
  `granted`, the sweep (or an immediate check) proceeds; on `rejected`, the project stays `archived`
  (disposal cancelled, fields cleared).

### SLM disposal policy (config)
- Store `{ retention_days, require_approval }` via the SLM settings mechanism
  (`autobot-slm-backend/api/settings.py`), key e.g. `llc.project_disposal_policy`. Backend reads it at
  dispose time (with safe defaults `{0, false}` when unset).
- SLM frontend (`autobot-slm-frontend`) gets a small "Project Disposal Policy" settings panel
  (retention days + require-approval toggle). Verified locally (npm works; SLM CI gate exists, #10494).

### Frontend (Company OS)
- Project detail/browser: "Archive" button (active→archived); on an archived project, "Delete" →
  confirm → `dispose`, showing the resulting state (immediate done / pending approval / scheduled for
  <date>) and a "Restore" affordance while pending.

---

## Data flow

Attach: user enters repo URL → `POST …/repo` → clone into workspace → `github_repo` + `workspace_path`
surfaced → repo appears in the Codebase Analytics "Project repos" selector → indexable. Lifecycle:
Archive → (later) Delete → `dispose` consults SLM policy → immediate | approval-gated | retention-scheduled
→ sweep/immediate deletes DB rows + workspace folder (repo untouched).

## Error handling

- Clone failure (bad URL / auth / network) → repo NOT linked, workspace cleaned, clear 4xx error.
- `dispose` on non-archived → `409`. Approval rejected → stays archived, disposal cleared.
- `rmtree` strictly guarded to the project subtree inside `projects_root()` — refuse anything that
  resolves outside it.
- SLM policy unreadable → safe defaults (immediate, no approval, no retention).
- Re-attach over an existing workspace → fetch/set-url, not a destructive re-clone.

## Testing

- Workspace service: `workspace_dir` determinism; clone happy-path (mock git) + bad URL + auth fail;
  `remove_workspace` path-safety (refuses escapes).
- API: attach/unlink repo; `with-repos` listing; archive/restore; dispose immediate vs retention vs
  approval-gated (`409` on non-archived); `DELETE` requires archived.
- Disposal service: deletes project+sprints+work-items+folder, never the repo; idempotent.
- Sweep: disposes only due + approved `pending_disposal`; skips future-dated / unapproved.
- SLM policy: read + defaults; frontend panel round-trips.
- Frontend: attach flow, workspace path display, analytics selector, archive/delete/restore states.
