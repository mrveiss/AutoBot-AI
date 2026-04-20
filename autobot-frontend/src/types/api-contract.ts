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

// =============================================================================
// Issue #5248 — Knowledge base stats + categories.
//
// Backend exposes these as `response_model=` Pydantic schemas in
// `autobot-backend/knowledge/schemas/stats.py`, so they appear under
// `components.schemas` in /openapi.json after the next deploy runs the CI
// `npm run gen:types` step. Until `./generated/api.ts` is regenerated, the
// lookups below resolve to `never` at compile-time — the consuming code
// uses the runtime-safe coercion layer in `KnowledgeRepository` so type
// narrowing happens at the repo boundary, not at call sites.
//
// After `./generated/api.ts` regenerates, no code change is needed — these
// aliases automatically pick up the new types.
// =============================================================================

/** `GET /api/knowledge_base/stats/basic` response. */
export type KnowledgeStatsBasic = components['schemas'] extends {
  KnowledgeStatsBasic: infer T
}
  ? T
  : {
      status: string
      total_facts: number
      total_vectors: number
      categories: string[]
    }

/** `GET /api/knowledge_base/detailed_stats` response. */
export type DetailedKnowledgeStats = components['schemas'] extends {
  DetailedKnowledgeStats: infer T
}
  ? T
  : {
      status: string
      basic_stats: Record<string, unknown>
      category_breakdown: Record<string, number>
      source_breakdown: Record<string, number>
      type_breakdown: Record<string, number>
      size_metrics: Record<string, number>
      rag_available: boolean
      message?: string
    }

/** Single row of `GET /api/knowledge_base/categories`. */
export type KnowledgeCategoryEntry = components['schemas'] extends {
  KnowledgeCategoryEntry: infer T
}
  ? T
  : { id: string; name: string; count: number }

/** `GET /api/knowledge_base/categories` response. */
export type KnowledgeCategoriesResponse = components['schemas'] extends {
  KnowledgeCategoriesResponse: infer T
}
  ? T
  : { categories: KnowledgeCategoryEntry[]; total: number }

/** `GET /api/knowledge_base/categories/main` response. */
export type KnowledgeMainCategoriesResponse = components['schemas'] extends {
  KnowledgeMainCategoriesResponse: infer T
}
  ? T
  : {
      categories: Array<{
        id: string
        name: string
        description: string
        icon: string
        color: string
        examples: string[]
        count: number
      }>
      total: number
    }
