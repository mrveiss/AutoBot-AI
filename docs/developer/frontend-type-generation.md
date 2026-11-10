# Frontend Type Generation from Backend OpenAPI

**Status:** Active (Issue #5209)
**Owner:** mrveiss

## Why

Core API-contract types (`ConnectorConfig`, `ConnectorStatus`, `KnowledgeStats`,
and many others) were previously declared **twice**:

- Once in Python (Pydantic models / dataclasses) under `autobot-backend/`
- Once in TypeScript (hand-written interfaces) under `autobot-frontend/src/types/`

When the backend added, renamed, or removed a field, the frontend silently kept
the old shape until a runtime bug surfaced. **Issue #5200** is a concrete
example — the connector response shape diverged from the declared frontend
interface and shipped to production.

This document describes the single-source-of-truth pipeline that eliminates
drift: FastAPI emits `/openapi.json` at runtime, and `openapi-typescript`
consumes it to produce TypeScript types that the frontend imports directly.

## Pipeline

```
FastAPI app
    │
    ▼
/openapi.json  ◀──  ground truth (Pydantic schemas)
    │
    ▼
openapi-typescript
    │
    ▼
autobot-frontend/src/types/generated/api.ts  ◀──  auto-generated, committed
    │
    ▼
autobot-frontend/src/types/api-contract.ts   ◀──  hand-written ergonomic aliases
    │
    ▼
application code (repositories, components, composables)
```

**Two layers, on purpose:**

- `generated/api.ts` is a verbatim dump of the OpenAPI schema. It's committed
  so CI can diff against it (see "CI enforcement" below) but is never
  hand-edited.
- `api-contract.ts` is the ergonomic re-export layer. It picks specific
  schemas from `components['schemas']['…']` and re-exports them under friendly
  names. This is the file application code imports from.

## How to run locally

**No running server is needed (#12363).** The schema is dumped offline from the backend's own app factory,
exactly as the `verify-generated-types` CI job does, then fed to `openapi-typescript`:

```bash
cd autobot-frontend
npm run gen:types           # runs gen:types:openapi first (a fresh schema, never a stale or missing openapi.json), then:
                            #   python3 ../scripts/audit_api_wiring.py --dump-openapi openapi.json --no-websocket-paths
                            #   openapi-typescript openapi.json -o src/types/generated/api.ts --additional-properties
```

`--no-websocket-paths` omits the audit-only `x-websocket-paths` key, so `openapi.json` is exactly the schema a
live server serves. `scripts/audit_api_wiring.py` is the one dumper (the SLM app has its own,
`autobot-slm-backend/scripts/dump_openapi.py`); there is no second one, and CI no longer carries an inline
python step. The backend must import in the environment you run it in (the repo's Python test environment
does). `openapi.json` is git-ignored for the main app: regenerate, never commit it.

This overwrites `src/types/generated/api.ts` in place. Commit the result
together with the backend change that motivated regeneration.

The generated `paths` interface is also what types `apiClient.call(...)`: the app's client binds it with
`import type { paths } from '@/types/generated/api'` (type-only, never in the bundle), so a changed route
shows up as a compile error at its callers (see `FRONTEND_API_CLIENTS.md`).

## CI enforcement

The `verify:types` script performs `git diff --exit-code` against
`src/types/generated/api.ts`. If the committed file drifts from what the
backend would produce, CI fails.

See `.github/workflows/_gate-frontend-test.yml` for the wired step. The contract is:

> **If CI says "generated types are out of date", run `npm run gen:types`, commit
> the diff, and push.**

This guarantees the repo always reflects the backend's real schema at HEAD.

## How to extend

When you want to consume a new backend type in the frontend:

1. Confirm the type exists in the generated file:
   ```bash
   grep 'MyNewType:' autobot-frontend/src/types/generated/api.ts
   ```
   (If it doesn't, the backend model probably isn't wired into any route's
   `response_model=` / `Body(...)` — fix the backend first.)

2. Add an ergonomic alias in `autobot-frontend/src/types/api-contract.ts`:
   ```ts
   export type MyNewType = components['schemas']['MyNewType']
   ```

3. Import it from application code:
   ```ts
   import type { MyNewType } from '@/types/api-contract'
   ```

4. If this replaces a hand-written duplicate (e.g. in
   `src/types/knowledgeBase.ts`), delete the duplicate only once all call
   sites compile with the generated type.

## What this replaces

- **Manual copying** of Python field names into TypeScript interfaces.
- **Stale comments** like `// sync manually with backend/models.py`.
- **Defensive casts** of the form `response.data as SomeLocalInterface` (the
  frontend now has the backend's actual schema, so narrow types come for free).

## What this does NOT replace (yet)

- **Dataclass models** that aren't exposed through a FastAPI route don't
  appear in `/openapi.json`. If the frontend needs them, either expose them
  via a route (preferred) or keep a hand-written type (annotate with a
  reference to the backend file).
- **Frontend-only types** (UI state, component props, route meta) stay
  hand-written — they have no backend counterpart.

## Migration plan

Issue #5209 is deliberately scoped to wiring up the pipeline plus one working
example (`CreateConnectorRequest`, `UpdateConnectorRequest`). Full migration
of all API-contract types happens in follow-up PRs:

- Expand `api-contract.ts` alias list as call sites are migrated.
- Delete hand-written duplicates in `src/types/knowledgeBase.ts` and peers
  after all callers compile with generated types.
- Track progress under the `tech-debt` label.
