/**
 * API Contract Types (Issue #5209)
 *
 * SINGLE SOURCE OF TRUTH for API-contract types shared between backend and frontend.
 *
 * This module re-exports auto-generated OpenAPI types with ergonomic aliases.
 * The generated file `./generated/api.ts` is produced by `npm run gen:types` from
 * the backend's live `/openapi.json` — never hand-edit it.
 *
 * HOW TO EXTEND:
 *   1. Add an alias below for a schema that exists in `components['schemas']`.
 *   2. Migrate hand-written duplicate in `./knowledgeBase.ts` (or similar) to
 *      import from `@/types/api-contract` instead.
 *   3. Delete the hand-written interface only once all call sites compile.
 *
 * WHY: Hand-maintained duplicates between Python models and TS interfaces drift
 * silently — see #5200 for a live production bug caused by this drift class.
 *
 * @see docs/developer/frontend-type-generation.md
 * @author mrveiss
 * @copyright (c) 2025 mrveiss
 */
import type { components } from './generated/api'

/** Request body for `POST /connectors` — creating a new connector. */
export type CreateConnectorRequest = components['schemas']['CreateConnectorRequest']

/** Request body for `PATCH /connectors/{id}` — partial connector update. */
export type UpdateConnectorRequest = components['schemas']['UpdateConnectorRequest']
