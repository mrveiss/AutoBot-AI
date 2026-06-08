// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * useKnowledgeBase Composable (backward-compat shim)
 *
 * The 807-line god-composable was split into domain-focused composables
 * under `./knowledge/*` (#5122). This file re-exports everything from the
 * new composables so existing consumers continue to work unchanged.
 *
 * Dead try/catch/log/rethrow wrappers around ApiClient calls were also
 * removed during the split (#5123) — ApiClient already logs every retry
 * and final failure, and it never returns null, so the wrappers only
 * double-logged the same error.
 *
 * Migration path: consumers should import the focused composable directly
 * (e.g. `import { useKnowledgeStats } from '@/composables/knowledge/useKnowledgeStats'`)
 * and this aggregator can be deleted once no callers remain.
 */

import {
  formatDate as formatDateHelper,
  formatFileSize as formatFileSizeHelper,
  formatCategoryName as formatCategoryHelper,
} from '@/utils/formatHelpers'

import { useKnowledgeStats } from './knowledge/useKnowledgeStats'
import { useKnowledgeCategories } from './knowledge/useKnowledgeCategories'
import { useKnowledgeFacts } from './knowledge/useKnowledgeFacts'
import { useKnowledgeFiles } from './knowledge/useKnowledgeFiles'
import { useMachineKnowledge } from './knowledge/useMachineKnowledge'
import { useManPages } from './knowledge/useManPages'
import { useKnowledgeJobs } from './knowledge/useKnowledgeJobs'
import { useKnowledgeIcons } from './knowledge/useKnowledgeIcons'

// ==================== Re-exports ====================

export { useKnowledgeStats } from './knowledge/useKnowledgeStats'
export { useKnowledgeCategories } from './knowledge/useKnowledgeCategories'
export { useKnowledgeFacts } from './knowledge/useKnowledgeFacts'
export type { AdvancedSearchOptions } from './knowledge/useKnowledgeFacts'
export { useKnowledgeFiles } from './knowledge/useKnowledgeFiles'
export { useMachineKnowledge } from './knowledge/useMachineKnowledge'
export type { MachineProfile } from './knowledge/useMachineKnowledge'
export { useManPages } from './knowledge/useManPages'
export type { ManPagesSummary } from './knowledge/useManPages'
export { useKnowledgeJobs } from './knowledge/useKnowledgeJobs'
export { useKnowledgeIcons } from './knowledge/useKnowledgeIcons'

// Public state types that lived in this module — preserved for consumers
// that still import them from `@/composables/useKnowledgeBase`.
export interface ProgressState {
  currentTask: string
  taskDetail: string
  overallProgress: number
  taskProgress: number
  status: 'waiting' | 'running' | 'success' | 'error'
  messages: ProgressMessage[]
}

export interface ProgressMessage {
  text: string
  type: 'info' | 'success' | 'warning' | 'error'
  timestamp: number
}

/**
 * @deprecated Use domain-specific composables from './knowledge/*' instead.
 * This aggregator is kept for backward compatibility until all consumers
 * migrate to importing only what they need.
 */
export function useKnowledgeBase() {
  const stats = useKnowledgeStats()
  const categories = useKnowledgeCategories()
  const facts = useKnowledgeFacts()
  const files = useKnowledgeFiles()
  const machine = useMachineKnowledge()
  const manPages = useManPages()
  const jobs = useKnowledgeJobs()
  const icons = useKnowledgeIcons()

  return {
    // Stats
    fetchStats: stats.fetchStats,
    fetchBasicStats: stats.fetchBasicStats,
    // Categories
    fetchCategories: categories.fetchCategories,
    fetchCategory: categories.fetchCategory,
    getCategorizedFacts: categories.getCategorizedFacts,
    buildCategoryFilterOptions: categories.buildCategoryFilterOptions,
    // Facts / search
    searchKnowledge: facts.searchKnowledge,
    advancedSearch: facts.advancedSearch,
    addFact: facts.addFact,
    // Files
    uploadKnowledgeFile: files.uploadKnowledgeFile,
    // Machine
    fetchMachineProfiles: machine.fetchMachineProfiles,
    fetchMachineProfile: machine.fetchMachineProfile,
    initializeMachineKnowledge: machine.initializeMachineKnowledge,
    refreshSystemKnowledge: machine.refreshSystemKnowledge,
    // Man pages
    fetchManPagesSummary: manPages.fetchManPagesSummary,
    integrateManPages: manPages.integrateManPages,
    populateManPages: manPages.populateManPages,
    populateAutoBotDocs: manPages.populateAutoBotDocs,
    // Jobs / vectorization
    getVectorizationStatus: jobs.getVectorizationStatus,
    vectorizeFacts: jobs.vectorizeFacts,
    pollJobStatus: jobs.pollJobStatus,
    // Icons + formatting
    getCategoryIcon: icons.getCategoryIcon,
    getTypeIcon: icons.getTypeIcon,
    getFileIcon: icons.getFileIcon,
    getOSBadgeClass: icons.getOSBadgeClass,
    getMessageIcon: icons.getMessageIcon,
    formatTime: icons.formatTime,
    // Formatting helpers (using shared utilities)
    formatDate: formatDateHelper,
    formatCategory: formatCategoryHelper,
    formatCategoryName: formatCategoryHelper, // Alias for backward compatibility
    formatFileSize: formatFileSizeHelper,
    formatDateOnly: formatDateHelper, // Alias for backward compatibility
  }
}

