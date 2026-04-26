// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * useKnowledgeOrphans Composable
 *
 * Encapsulates all HTTP calls for SessionOrphanManager:
 *   - scanSessionOrphans   — GET  /knowledge-maintenance/session-orphans
 *   - cleanupSessionOrphans — DELETE /knowledge-maintenance/session-orphans?dry_run=false&preserve_important=true
 *
 * Extracted from SessionOrphanManager.vue (#6047).
 */

import { ref, readonly, type Ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useLoadingState } from '@/composables/useLoadingState'

// ==================== Types ====================

export interface OrphanedFact {
  fact_id: string
  session_id: string
  category: string
  content_preview: string
  important: boolean
}

export interface OrphanScanResult {
  total_facts_checked: number
  facts_with_session_tracking: number
  orphaned_count: number
  orphaned_sessions: number
  session_breakdown: Record<string, number>
  orphaned_facts: OrphanedFact[]
}

export interface OrphanCleanupResult {
  facts_removed: number
  facts_preserved: number
  [key: string]: unknown
}

interface OrphanApiResponse<T> {
  status: string
  message?: string
  data: T
}

// ==================== Composable ====================

export interface UseKnowledgeOrphansReturn {
  orphanScanResult: Readonly<Ref<OrphanScanResult | null>>
  isScanning: Readonly<Ref<boolean>>
  isCleaningOrphans: Readonly<Ref<boolean>>
  scanSessionOrphans: () => Promise<OrphanScanResult>
  cleanupSessionOrphans: () => Promise<OrphanCleanupResult>
}

export function useKnowledgeOrphans(): UseKnowledgeOrphansReturn {
  const orphanScanResult = ref<OrphanScanResult | null>(null)

  const scanState = useLoadingState()
  const cleanupState = useLoadingState()

  // GET /knowledge-maintenance/session-orphans
  const scanSessionOrphans = (): Promise<OrphanScanResult> =>
    scanState.wrap(async () => {
      orphanScanResult.value = null
      const response = await apiClient.rawRequest(
        `${getApiBase()}/knowledge-maintenance/session-orphans`,
        { method: 'GET' },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || `Server error: ${response.status}`)
      }
      const json = (await response.json()) as OrphanApiResponse<OrphanScanResult>
      if (json.status !== 'success') {
        throw new Error(json.message || 'Failed to scan for orphans')
      }
      orphanScanResult.value = json.data
      return json.data
    })

  // DELETE /knowledge-maintenance/session-orphans?dry_run=false&preserve_important=true
  const cleanupSessionOrphans = (): Promise<OrphanCleanupResult> =>
    cleanupState.wrap(async () => {
      const response = await apiClient.rawRequest(
        `${getApiBase()}/knowledge-maintenance/session-orphans?dry_run=false&preserve_important=true`,
        { method: 'DELETE' },
      )
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(errorText || `Server error: ${response.status}`)
      }
      const json = (await response.json()) as OrphanApiResponse<OrphanCleanupResult>
      if (json.status !== 'success') {
        throw new Error(json.message || 'Failed to cleanup orphans')
      }
      orphanScanResult.value = null
      return json.data
    })

  return {
    orphanScanResult: readonly(orphanScanResult) as Readonly<Ref<OrphanScanResult | null>>,
    isScanning: readonly(scanState.isLoading),
    isCleaningOrphans: readonly(cleanupState.isLoading),
    scanSessionOrphans,
    cleanupSessionOrphans,
  }
}

export default useKnowledgeOrphans
