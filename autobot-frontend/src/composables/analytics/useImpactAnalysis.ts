// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Impact analysis — "what breaks if I change this" (#13506).
 *
 * Wraps `GET /api/analytics/codebase/impact`, which walks the code graph
 * backwards from a node and reports what transitively calls it.
 *
 * The engine (#13471) was built so a truncated walk cannot pass for a complete
 * one — that is the defect #13468 was filed to remove. The response therefore
 * carries `depth_capped` with its un-expanded frontier, the skipped edges with
 * reasons, and both edge counts. This composable keeps all of it: `isPartial`
 * exists so the UI has a single, hard-to-ignore signal, and no confidence score
 * is derived from the counts (#13482 Q2 bound that).
 */

import { computed, ref } from 'vue'

import { getApiBase } from '@/config/ssot-config'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useImpactAnalysis')

export interface ImpactEdge {
  [key: string]: unknown
}

export interface ImpactResponse {
  indexed: boolean
  root_id?: string
  seed_ids?: string[]
  reached?: string[]
  edges?: ImpactEdge[]
  depth_capped?: boolean
  depth_capped_frontier?: string[]
  skipped_edges?: ImpactEdge[]
  resolved_edge_count?: number
  unresolved_edge_count?: number
  max_depth?: number
  depth_reached?: number
  message?: string
}

export function useImpactAnalysis() {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const result = ref<ImpactResponse | null>(null)

  /** True when the graph has never been built — distinct from "node not found". */
  const notIndexed = computed(() => result.value !== null && result.value.indexed === false)

  /**
   * True when the answer is a lower bound rather than the whole picture.
   *
   * Either the walk hit its depth limit, or edges existed that could not be
   * resolved. Both mean "there may be more callers than shown", and the panel
   * must say so — a partial list rendered as complete is worse than no list,
   * because it reads as evidence that nothing else is affected.
   */
  const isPartial = computed(() => {
    const r = result.value
    if (!r || r.indexed === false) return false
    return Boolean(r.depth_capped) || (r.unresolved_edge_count ?? 0) > 0
  })

  const callerCount = computed(() => result.value?.reached?.length ?? 0)

  async function analyze(nodeId: string, maxDepth?: number): Promise<void> {
    const id = nodeId.trim()
    if (!id) {
      error.value = 'A node id is required.'
      return
    }

    loading.value = true
    error.value = null
    result.value = null

    try {
      const params = new URLSearchParams({ node_id: id })
      if (maxDepth !== undefined) params.set('max_depth', String(maxDepth))
      result.value = await apiClient.get<ImpactResponse>(
        `${getApiBase()}/analytics/codebase/impact?${params.toString()}`,
      )
      logger.info(
        'Impact walk for %s: %d reached%s',
        id,
        result.value?.reached?.length ?? 0,
        result.value?.depth_capped ? ' (depth-capped)' : '',
      )
    } catch (err) {
      error.value = 'Impact analysis failed. Please try again.'
      logger.error('Impact analysis failed:', err)
    } finally {
      loading.value = false
    }
  }

  function reset(): void {
    result.value = null
    error.value = null
  }

  return { loading, error, result, notIndexed, isPartial, callerCount, analyze, reset }
}
