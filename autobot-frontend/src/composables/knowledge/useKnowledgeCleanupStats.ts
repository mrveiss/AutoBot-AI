// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeCleanupStats Composable
 *
 * Encapsulates all HTTP calls for CleanupStatistics:
 *   - scanForIssues  — POST /knowledge-maintenance/cleanup (dry_run=true)
 *   - runCleanup     — POST /knowledge-maintenance/cleanup (dry_run=false)
 *
 * Extracted from CleanupStatistics.vue (#6051).
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

// ==================== Types ====================

export interface CleanupOptions {
  removeEmpty: boolean
  removeOrphanedTags: boolean
  fixMetadata: boolean
}

export interface IssuesFound {
  empty_facts: number
  orphaned_tags: number
  malformed_metadata: number
}

export interface ScanResult {
  dry_run: boolean
  issues_found: IssuesFound
}

export interface CleanupResult {
  success?: boolean
  message?: string
  fixes_applied?: {
    empty_removed?: number
    tags_cleaned?: number
    metadata_fixed?: number
  }
  [key: string]: unknown
}

// ==================== Composable ====================

export interface UseKnowledgeCleanupStatsReturn {
  scanResult: Readonly<Ref<ScanResult | null>>
  isScanning: Readonly<Ref<boolean>>
  isCleaning: Readonly<Ref<boolean>>
  scanForIssues: (options: CleanupOptions) => Promise<ScanResult>
  runCleanup: (options: CleanupOptions) => Promise<CleanupResult>
}

export function useKnowledgeCleanupStats(): UseKnowledgeCleanupStatsReturn {
  const scanResult = ref<ScanResult | null>(null)

  const scanState = useLoadingState()
  const cleanState = useLoadingState()

  // Pattern B: POST mutation — dry-run scan for issues
  const scanForIssues = (options: CleanupOptions): Promise<ScanResult> =>
    scanState.wrap(async () => {
      const data = await apiClient.post<CleanupResult>(`${getApiBase()}/knowledge-maintenance/cleanup`, {
        remove_empty: options.removeEmpty,
        remove_orphaned_tags: options.removeOrphanedTags,
        fix_metadata: options.fixMetadata,
        dry_run: true,
      })
      const result: ScanResult = {
        dry_run: true,
        issues_found: (data.issues_found as IssuesFound) ?? {
          empty_facts: 0,
          orphaned_tags: 0,
          malformed_metadata: 0,
        },
      }
      scanResult.value = result
      return result
    })

  // Pattern B: POST mutation — actual cleanup
  const runCleanup = (options: CleanupOptions): Promise<CleanupResult> =>
    cleanState.wrap(async () => {
      const data = await apiClient.post<CleanupResult>(`${getApiBase()}/knowledge-maintenance/cleanup`, {
        remove_empty: options.removeEmpty,
        remove_orphaned_tags: options.removeOrphanedTags,
        fix_metadata: options.fixMetadata,
        dry_run: false,
      })
      scanResult.value = null
      return data
    })

  return {
    scanResult: readonly(scanResult) as Readonly<Ref<ScanResult | null>>,
    isScanning: readonly(scanState.isLoading),
    isCleaning: readonly(cleanState.isLoading),
    scanForIssues,
    runCleanup,
  }
}

export default useKnowledgeCleanupStats
