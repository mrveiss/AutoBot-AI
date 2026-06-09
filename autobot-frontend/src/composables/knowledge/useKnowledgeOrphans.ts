// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * useKnowledgeOrphans Composable
 *
 * Encapsulates all HTTP calls for SessionOrphanManager and MemoryOrphanManager:
 *   - scanSessionOrphans    — GET    /knowledge-maintenance/session-orphans
 *   - cleanupSessionOrphans — DELETE /knowledge-maintenance/session-orphans?dry_run=false&preserve_important=true
 *   - scanMemoryOrphans     — GET    /memory/entities/orphans
 *   - cleanupMemoryOrphans  — DELETE /memory/entities/orphans?dry_run=false
 *
 * Extracted from SessionOrphanManager.vue (#6047) and MemoryOrphanManager.vue (#6048).
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

// ---- Memory orphan types ----

export interface MemoryOrphanedEntity {
  id: string
  name: string
  session_id: string
  created_at?: string
  observations?: string[]
}

export interface MemoryOrphanScanResult {
  total_conversation_entities: number
  active_sessions: number
  orphaned_count: number
  orphaned_entities: MemoryOrphanedEntity[]
}

export interface MemoryOrphanCleanupResult {
  deleted_count: number
  failed_count: number
  [key: string]: unknown
}

interface MemoryOrphanApiResponse<T> {
  success: boolean
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
  memoryOrphanScanResult: Readonly<Ref<MemoryOrphanScanResult | null>>
  isScanningMemory: Readonly<Ref<boolean>>
  isCleaningMemory: Readonly<Ref<boolean>>
  scanMemoryOrphans: () => Promise<MemoryOrphanScanResult>
  cleanupMemoryOrphans: () => Promise<MemoryOrphanCleanupResult>
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

  // ---- Memory orphan state ----

  const memoryOrphanScanResult = ref<MemoryOrphanScanResult | null>(null)
  const memoryScanState = useLoadingState()
  const memoryCleanupState = useLoadingState()

  // GET /memory/entities/orphans
  const scanMemoryOrphans = (): Promise<MemoryOrphanScanResult> =>
    memoryScanState.wrap(async () => {
      memoryOrphanScanResult.value = null
      const response = await apiClient.rawRequest(
        `${getApiBase()}/memory/entities/orphans`,
        { method: 'GET' },
      )
      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        throw new Error(errorText || `Server error: ${response.status}`)
      }
      const json = (await response.json()) as MemoryOrphanApiResponse<MemoryOrphanScanResult>
      if (!json.success) {
        throw new Error(json.message || 'Failed to scan for orphans')
      }
      memoryOrphanScanResult.value = json.data
      return json.data
    })

  // DELETE /memory/entities/orphans?dry_run=false
  const cleanupMemoryOrphans = (): Promise<MemoryOrphanCleanupResult> =>
    memoryCleanupState.wrap(async () => {
      const response = await apiClient.rawRequest(
        `${getApiBase()}/memory/entities/orphans?dry_run=false`,
        { method: 'DELETE' },
      )
      if (!response.ok) {
        const errorText = await response.text().catch(() => '')
        throw new Error(errorText || `Server error: ${response.status}`)
      }
      const json = (await response.json()) as MemoryOrphanApiResponse<MemoryOrphanCleanupResult>
      if (!json.success) {
        throw new Error(json.message || 'Failed to cleanup orphans')
      }
      memoryOrphanScanResult.value = null
      return json.data
    })

  return {
    orphanScanResult: readonly(orphanScanResult) as Readonly<Ref<OrphanScanResult | null>>,
    isScanning: readonly(scanState.isLoading),
    isCleaningOrphans: readonly(cleanupState.isLoading),
    scanSessionOrphans,
    cleanupSessionOrphans,
    memoryOrphanScanResult: readonly(memoryOrphanScanResult) as Readonly<Ref<MemoryOrphanScanResult | null>>,
    isScanningMemory: readonly(memoryScanState.isLoading),
    isCleaningMemory: readonly(memoryCleanupState.isLoading),
    scanMemoryOrphans,
    cleanupMemoryOrphans,
  }
}

export default useKnowledgeOrphans
