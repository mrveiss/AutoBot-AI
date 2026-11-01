# ADR-011: One Frontend — the SLM Back Office Becomes `/admin`, the SLM Backend Stays Remote Behind `/slm/api`

## Status

**Status**: Rejected (2026-11-02), by the maintainer: "slm is firs thing user installs and is the point from which other functionality gets installed, we keep it separate". See [ADR-012](012-slm-first-and-separate.md). The rest of this document is kept as the record of what was proposed. The `/admin` section that landed from it stays, for main-app administration only.

Refines [ADR-008](008-frontend-shared-code-boundary.md) (the two-SPA boundary) for the case where there is one SPA. Does not change [ADR-005](005-single-frontend-mandate.md) or [ADR-010](010-role-separation-count-agnostic-placement.md).

## Date

**Date**: 2026-10-31

## Context

AutoBot ships two Vue apps: `autobot-frontend/` (the user app) and `autobot-slm-frontend/` (the console of the SLM, AutoBot's own service lifecycle manager — it provisions, updates and monitors **AutoBot's** nodes and services, nothing else; maintainer positioning 2026-10-25: *"AutoBot is not platform to manage system — our SLM manages only autobot infrastructure."*). The SLM console is served under `/slm/` from its own build, logs in separately (SLM HS256 token in `sessionStorage['slm_access_token']`, `autobot-slm-frontend/src/utils/authStorage.ts`), and talks to the SLM backend at `/slm/api` through its own `ApiClient`.

Epic #19829 records the decision to end that split. The ADR is task T1 (#19830); it is written before any code moves so that T4–T16 implement one design.

### Maintainer decisions this ADR records (verbatim, epic #19829, 2026-10-27)

> - ONE frontend app (`autobot-frontend`). SLM views become a role-gated back-office section at `/admin/<domain>/...` (admins + granted advanced users, permission `service.management` or admin role).
> - ONE user system (#10193): one login, one session.
> - SLM BACKEND stays separately deployable (its own machine when scaling). The unified UI calls it via `/slm/api`, proxied by nginx to wherever the SLM runs. The SLM-only UI (`autobot-slm-gui` profile, `/slm/` static build) is retired.
> - Hard deps: #10200 (slm_users migration), #16389 (aud/iss on RS256), #18892 (SLM 401 redirect). RS256 + JWKS verifier already done (#10196-#10198).

Related rulings that still apply, with their new location:

- #17814, maintainer comment 2026-10-27: *"there will be one frontend app; SLM views move into `autobot-frontend` under a role-gated `/admin` section (epic #19829) ... the reconciliation target is now the unified app, not SLM."*
- Owner rule 2026-10-22 (on #19217): *"We want unified control for one area features even if toggles are needed in different dialogs, and system-wide admin components go into the SLM panel."* The rule stands; "the SLM panel" is now `/admin`.
- #13854 / #19125 (owner decision 2026-10-21, *"Super admin is the highest form of admin"*): the permission table decides, never an `is_admin` shortcut, and `superadmin` holds admin's set — see `docs/developer/THREAT_MODEL.md` §5.
- #16387 (owner decision): SLM token revocation fails **closed** — a revocation-store outage answers 503 and keeps the session; only 401 ends it (#18892). The unified client keeps that distinction.

### Measured state (`origin/main` at `b28e9d43e3`, 2026-10-31)

| Fact | Measurement |
|---|---|
| SLM route records | **77**, not the 76 in the epic: 63 `path:` entries in `autobot-slm-frontend/src/router/index.ts` + 14 in `monitoringRoutes.ts`. #19851 (2026-10-28) nested the performance children under a layout and added one default-redirect record. |
| Of which redirects / views | 16 redirect records (14 + 2), 61 component records (5 of them layouts: maintenance, settings, monitoring, tools, performance) |
| Admin-only today | 23 view routes carry `meta.admin: true` (plus one admin-flagged redirect); the SLM guard refuses them unless `/auth/me` returns `is_admin` |
| Existing main-app `/admin` routes | 9: `users`, `sandbox`, `advanced-control`, `budget-policies`, `system-health`, `provider-fallback`, `pricing`, `mcp-servers`, `permission-scopes` (`autobot-frontend/src/router/index.ts:777-895`), all `meta.admin: true`; `nav-items-coverage.test.ts` (#16933) requires an `adminMenuItems` entry per `/admin/*` route |
| Main-app routes under `/slm/` | 2: `/slm/tools/novnc` (#4977), `/slm/themes` (#10472) — both trip #19843's "no `/slm/` targets" guard |
| Main-app legacy redirects to the SLM | 9 records (`/tools`, `/tools/*`, `/monitoring`, `/monitoring/*`, `/settings`, `/settings/*`, `/infrastructure`, `/tls-certificates`, …) jump to `getSLMAdminUrl() + '/#/…'` — hash URLs the history-mode SLM router never served |
| `service.management` holders | `ROLE_PERMISSIONS` in `autobot_shared/auth/permissions.py`: `admin` (:301 block) and `operator` (:368 block); `superadmin` inherits admin's set; not analyst, editor, user, readonly. The user app already derives `userStore.hasServiceManagement` from the generated copy of that table |
| SLM i18n | 11 locale files; `en.json` has **3682** keys (3684 with `_meta`), not the 3628 in the epic/#19839. The user app's `en.json` already has an `admin` namespace with 5 children (`mcpServers`, `permissionScopes`, `pricing`, `providerFallback`, `systemHealth`) |
| SLM locale generator | `scripts/lift_locale_translations.py --app autobot-slm-frontend/src/locales --check` runs in `slm-frontend-check.yml:142`; the SLM locales are a deterministic projection of the user app's translations |
| Where `/slm` is served | docker: `docker/nginx/nginx-slm-locations.conf` (`/slm/api/ws/`, `/slm/api/` proxied; `/slm/` aliased to the built bundle); bare-metal installer: one `location /slm/` proxied whole to the SLM; split-host ansible frontend site `roles/frontend/templates/nginx-frontend.conf.j2`: **no** `/slm` location at all |
| Who builds the SLM UI | `docker/frontend/Dockerfile` `slm-builder` + `slm-gui` stages; `docker-compose.yml` `autobot-slm-gui` profile; `slm_manager` role `tasks/main.yml:905-941` via `_shared/tasks/build_publish_slm_frontend.yml`, plus `slm-admin-ui.service` and `colocated_frontend_detect.yml`; CI `slm-frontend-check.yml`, with SLM steps in `auto-fix-generated-types.yml`, `duplication-guard.yml`, `stylelint-tokens.yml`, `verify-generated-types.yml` |
| Machine callers of the SLM login | ansible `update-all-nodes.yml:768,860` and `provision-fleet-roles.yml:873` POST `/slm/api/auth/login` on the SLM host directly |

## Decision

### 1. One app, one namespace: `/admin/<domain>/...`

Everything the SLM console shows moves into `autobot-frontend` under one parent route `/admin` with an `AdminLayout` (#19833). The domains are the ones the port issues already name — `fleet` (#19835), `monitoring` (#19836), `settings` (#19837) — plus `tools`, `agents`, `skills`, `orchestration`, `security` and `shared-links` for #19838. A route's domain is where its SLM section was; nothing is renamed on the way.

**The 9 existing main-app `/admin` routes** become children of the same parent in #19833 **keeping their current paths** (its AC: "old URLs still resolve"). Each takes its domain path when its SLM counterpart is ported or reconciled, with the old path left as a redirect:

| Today | Lands at | Why there |
|---|---|---|
| `/admin/users` | `/admin/settings/users` | reconciles with SLM `settings/admin/users` (#17814) |
| `/admin/mcp-servers` | `/admin/tools/mcp` | reconciles with SLM `tools/mcp` (#17814) |
| `/admin/advanced-control` | `/admin/tools/advanced-control` | same view exists in the SLM `tools/` section |
| `/admin/provider-fallback` | `/admin/settings/llm-fallbacks` | SLM `settings/admin/llm-fallbacks` is the same concern (GH#8998 moved it there) |
| `/admin/sandbox` | `/admin/tools/sandbox` | no SLM counterpart; a tool |
| `/admin/budget-policies` | `/admin/settings/budget-policies` | sibling of SLM `settings/admin/budget-audit` (read-only audit), not a duplicate |
| `/admin/system-health` | `/admin/monitoring/system-health` | no SLM counterpart; monitoring |
| `/admin/pricing` | `/admin/settings/pricing` | no SLM counterpart (#17811: misplaced) |
| `/admin/permission-scopes` | `/admin/settings/permission-scopes` | no SLM counterpart (#17811: misplaced) |
| `/slm/tools/novnc` | `/admin/tools/novnc` | same view as SLM `tools/novnc` |
| `/slm/themes` | `/admin/settings/themes` | theme packages are platform-wide settings |

Which implementation survives in each duplicate row is #17814's decision, taken in the unified app, not here.

### 2. Who may enter: the permission table, at two levels

- The `/admin` parent carries `meta.permission: 'service.management'` and the router guard checks it with the **table-derived** predicate (`userStore.hasServiceManagement`, built from the generated `ROLE_PERMISSIONS`; or `usePermissions().holdsPermission`, never `hasPermission`, whose admin bypass #13854 ruled out). A caller without it is redirected, as the existing `meta.admin` / `meta.minRole` guards do.
- Children that are `meta.admin: true` in the SLM today keep `meta.admin: true`: an administrative role (`admin`, `superadmin` — `ADMIN_ROLES` in `autobot-frontend/src/constants/roles.ts`). This reproduces the SLM's `is_admin` gate exactly; it does not widen it.
- #19843 makes "every `/admin` child declares one of the two" a CI guard.
- The UI check is routing only. The SLM backend's own `require_permission` gates (`autobot-slm-backend/services/auth.py`, `PermissionGate` over `evaluate_permission`) remain the authority and are unchanged by the port.

### 3. The SLM backend stays remote, behind `/slm/api` only

The SLM backend keeps its own deployment (`slm` role in ADR-010; its own machine when scaling). The browser reaches it at **one path, on the user app's origin**: `/slm/api` (HTTP) and `/slm/api/ws/` (WebSocket upgrade), proxied by nginx to an upstream named by the SSOT, never a literal host (#19832 adds that location to the split-host frontend site, which has none today). The SLM host keeps serving `/slm/api` on its own vhost for its machine callers (node agents, the update playbooks). The `/slm/` static UI is retired; after #19840 nginx answers `/slm/<path>` with a 301 to the mapped `/admin/...` path.

### 4. One session

| | Before | After |
|---|---|---|
| Token | SLM HS256 from `/slm/api/auth/login`, `sessionStorage['slm_access_token']` (localStorage fallback), read by `readSlmToken()` | the main-app session (`localStorage['autobot_auth']`, `autobot-frontend/src/utils/authToken.ts`), an RS256 authority token |
| Verified by | `decode_token_async`: HS256 with the SLM secret, RS256 via JWKS (#10196–#10198) | the same RS256/JWKS path, now **requiring** `aud`/`iss` that name the SLM API (#16389, #19831) |
| Client | SLM `ApiClient` (base `getSlmApiBase()`), own 401 handling | one `slmApi` adapter over the main `ApiClient`, base `/slm/api` (#19834): no second client class, no read of `slm_access_token` |
| 401 / 503 | 401 clears SLM keys and redirects to the SLM `/login` (misrouted today, #18892) | 401 ends the one session; 503 `revocation_check_unavailable` keeps it (#16387 fails closed) |
| Users | `slm_users` | the main user store (#10200) |

`#10200`, `#16389`, `#18892` are open on 2026-10-31; W0 (#19831, #19832) cannot be declared done before they land.

### 5. i18n: the SLM tree nests under `admin.*`

#19839 moves every SLM key `<ns>.<rest>` to `admin.<ns>.<rest>` in each of the 11 user-app locales, next to the 5 `admin.*` children that already exist (no top-level name overlaps were measured). The merged values are the lifting rule's current output, so the step is a move, not a retranslation; keys still in English count toward `repo_tests/i18n_untranslated_ratchet_test.py` like any other. Once #19842 deletes the SLM locale directory the generator has no target; its `--check` step goes with `slm-frontend-check.yml`.

### 6. The kit boundary (ADR-008) is unchanged

`@autobot/ui` (`libs/autobot-ui`) still carries no backend knowledge. Ported views keep their kit components as they are. The SLM `ApiClient`, `useSlmWebSocket` and the fleet/provision stores are **app** code: they move into `autobot-frontend` (#19834), not into the kit. ADR-008's reason for two clients — different token source and 401 policy — disappears with one session, which is why one client with a second base path is the right shape now.

### 7. Redirects, and the order they become reachable

1. **W2 (#19835–#19838):** each port adds an in-app redirect from the SLM's history-mode path to the new path (`/slm/fleet/nodes` → `/admin/fleet/nodes`). While nginx still aliases `/slm/`, those routes are shadowed — the alias wins over the SPA fallback — so they are defined early but take effect only at step 3.
2. **W2:** the 9 main-app hash redirects (`/tools`, `/monitoring`, `/settings`, `/infrastructure`, `/tls-certificates` and their `/*` forms) become plain in-app redirects to `/admin/tools`, `/admin/monitoring`, `/admin/settings`, `/admin/fleet/infrastructure`, `/admin/security`; `getSLMAdminUrl()` loses its last caller.
3. **W4 #19840:** drop the `slm-builder`/`slm-gui` Dockerfile stages and the `autobot-slm-gui` profile; nginx 301s `/slm/<path>` → `/admin/<path>` using the table below and keeps `/slm/api`, `/slm/api/ws/`.
4. **W4 #19841:** `slm_manager` stops building and serving the UI (`tasks/main.yml:905-941`, `slm-admin-ui.service`, `colocated_frontend_detect.yml`), deploys the backend only; the builtin updater applies it without leaving a stale `/slm/` root.
5. **W4 #19842:** remove `autobot-slm-frontend/`, its lockfile entries, `slm-frontend-check.yml` and the SLM steps in the four other workflows, with per-view/store/test/key landing evidence in the PR.
6. **W5 #19843:** guards — one Vite app, no `/slm/` targets except `/slm/api`, every `/admin` child declares a permission.

### 8. Route map — all 77 SLM records → `/admin`

Permission: **SM** = `service.management` (the parent gate); **ADMIN** = administrative role (`meta.admin: true`, as in the SLM today); a redirect carries its target's. "→" rows are redirect records.

| # | SLM path (today) | New path | Perm. | Issue |
|---|---|---|---|---|
| 1 | `/login` | retired — the main-app `/login` | — | #19831 |
| 2 | `/sso-callback` | retired — one login (see Open questions) | — | #19831 |
| 3 | `/setup` (first-run wizard, #1294) | `/admin/fleet/setup` | SM | #19835 |
| 4 | `/` → `/fleet` | `/admin` → `/admin/fleet/nodes` | SM | #19833 |
| 5 | `/fleet/:tab?` (default `nodes`) | `/admin/fleet/:tab?` | SM | #19835 |
| 6 | `/services` → | → `/admin/orchestration/per-node` | SM | #19838 |
| 7 | `/shared-links` | `/admin/shared-links` | ADMIN | #19838 |
| 8 | `/deployments/:tab?` (default `standard`) | `/admin/fleet/deployments/:tab?` | SM | #19835 |
| 9 | `/backups/replications` → | → `/admin/orchestration/replication` | SM | #19838 |
| 10 | `/backups/:tab?` | `/admin/fleet/backups/:tab?` | SM | #19835 |
| 11 | `/replications` → | → `/admin/orchestration/replication` | SM | #19838 |
| 12 | `/maintenance` (layout) | `/admin/fleet/maintenance` | SM | #19835 |
| 13 | `/maintenance/updates` → | → `/admin/fleet/maintenance/updates/system` | SM | #19835 |
| 14 | `/maintenance/updates/:tab` | `/admin/fleet/maintenance/updates/:tab` | SM | #19835 |
| 15 | `/code-sync` → | → `/admin/fleet/maintenance/updates/code-sync` | SM | #19835 |
| 16 | `/agents/:tab?` (default `local-agents`) | `/admin/agents/:tab?` | SM | #19838 |
| 17 | `/agent-config` → | → `/admin/agents/local-agents` | SM | #19838 |
| 18 | `/infrastructure` → | → `/admin/fleet/infrastructure` | SM | #19835 |
| 19 | `/settings` (layout) | `/admin/settings` | SM | #19837 |
| 20 | `/settings/` → | → `/admin/settings/general` | SM | #19837 |
| 21 | `/settings/general` | `/admin/settings/general` | SM | #19837 |
| 22 | `/settings/infrastructure` → `/roles` | → `/admin/settings/roles` | SM | #19837 |
| 23 | `/settings/nodes` → `/` | → `/admin/fleet/nodes` | SM | #19837 |
| 24 | `/settings/monitoring` | `/admin/settings/monitoring` | SM | #19837 |
| 25 | `/settings/notifications` | `/admin/settings/notifications` | SM | #19837 |
| 26 | `/settings/api` | `/admin/settings/api` | SM | #19837 |
| 27 | `/settings/backend` | `/admin/settings/backend` | SM | #19837 |
| 28 | `/settings/security` (MFA, API keys) | `/admin/settings/security` (see Open questions) | SM | #19837 |
| 29 | `/settings/admin/users` | `/admin/settings/users` | ADMIN | #19837, #17814 |
| 30 | `/settings/admin/cache` | `/admin/settings/cache` | ADMIN | #19837 |
| 31 | `/settings/admin/prompts` | `/admin/settings/prompts` | ADMIN | #19837 |
| 32 | `/settings/admin/personality` | `/admin/settings/personality` | ADMIN | #19837 |
| 33 | `/settings/admin/secrets` | `/admin/settings/secrets` | ADMIN | #19837 |
| 34 | `/settings/admin/log-forwarding` | `/admin/settings/log-forwarding` | ADMIN | #19837 |
| 35 | `/settings/admin/web-research` | `/admin/settings/web-research` | ADMIN | #19837 |
| 36 | `/settings/admin/npu-workers` → | → `/admin/fleet/npu` | SM | #19835 |
| 37 | `/settings/admin/config-defaults` | `/admin/settings/config-defaults` | ADMIN | #19837 |
| 38 | `/settings/admin/llm` | `/admin/settings/llm` | ADMIN | #19837 |
| 39 | `/settings/admin/llm-fallbacks` | `/admin/settings/llm-fallbacks` | ADMIN | #19837 |
| 40 | `/settings/admin/budget-audit` | `/admin/settings/budget-audit` | ADMIN | #19837 |
| 41 | `/settings/admin/sso` | `/admin/settings/sso` | ADMIN | #19837 |
| 42 | `/settings/admin/data-hygiene` | `/admin/settings/data-hygiene` | ADMIN | #19837 |
| 43 | `/settings/disposal-policy` | `/admin/settings/disposal-policy` | SM | #19837 |
| 44 | `/settings/findings-policy` | `/admin/settings/findings-policy` | SM | #19837 |
| 45 | `/monitoring` (layout) | `/admin/monitoring` | SM | #19836 |
| 46 | `/monitoring/` → | → `/admin/monitoring/system` | SM | #19836 |
| 47 | `/monitoring/system` | `/admin/monitoring/system` | SM | #19836 |
| 48 | `/monitoring/logs` | `/admin/monitoring/logs` | SM | #19836 |
| 49 | `/monitoring/dashboards` | `/admin/monitoring/dashboards` | SM | #19836 |
| 50 | `/monitoring/alerts` | `/admin/monitoring/alerts` | SM | #19836 |
| 51 | `/monitoring/errors` | `/admin/monitoring/errors` | SM | #19836 |
| 52 | `/monitoring/admin` | `/admin/monitoring/admin` | ADMIN | #19836 |
| 53 | `/monitoring/agent-ledger` | `/admin/monitoring/agent-ledger` | ADMIN | #19836 |
| 54 | `/monitoring/performance` (layout) | `/admin/monitoring/performance` | SM | #19836 |
| 55 | `/monitoring/performance/` → | → `/admin/monitoring/performance/overview` | SM | #19836 |
| 56 | `/monitoring/performance/overview` | `/admin/monitoring/performance/overview` | SM | #19836 |
| 57 | `/monitoring/performance/traces` | `/admin/monitoring/performance/traces` | SM | #19836 |
| 58 | `/monitoring/performance/slos` | `/admin/monitoring/performance/slos` | SM | #19836 |
| 59 | `/monitoring/performance/alerts` | `/admin/monitoring/performance/alerts` | SM | #19836 |
| 60 | `/orchestration/:tab?` (default `per-node`) | `/admin/orchestration/:tab?` | SM | #19838 |
| 61 | `/roles` | `/admin/settings/roles` | SM | #19837 |
| 62 | `/skills/:tab?` (default `active`) | `/admin/skills/:tab?` | SM | #19838 |
| 63 | `/external-agents` → | → `/admin/agents/external-agents` | SM | #19838 |
| 64 | `/security/:tab?` (default `overview`) | `/admin/security/:tab?` | SM | #19838 |
| 65 | `/tools` (layout) | `/admin/tools` | SM | #19838 |
| 66 | `/tools/` → | → `/admin/tools/fleet` | SM | #19838 |
| 67 | `/tools/fleet` | `/admin/tools/fleet` | SM | #19838 |
| 68 | `/tools/terminal` | `/admin/tools/terminal` | ADMIN | #19838 |
| 69 | `/tools/files` | `/admin/tools/files` | ADMIN | #19838 |
| 70 | `/tools/browser` | `/admin/tools/browser` | ADMIN | #19838 |
| 71 | `/tools/novnc` | `/admin/tools/novnc` | ADMIN | #19838 |
| 72 | `/tools/advanced-control` | `/admin/tools/advanced-control` | ADMIN | #19838 |
| 73 | `/tools/voice` | `/admin/tools/voice` | ADMIN | #19838 |
| 74 | `/tools/mcp` | `/admin/tools/mcp` | ADMIN | #19838, #17814 |
| 75 | `/tools/agents` | `/admin/tools/agents` | SM | #19838 |
| 76 | `/tools/vision` | `/admin/tools/vision` | SM | #19838 |
| 77 | `/tools/batch` | `/admin/tools/batch` | SM | #19838 |

The `/slm/<path>` 301 table in #19840 is this table with `/slm` prefixed to column 2; the hash form is handled per Open question 1.

### Alternatives considered

1. **Keep two apps, share more code** (ADR-008's standing answer). Rejected by the 2026-10-27 decision: two logins, two sessions and 11 pages built twice (#17814) are the cost being removed; sharing code does not remove them.
2. **Fold the SLM backend into the main backend as well.** Not chosen: the SLM must run on its own machine when scaling and is the thing that updates the main backend; the decision keeps it separately deployable and changes only how the browser reaches it.
3. **Mount the SLM app as a micro-frontend under `/admin`.** Not chosen: it keeps the second session, second client, second i18n tree and second CI the decision retires.

## Consequences

### Positive

- One login, one session, one HTTP client, one i18n tree, one Vite app, one CI lane for the UI.
- `/admin` has one owner (the parent route) and one entry rule, enforced by #19843.
- The SLM's deployment story is unchanged for operators who run it on its own node.

### Negative

- Until #10200/#16389/#18892 land, nothing in W1+ can ship to users; W0 is gated on three open issues.
- Every `/slm/...` bookmark changes; the 301 table must be complete or operators get 404s.
- The user app's bundle grows by the SLM views; lazy `import()` per route keeps them off the user paths but the i18n bundle (already ~366 KB English, #12342) gains 3682 keys.

### Neutral

- `docs/developer/ARCHITECTURE_EXCEPTIONS.md` "SLM Recovery Page" exists to recover from a broken `/slm/` bundle; once nothing serves that bundle the exception's reason is gone (see Open questions).

## Open questions for the maintainer (not decided here)

1. **Hash-form redirects.** #19840's AC asks nginx to 301 `/slm/#/<path>`. A fragment is never sent to the server, so nginx cannot see it; the hash form needs a client-side handler (a `/slm` route in the user app, or the 301 target reading `location.hash`). Which?
2. **The 9 existing `/admin` routes:** confirm the two-step rule in Decision 1 (keep paths in #19833, move to domain paths on reconciliation).
3. **`/settings/security` (row 28)** manages MFA and API keys for SLM users; after #10200 those are main-app users with their own security settings. Duplicate to reconcile under #17814, or retire?
4. **`/setup` (row 3):** confirm `/admin/fleet/setup`, and that the SLM's one-time `/setup/status` first-run redirect runs only when entering `/admin`, not on every user-app navigation.
5. **SLM `/auth/login` for machines.** The playbooks log in to the SLM with an SLM user; after #10200 and the UI's retirement, what credential do they present, and does the HS256 login path stay for them?
6. **`meta.admin` children:** keep the administrative-role gate the SLM has, or name fine-grained permissions (`admin.system`, `admin.users.write`) per child? The SLM backend's per-route gates were not enumerated for this ADR.
7. **Counts in child ACs:** #19839 quotes 3628 keys and the epic 76 routes; `origin/main` has 3682 and 77. The PRs should quote the count at merge time.
8. **#16389** carries `needs-structure` (no goal milestone / phase label) although it gates W0.
9. **SLM recovery page and `frontend_bundle_status`** (`autobot-slm-backend/api/health.py`): retire with #19841, or re-scope to the backend's own health?
10. **Upstream scheme for #19832:** the SLM vhost serves TLS (`slm_tls_cert`); does the frontend site proxy `/slm/api` over TLS to it, and from which SSOT key?
11. **The `admin.*` ruling of 2026-10-22** named "the SLM panel"; confirm the restatement "platform-wide admin UI lives under `/admin`".

## Related ADRs

- [ADR-005](005-single-frontend-mandate.md) — one frontend server; unchanged
- [ADR-008](008-frontend-shared-code-boundary.md) — the kit boundary this ADR keeps while collapsing the two SPAs
- [ADR-010](010-role-separation-count-agnostic-placement.md) — the `slm` role stays a separately placed role

---

**Author**: mrveiss
**Copyright**: © 2026 mrveiss
