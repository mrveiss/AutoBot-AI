/**
 * Document Lifecycle Change Tracking Composable
 *
 * Provides real-time tracking of document changes (added, updated, removed)
 * for knowledge base documents across different hosts/OS.
 *
 * Features:
 * - Automatic change detection via polling or WebSocket
 * - Per-host change tracking
 * - Change notifications with toast alerts
 * - Change history and statistics
 */

import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useDocumentChanges
const logger = createLogger('useDocumentChanges')

export interface DocumentChange {
  document_id: string
  command?: string
  title: string
  change_type: 'added' | 'updated' | 'removed'
  timestamp: Date
  content_size?: number
  old_hash?: string
  new_hash?: string
}

export interface ChangeSummary {
  added: number
  updated: number
  removed: number
  unchanged: number
}

export interface VectorizationResult {
  attempted: number
  successful: number
  failed: number
  skipped: number
  details: Array<{
    doc_id: string
    command: string
    status: 'success' | 'failed' | 'skipped' | 'error'
    fact_id?: string
    reason?: string
  }>
}

export interface ChangeDetectionResult {
  status: string
  machine_id: string
  scan_type: string
  total_scanned: number
  changes: {
    added: DocumentChange[]
    updated: DocumentChange[]
    removed: DocumentChange[]
    unchanged: number
  }
  summary: ChangeSummary
  vectorization?: VectorizationResult
}

const STORAGE_KEY = 'autobot-document-changes'

interface PersistedState {
  recentChanges: Array<DocumentChange & { timestamp: string }>
  changeSummary: ChangeSummary
  lastScanTime: string | null
  lastVectorizationResult: VectorizationResult | null
  machineId: string
}

function loadPersistedState(): Partial<PersistedState> | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function persistState(state: PersistedState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch {
    // localStorage full or unavailable — ignore
  }
}

export function useDocumentChanges() {
  const { t } = useI18n()

  // Restore persisted state
  const persisted = loadPersistedState()

  // State
  const recentChanges = ref<DocumentChange[]>(
    persisted?.recentChanges?.map(c => ({
      ...c,
      timestamp: new Date(c.timestamp)
    })) ?? []
  )
  const changeSummary = ref<ChangeSummary>(
    persisted?.changeSummary ?? {
      added: 0,
      updated: 0,
      removed: 0,
      unchanged: 0
    }
  )
  const isScanning = ref(false)
  const lastScanTime = ref<Date | null>(
    persisted?.lastScanTime ? new Date(persisted.lastScanTime) : null
  )
  const machineId = ref<string>(persisted?.machineId ?? 'default-host')
  const autoRefreshInterval = ref<number | null>(null)
  const lastVectorizationResult = ref<VectorizationResult | null>(
    persisted?.lastVectorizationResult ?? null
  )

  /** Save current state to localStorage */
  const saveState = () => {
    persistState({
      recentChanges: recentChanges.value.map(c => ({
        ...c,
        timestamp: c.timestamp.toISOString()
      })) as PersistedState['recentChanges'],
      changeSummary: changeSummary.value,
      lastScanTime: lastScanTime.value?.toISOString() ?? null,
      lastVectorizationResult: lastVectorizationResult.value,
      machineId: machineId.value
    })
  }

  // Computed
  const totalChanges = computed(() => {
    return changeSummary.value.added +
           changeSummary.value.updated +
           changeSummary.value.removed
  })

  const hasChanges = computed(() => totalChanges.value > 0)

  const changesByType = computed(() => {
    const grouped: Record<string, DocumentChange[]> = {
      added: [],
      updated: [],
      removed: []
    }

    recentChanges.value.forEach(change => {
      if (grouped[change.change_type]) {
        grouped[change.change_type].push(change)
      }
    })

    return grouped
  })

  /**
   * Scan for document changes on the current host
   * @param force Force a full scan (ignore cache)
   * @param autoVectorize Automatically vectorize detected changes for RAG queries
   */
  const scanForChanges = async (force = false, autoVectorize = false): Promise<ChangeDetectionResult | null> => {
    if (isScanning.value) {
      logger.warn('Scan already in progress')
      return null
    }

    isScanning.value = true

    try {
      // Issue #552: Fixed path - backend uses /api/knowledge-maintenance/*
      const response = await ApiClient.post('/api/knowledge-maintenance/scan_host_changes', {
        machine_id: machineId.value,
        force,
        scan_type: 'manpages',
        auto_vectorize: autoVectorize
      })

      const result: ChangeDetectionResult = await response.json()

      if (result.status === 'success') {
        // Update summary
        changeSummary.value = result.summary

        // Store vectorization results if present
        if (result.vectorization) {
          lastVectorizationResult.value = result.vectorization
          logger.info('Vectorization completed:', result.vectorization)
        }

        // Merge new changes into recent changes
        const newChanges: DocumentChange[] = [
          ...result.changes.added.map(c => ({ ...c, change_type: 'added' as const, timestamp: new Date() })),
          ...result.changes.updated.map(c => ({ ...c, change_type: 'updated' as const, timestamp: new Date() })),
          ...result.changes.removed.map(c => ({ ...c, change_type: 'removed' as const, timestamp: new Date() }))
        ]

        // Add to recent changes (keep last 50)
        recentChanges.value = [...newChanges, ...recentChanges.value].slice(0, 50)

        lastScanTime.value = new Date()
        saveState()

        return result
      }

      return null
    } catch (error) {
      logger.error('Failed to scan for changes:', error)
      return null
    } finally {
      isScanning.value = false
    }
  }

  /**
   * Get change icon based on change type
   */
  const getChangeIcon = (changeType: string): string => {
    switch (changeType) {
      case 'added':
        return 'fas fa-plus-circle text-green-500'
      case 'updated':
        return 'fas fa-sync-alt text-blue-500'
      case 'removed':
        return 'fas fa-minus-circle text-red-500'
      default:
        return 'fas fa-info-circle text-gray-500'
    }
  }

  /**
   * Get change type display name (i18n)
   */
  const getChangeTypeName = (changeType: string): string => {
    switch (changeType) {
      case 'added':
        return t('knowledge.changeFeed.changeTypeAdded')
      case 'updated':
        return t('knowledge.changeFeed.changeTypeUpdated')
      case 'removed':
        return t('knowledge.changeFeed.changeTypeRemoved')
      default:
        return t('knowledge.changeFeed.changeTypeChanged')
    }
  }

  /**
   * Format timestamp relative to now (i18n)
   */
  const formatRelativeTime = (timestamp: Date): string => {
    const now = new Date()
    const diffMs = now.getTime() - timestamp.getTime()
    const diffSec = Math.floor(diffMs / 1000)
    const diffMin = Math.floor(diffSec / 60)
    const diffHour = Math.floor(diffMin / 60)
    const diffDay = Math.floor(diffHour / 24)

    if (diffSec < 60) return t('knowledge.changeFeed.timeJustNow')
    if (diffMin < 60) return t('knowledge.changeFeed.timeMinutesAgo', { count: diffMin })
    if (diffHour < 24) return t('knowledge.changeFeed.timeHoursAgo', { count: diffHour })
    return t('knowledge.changeFeed.timeDaysAgo', { count: diffDay })
  }

  /**
   * Clear all tracked changes
   */
  const clearChanges = () => {
    recentChanges.value = []
    changeSummary.value = {
      added: 0,
      updated: 0,
      removed: 0,
      unchanged: 0
    }
    lastVectorizationResult.value = null
    saveState()
  }

  /**
   * Start auto-refresh polling
   */
  const startAutoRefresh = (intervalMinutes = 30) => {
    stopAutoRefresh() // Clear any existing interval

    autoRefreshInterval.value = window.setInterval(() => {
      scanForChanges(false)
    }, intervalMinutes * 60 * 1000)
  }

  /**
   * Stop auto-refresh polling
   */
  const stopAutoRefresh = () => {
    if (autoRefreshInterval.value !== null) {
      clearInterval(autoRefreshInterval.value)
      autoRefreshInterval.value = null
    }
  }

  /**
   * Set machine ID for scanning
   */
  const setMachineId = (id: string) => {
    machineId.value = id
    saveState()
  }

  /**
   * Get changes for a specific document
   */
  const getDocumentChanges = (documentId: string): DocumentChange[] => {
    return recentChanges.value.filter(change => change.document_id === documentId)
  }

  /**
   * Export changes to JSON
   */
  const exportChanges = (): string => {
    return JSON.stringify({
      machine_id: machineId.value,
      last_scan: lastScanTime.value,
      summary: changeSummary.value,
      changes: recentChanges.value
    }, null, 2)
  }

  // Lifecycle
  onUnmounted(() => {
    stopAutoRefresh()
  })

  return {
    // State
    recentChanges,
    changeSummary,
    isScanning,
    lastScanTime,
    machineId,
    lastVectorizationResult,

    // Computed
    totalChanges,
    hasChanges,
    changesByType,

    // Methods
    scanForChanges,
    getChangeIcon,
    getChangeTypeName,
    formatRelativeTime,
    clearChanges,
    startAutoRefresh,
    stopAutoRefresh,
    setMachineId,
    getDocumentChanges,
    exportChanges
  }
}
