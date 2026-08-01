---
tags:
  - llc
  - api
  - security
aliases:
  - Tenant Context
  - X-Organization-Id
status: current
---

# LLC API tenant-context resolution (#12215)

Every LLC API endpoint that reads or mutates company-scoped data must know
*which company* (tenant) the request is for. This document is the single
source of truth for how that tenant context is derived and enforced —
previously this was undocumented and callers only discovered the contract via
opaque `400` responses (#12215).

## Canonical mechanism: `TenantContext`

Human-facing LLC routes (i.e. everything under `/api/llc/*` except the
agent-bearer surface described below) resolve tenant context through a single
FastAPI dependency chain, defined in
[`api/user_management/dependencies.py`](../../autobot-backend/api/user_management/dependencies.py):

```
get_current_user  →  get_tenant_context  →  require_org_context
```

- **`get_current_user`** — resolves the authenticated user from the session
  JWT (`Authorization: Bearer ...`). Always required first; there is no
  tenant context without an authenticated user.
- **`get_tenant_context`** — builds a `TenantContext(org_id, user_id,
  is_platform_admin)` from the request, using this precedence for `org_id`
  (first match wins), per GH#10750 A5:
  1. `X-Organization-Id` request header.
  2. `company_id` (or `id`) path parameter — e.g.
     `/companies/{company_id}/...`.
  3. `company_id` query parameter (`?company_id=...`).
  4. `org_id` JWT claim (legacy fallback, no extra DB check).
- **`require_org_context`** — the dependency routers actually declare; wraps
  `get_tenant_context` and raises `400` with a message naming the
  `X-Organization-Id` header if no `org_id` could be resolved from any
  source.

### Anti-spoofing guarantee

A client **cannot** grant itself access to another company's data merely by
sending an `X-Organization-Id` header or `company_id` param:

- If the resolved `org_id` came from the header/path/query (sources 1–3) and
  the caller is **not** a platform admin, `get_tenant_context` performs a
  membership check against `llc_company_memberships`. Non-members are
  rejected with `403` before any handler code runs.
- Individual routers additionally re-validate that the specific resource
  being read/written belongs to `ctx.org_id` (see below) — the header only
  ever *selects* which of the caller's own companies is in scope; it can
  never grant access to a company the caller isn't a member of.
- Platform admins (`role == "admin"` or `is_platform_admin == True` on the
  JWT) may address any company without a membership check — this is the only
  privileged path.

### Per-resource IDOR guard

Once `ctx.org_id` is resolved, routers must additionally confirm the
*specific row(s)* being accessed belong to that org. The canonical helpers
(`llc/deps.py`, GH#10148/#12184) are:

| Helper | Use when |
|---|---|
| `assert_company_access(ctx, company_id)` | The route already loaded/knows a `company_id` (e.g. from a path param or a fetched row) and just needs the tenant check. |
| `load_authorized(session, Model, obj_id, ctx, ...)` | Loading a single row by id — fetch + tenant-check in one call. |
| `load_owned_project(project_id, session, ctx)` | Project-scoped resources specifically (sprints, findings). |

All of these return `404` (not `403`) on a cross-tenant mismatch, so a
cross-tenant caller can't distinguish "not yours" from "doesn't exist".

## Why some routes need the header and others don't

`_extract_request_org_id` only recognizes path params literally named
`company_id` or `id`. Routes nested under `/companies/{company_id}/...`
therefore resolve `org_id` from the URL with **no header required**. Flat
routes keyed by a different resource id (e.g. `/goals/{goal_id}`,
`/agents/{agent_id}/heartbeat/trigger`) have no such path param, so the
caller **must** send `X-Organization-Id` (or rely on the JWT `org_id`
fallback) — otherwise `require_org_context` returns `400`.

This is expected, not a bug: **when calling any flat-resource LLC endpoint,
always send `X-Organization-Id`.** It is safe to send it unconditionally on
every LLC request (nested routes simply ignore it in favour of the path
value, per the precedence above).

## Legitimate variants (not deviations)

A few LLC routers intentionally use a different mechanism because the caller
is not a human session:

- **Agent bearer auth** (`/api/llc/agent/*`) — `LLCAgentAuthMiddleware`
  (`llc/middleware/agent_auth.py`) validates an `Authorization: Bearer
  <agent-api-key>` token against `llc_agent_api_keys` and injects
  `request.state.agent_id` / `request.state.company_id` directly. Agents
  authenticate with a per-agent key scoped to exactly one company at
  creation time, so there is no header to spoof and no `TenantContext` to
  resolve.
- **Board-role checks** (`llc/api/controls.py`, replay.py) — instant-control
  endpoints (pause/resume/terminate) require a specific `MembershipRole`
  (`OWNER`/`ADMIN`), not just membership, via `llc.deps.require_board_role`.
  This is a stricter, not looser, variant of the same DB-backed membership
  check.
- **Webhooks** (`llc/api/github_webhooks.py`) — authenticated via GitHub's
  HMAC webhook signature, not a user session; no `TenantContext` exists to
  resolve.
- **Public/global endpoints** (`llc/api/health.py`, `llc/api/adapters.py`) —
  return no tenant-scoped data (a health probe; the list of registered
  adapter *types*, not per-company config), so no tenant context is needed.

## Audit history

- **#12215**: documented this contract; standardized error messaging;
  closed two IDOR gaps found during the audit — `llc/api/activity.py` and
  `llc/api/routines.py` previously required only authentication with **no**
  tenant check at all, letting any authenticated user read another
  company's activity log, or read/update/delete/trigger another company's
  routines by UUID. Both now use `require_org_context` +
  `assert_company_access`/an owned-row loader, consistent with every other
  LLC router.
- **#12184/#10148**: introduced the shared `assert_company_access` /
  `load_authorized` / `load_owned_project` helpers, consolidating ~9
  near-identical per-router IDOR checks.
- **#12148**: templates.py hardened to bind company-scoped operations to
  `ctx.org_id` rather than trusting a caller-supplied `company_id`.
- **#12233**: `companies.py` `GET/PATCH/DELETE /{company_id}` gained the
  same `ctx.org_id == company_id` guard as other routers.
- **#10750 A5**: introduced the `TenantContext` precedence + membership-check
  design described above.
