// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0

/**
 * The one definition of "needs vectorizing" (#22332, #18244).
 *
 * `pending` means NOT YET vectorized, so it is vectorizable; every unknown document is `pending`.
 * Only `vectorized` is done. `failed` stays vectorizable (a retry). Every vectorization toolbar,
 * badge count and action button reads this and none re-derives it.
 */
import type { VectorizationStatus } from '@/composables/useKnowledgeVectorization'

export function isVectorizable(status: VectorizationStatus | undefined): boolean {
  return status !== 'vectorized'
}

/** Ids from `ids` whose recorded state still needs vectorizing (no recorded state counts). */
export function vectorizableIds(
  ids: Iterable<string>,
  states: ReadonlyMap<string, { status: VectorizationStatus }>,
): string[] {
  return Array.from(ids).filter((id) => isVectorizable(states.get(id)?.status))
}
