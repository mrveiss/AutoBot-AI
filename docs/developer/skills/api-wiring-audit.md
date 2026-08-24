---
name: api-wiring-audit
description: Audit and enforce frontend/backend API contract wiring in AutoBot-AI (or any FastAPI + SPA monorepo). Use this skill whenever the user mentions unwired features, dead buttons, 404s from the GUI, API contract drift, endpoints that "don't exist", unmounted routers, frontend/backend mismatch, or before marking ANY frontend feature complete. Also use it when implementing or modifying any frontend API call, any FastAPI route, or any router registration — run the audit as a completion gate, not just when explicitly asked.
---

# API Wiring Audit

Detects and fixes the three classes of frontend/backend contract drift:

1. **Unwired frontend calls** — UI code calling `/api/...` paths that no backend route serves (silent 404s, dead buttons).
2. **Unmounted routers** — FastAPI router modules that exist but are never registered in the router registry / app factory.
3. **Dead backend surface** — routes no frontend consumer uses (optional report).

## The script

`scripts/audit_api_wiring.py` (bundled here; in AutoBot it lives at `scripts/audit_api_wiring.py` in the repo root). Copy it there if missing.

### Authoritative mode (always prefer when backend deps are installed)

```bash
# 1. Dump the real route table by building the app:
python scripts/audit_api_wiring.py --dump-openapi openapi.json
# (or fetch from a running server: --openapi http://localhost:8001/openapi.json)

# 2. Audit, failing the build on any finding:
python scripts/audit_api_wiring.py --openapi openapi.json --fail-on-unwired
```

Exit codes: `0` clean · `1` unwired frontend calls · `2` unmounted routers · `3` both.

### Static mode (no deps; triage only)

```bash
python scripts/audit_api_wiring.py
```

Regex-based with heuristic prefix resolution (`APIRouter(prefix=...)` + `include_router(prefix=...)`). Expect a few false positives from multi-level prefix chains — verify each finding with grep before fixing. Never present static-mode results as definitive.

### Suggestions and baseline health (#12738)

Every unwired finding now prints its closest surviving routes:

```
  /api/browser/navigate
      ?  did you mean /api/browser/mcp/navigate
      <- autobot-frontend/src/composables/useBrowser.ts
```

Suggestions are segment-aware, weighted toward leading-segment agreement (a rename usually changes the last segment) and suppressed below a similarity floor — no suggestion means no confident match, not "no route exists".

With `--baseline`, a `BASELINE HEALTH` section classifies what the baseline is absorbing:

- `REMOVED-ENDPOINT DRIFT` — baselined call with a close surviving route; almost always a rename. **Rewire it; do not leave it baselined** — this is the case where the gate stays green while the button is dead.
- `RESOLVED (prune from baseline)` — now matches a real route; the entry is stale.
- `NO LONGER CALLED (prune from baseline)` — no caller left; residue.

Non-gating by design. Trust these classifications only in authoritative (`--openapi`) mode: static mode's route table combines every registry prefix with every route, so it both invents matches and hides real ones.

### Dead surface report

```bash
python scripts/audit_api_wiring.py --openapi openapi.json --dead-surface
```

## Workflow

1. **Run the audit first**, before reading or changing any code. The output is the task list.
2. **For each unwired frontend call**, decide which side is canonical:
   - Backend route exists under a *different* path (e.g. `budgets` vs `budget`, `approvals/{id}/approve` vs `work-items/{id}/review/approve`) → fix the **frontend** path. Backend is canonical unless the user says otherwise.
   - No backend exists at all → ask the user (or check the issue tracker): implement a minimal backend, or feature-flag/remove the UI. **Never leave a dead button shipped.**
3. **For each unmounted router**: if anything in `autobot-frontend/src` consumes its paths, mount it in `initialization/router_registry/`. If nothing consumes it and git history shows it stale, propose deletion — don't silently delete.
4. **Re-run with `--fail-on-unwired` until exit code 0.** One commit per logical fix.
5. **Regenerate frontend types** after any backend route change:
   ```bash
   cd autobot-frontend && npm run gen:types
   ```

## Rules (apply even when the skill wasn't explicitly invoked)

- Never write a frontend API call against a path absent from `openapi.json`. If the endpoint doesn't exist yet, implement the backend route first, dump the spec, then write the frontend call.
- Frontend components must derive request/response types from `src/types/generated/api.ts`, not hand-typed strings/interfaces. If the generated file lacks the endpoint, that *is* the wiring check failing — fix the backend or regenerate, don't hand-type around it.
- Before declaring any frontend feature complete, run the authoritative audit and resolve all findings touching the files you changed.
- When adding a new FastAPI router module, register it in the router registry in the same commit. A router file with no registration is a defect, not a draft.

## Adapting to other repos

The script assumes AutoBot's layout (`autobot-backend/`, `autobot-frontend/src/`, `app_factory.create_app()`). For other FastAPI + SPA monorepos, edit the `BACKEND`, `FRONTEND_SRC`, and `dump_openapi()` constants at the top of the script — everything else is layout-agnostic.
