# Scoped + Shareable Custom Skills and Custom Agents

**Status:** Design approved · **Umbrella:** #11277 · **Absorbs:** #11141 · **Date:** 2026-07-08

## Problem

Custom skills (user-created, imported, or hub-installed) and custom agents have no
per-user / per-group / per-company scoping. Today:

- Custom skill **definitions** persist to Redis or `/var/lib/autobot/skill_cache`, but
  `SkillManager.initialize()` only re-loads *config/enabled state* for already-registered
  skills — it never re-registers custom definitions. **They vanish from the registry on
  backend restart.**
- There is no sharing model: a skill is global-in-Redis or nothing. Nothing lets a user
  create a skill once and share it company-wide, or limit it to a group.
- Without a canonical shared instance, the same skill gets **duplicated** per user.
- Custom agents are company-scoped via `agent_org_nodes.company_id` (Company OS) but have
  no way to be *limited* below company-wide, and skills don't align to that model.

Secrets already solved the scoping/sharing problem (`SecretScope` + `SecretGrant`). This
design mirrors that model — authorization only, no crypto envelope — for skills and agents.

## Goals

1. Custom skills/agents are created **once and shared company-wide by default**
   (`ORGANIZATION` scope), narrowable to `GROUP` / `SHARED` / `USER`. **No duplication.**
2. Definitions persist to **Postgres** so they survive `/opt/autobot` git-pull deploys.
3. Custom/hub/imported skills **re-register at boot** (fix the restart-loss bug).
4. Governance/trust gating retained (external ⇒ sandboxed).
5. One reusable scope/grant primitive serves **both** skills and agents.

## Non-Goals

- No cross-org "SYSTEM" scope. `ORGANIZATION` is the ceiling; truly-global stays the
  builtin/code path (promote via `promoter.py`).
- No at-rest encryption of definitions (they are manifests/config, not secret values).
- No new agent-sharing subsystem — agents keep Company OS (`agent_org_nodes.company_id`)
  for the ORG default and only use grants when limited.

## Decisions (brainstormed)

| Topic | Decision |
|---|---|
| Scope enum | `USER / SESSION / SHARED / GROUP / ORGANIZATION`, mirroring `SecretScope` |
| Default scope | `ORGANIZATION` (company-wide), narrowable down |
| Ceiling | `ORGANIZATION`; global = builtin code via `promoter.py` |
| Reuse depth | Authorization only (scope + grants); plaintext Postgres definitions |
| Enforcement | One global registry + `visible_to(principal)` filter at list/route/execute |
| Agents | Reuse `agent_org_nodes.company_id`; `resource_grants` only when limited |
| Sequencing | Shared core → skills → agents; reload fix as early prerequisite |

## Architecture

### Data model (shared core)

`ScopeLevel` enum in `autobot_shared` (mirrors `SecretScope`, no crypto).

`skill_definitions` (Postgres) — canonical, dedup'd home for custom skills:

```
id, name, version, manifest (JSONB), body (text),
owner_id, company_id, scope (default ORGANIZATION),
trust_level (sandboxed|monitored|trusted), source (generated|imported|hub),
is_active, created_at, updated_at
UNIQUE(company_id, name)
```

`resource_grants` (Postgres) — one generic grant table, discriminated by `resource_type`
so the same share/revoke mechanics serve skills and agents:

```
id, resource_type (skill|agent), resource_id,
grantee_type (user|group), grantee_id, permission (view|use|manage),
created_by, created_at
UNIQUE(resource_type, resource_id, grantee_type, grantee_id)
```

Sharing = add a row; revoke = delete a row (same ergonomics as `SecretGrant`, no DEK).

### Visibility resolver (the reusable primitive)

`visible_to(principal) -> set[resource_id]`, evaluating for a resource:

- `scope == ORGANIZATION && resource.company_id == principal.company_id`, **OR**
- `scope == GROUP && principal in resource's group`, **OR**
- principal is `owner_id`, **OR**
- a matching `resource_grants` row (`permission >= requested`).

Both skills and agents call this one function — the same query shape secrets already use.
A `company_id`-keyed resolution cache keeps the hot path fast; invalidated on grant/scope
change.

### Registry integration & boot reload

The in-process `SkillRegistry` singleton remains the single home for all definitions
(natural dedup). `SkillManager.initialize()` loads from two sources:

1. **Builtin (code)** — `discover_builtin_skills()` scans `skills.builtin.__path__` (global,
   first-party) — unchanged.
2. **Custom (DB)** — new `load_custom_definitions()` reads active `skill_definitions` rows
   and registers each as a `DeclarativeSkill` (or MCP-backed for hub skills), tagged with
   `company_id` / `scope`.

Source 2 **is the boot-reload fix**: generator / importer / hub write a `skill_definitions`
row and register into the live registry; on restart they re-register from Postgres.

### Enforcement (filter, not per-user registries)

Storage stays single-instance; every principal-facing entry point applies `visible_to`:

- **List** (`SkillsView`, agent tool catalog) → visible skills only.
- **Route/plan** (routing index, capability match) → candidates pre-filtered by visibility.
- **Execute** (`SkillManager.execute_skill`) → **hard authorization gate**: deny if principal
  lacks `use`, regardless of how the skill was addressed.

Trust gates execution independently: a skill visible to you but `sandboxed` still runs
sandboxed. Scope answers "can you see/use it"; trust answers "how does it run."

### Governance & dedup/conflict (absorbs #11141)

- Create/import/hub-install runs through the existing `GovernanceEngine`
  (`FULL_AUTO / SEMI_AUTO / LOCKED`); external ⇒ `sandboxed`.
- Setting/raising scope to company-wide `ORGANIZATION` can require approval under
  `SEMI_AUTO` via the existing `skills:approvals:pending` channel.
- **Reuse-or-fork guard:** creating a name that already exists at a visible scope surfaces
  the existing one (share/limit) instead of silently duplicating.
- **Cross-source conflict resolver (#11141):** same name from builtin + DB + hub resolves
  deterministically (builtin/trusted wins) and records a structured conflict instead of a
  bare "already registered, skipping" warning.

### API & UI surface

- `POST /skills` (create, default ORG scope); `PATCH /skills/{id}/scope` (limit down);
  `POST /skills/{id}/grants` + `DELETE …/grants/{granteeId}` (share/revoke) — all authorized
  by the resolver. Agents reuse the same grant endpoints via `resource_type=agent`.
- `SkillsView.vue`: scope badge (defaults "Company-wide") + "Limit access…" control
  (group/users), i18n across all 11 locales. Company OS agent views get the same affordance.

## Task tree

- **T0 — Boot-reload fix** (prerequisite bug): re-register custom/hub/imported definitions at
  startup so they survive restart. Standalone value.
- **T1 — Shared scope/authz core**: `ScopeLevel`, `resource_grants` + migration,
  `visible_to()` resolver + cache, authz service + unit tests. No behavior change.
- **T2 — Skills adopt scoping**:
  - 2.1 `skill_definitions` table + migration; custom persistence Redis-only → Postgres.
  - 2.2 Registry loads custom defs at boot; generator/importer/hub write DB rows (builds on T0).
  - 2.3 Visibility filter at list/route/execute + execute-time hard gate.
  - 2.4 Reuse-or-fork guard + cross-source conflict resolver (Closes #11141).
  - 2.5 API (create/scope/grant) + `SkillsView` scope badge & "Limit access" (i18n ×11).
  - 2.6 Governance trigger on company-wide scope change.
- **T3 — Custom agents adopt scoping**:
  - 3.1 Agents use `resource_grants` (resource_type=agent) for limiting; ORG default stays
    `agent_org_nodes.company_id`.
  - 3.2 Company OS agent views: "Limit access" affordance + visibility filter on listings.
  - 3.3 Agent capability-KB indexing respects limited scope.
- **T4 — Docs & closure**: update skills/agents docs; verify ACs; file discovery issues.

Each T is one PR-sized deliverable (T2 splits into ~6 sub-PRs).

## Testing strategy

- **Unit:** `visible_to()` truth table across all scopes + grant combinations; conflict
  resolver determinism; reuse-or-fork guard.
- **Integration:** boot re-registration round-trip (create custom skill → restart → still
  registered); execute-time denial for out-of-scope principal; company-wide approval gate
  under SEMI_AUTO.
- **Migration:** `skill_definitions` / `resource_grants` up/down; back-fill existing
  Redis-persisted custom skills into Postgres.
- **Deploy:** verify custom skills persist across a `/opt/autobot` git-pull (data survives,
  not tied to code checkout).

## Risks

- **Registry hot-path cost** of per-principal visibility → mitigated by the `company_id`
  resolution cache.
- **Back-fill** of existing Redis custom skills must be idempotent and dedup by
  `(company_id, name)`.
- **Two identity keyspaces for agents** (`agent_id` string vs `agent_org_nodes.id`, #10032) —
  grants must use a single stable key; standardize before T3.
