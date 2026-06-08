// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeDeduplication Composable
 *
 * Encapsulates all HTTP calls for DeduplicationManager:
 *   - scanDuplicates  — POST /knowledge-maintenance/deduplicate?dry_run=true
 *   - scanOrphans     — GET  /knowledge-maintenance/orphans
 *   - cleanupDuplicates — POST /knowledge-maintenance/deduplicate?dry_run=false
 *   - cleanupOrphans  — DELETE /knowledge-maintenance/orphans?dry_run=false
 *
 * Extracted from DeduplicationManager.vue (#6043).
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

// ==================== Types ====================

export interface DuplicateGroup {
  hash: string
  count: number
  fact_ids: string[]
  category?: string
  title?: string
  total_copies?: number
  removed_count?: number
  kept_fact_id?: string
  kept_created_at?: string
}

export interface DuplicateStats {
  total_facts_scanned: number
  total_duplicates: number
  duplicate_groups_found: number
  duplicates: DuplicateGroup[]
  status?: string
  [key: string]: unknown
}

export interface OrphanedFact {
  fact_id: string
  content?: string
  title?: string
  category?: string
  file_path?: string
}

export interface OrphanStats {
  total_facts_checked: number
  orphaned_count: number
  orphaned_facts: OrphanedFact[]
  status?: string
  [key: string]: unknown
}

interface DeduplicateActionResponse {
  status: string
  deleted_count?: number
  message?: string
  [key: string]: unknown
}

// ==================== Composable ====================

export interface UseKnowledgeDeduplicationReturn {
  duplicateStats: Readonly<Ref<DuplicateStats>>
  orphanStats: Readonly<Ref<OrphanStats>>
  isScanning: Readonly<Ref<boolean>>
  isCleaning: Readonly<Ref<boolean>>
  scanDuplicates: () => Promise<DuplicateStats>
  scanOrphans: () => Promise<OrphanStats>
  cleanupDuplicates: () => Promise<DeduplicateActionResponse>
  cleanupOrphans: () => Promise<DeduplicateActionResponse>
}

const DEFAULT_DUPLICATE_STATS: DuplicateStats = {
  total_facts_scanned: 0,
  total_duplicates: 0,
  duplicate_groups_found: 0,
  duplicates: [],
}

const DEFAULT_ORPHAN_STATS: OrphanStats = {
  total_facts_checked: 0,
  orphaned_count: 0,
  orphaned_facts: [],
}

export function useKnowledgeDeduplication(): UseKnowledgeDeduplicationReturn {
  const duplicateStats = ref<DuplicateStats>({ ...DEFAULT_DUPLICATE_STATS })
  const orphanStats = ref<OrphanStats>({ ...DEFAULT_ORPHAN_STATS })

  const scanState = useLoadingState()
  const cleanState = useLoadingState()

  // Pattern B: POST mutation — dry-run scan for duplicates
  const scanDuplicates = (): Promise<DuplicateStats> =>
    scanState.wrap(async () => {
      const data = await apiClient.post<DuplicateStats>(
        `${getApiBase()}/knowledge-maintenance/deduplicate?dry_run=true`,
      )
      duplicateStats.value = data
      return data
    })

  // Pattern A: GET read — scan for orphaned facts
  const scanOrphans = (): Promise<OrphanStats> =>
    scanState.wrap(async () => {
      const data = await apiClient.get<OrphanStats>(
        `${getApiBase()}/knowledge-maintenance/orphans`,
      )
      orphanStats.value = data
      return data
    })

  // Pattern B: POST mutation — actual deduplication
  const cleanupDuplicates = (): Promise<DeduplicateActionResponse> =>
    cleanState.wrap(() =>
      apiClient.post<DeduplicateActionResponse>(
        `${getApiBase()}/knowledge-maintenance/deduplicate?dry_run=false`,
      ),
    )

  // Pattern B: DELETE mutation — remove orphaned facts
  const cleanupOrphans = (): Promise<DeduplicateActionResponse> =>
    cleanState.wrap(() =>
      apiClient.delete<DeduplicateActionResponse>(
        `${getApiBase()}/knowledge-maintenance/orphans?dry_run=false`,
      ),
    )

  return {
    duplicateStats: readonly(duplicateStats) as Readonly<Ref<DuplicateStats>>,
    orphanStats: readonly(orphanStats) as Readonly<Ref<OrphanStats>>,
    isScanning: readonly(scanState.isLoading),
    isCleaning: readonly(cleanState.isLoading),
    scanDuplicates,
    scanOrphans,
    cleanupDuplicates,
    cleanupOrphans,
  }
}

export default useKnowledgeDeduplication
