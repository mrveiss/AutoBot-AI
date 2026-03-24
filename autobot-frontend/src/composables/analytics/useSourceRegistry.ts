// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Composable: useSourceRegistry
 *
 * Encapsulates code source registry state and operations:
 * source listing, selection, editing, sharing, and knowledge base opt-in.
 *
 * Issues #1133, #1710, #2228, #2230: Extracted from CodebaseAnalytics.vue
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useSourceRegistry')

// Issue #1133: CodeSource type
export interface CodeSource {
  id: string
  name: string
  source_type: 'github' | 'local'
  repo: string | null
  branch: string
  credential_id: string | null
  clone_path: string | null
  last_synced: string | null
  status: 'configured' | 'syncing' | 'ready' | 'error'
  error_message: string | null
  owner_id: string | null
  access: 'private' | 'shared' | 'public'
  shared_with: string[]
  created_at: string
}

export interface UseSourceRegistryDeps {
  t: (key: string, params?: Record<string, unknown>) => string
  showToast: (msg: string, type?: string, duration?: number) => void
  notify: (msg: string, type?: string) => void
}

export const STORAGE_KEY_PATH = 'codebase-analytics-path'

export function useSourceRegistry(deps: UseSourceRegistryDeps) {
  const { t, notify } = deps
  const route = useRoute()

  // Load path from localStorage if available, otherwise use default
  const savedPath = localStorage.getItem(STORAGE_KEY_PATH)
  const rootPath = ref(savedPath || '/opt/autobot')

  // Issue #1133: Source registry state
  const sources = ref<CodeSource[]>([])
  const selectedSource = ref<CodeSource | null>(null)
  const showSourceManager = ref(false)
  const showAddSourceModal = ref(false)
  const showShareSourceModal = ref(false)
  const editTargetSource = ref<CodeSource | null>(null)
  const shareTargetSource = ref<CodeSource | null>(null)
  const showKnowledgeBaseOptIn = ref(false)
  const knowledgeBaseAdding = ref(false)

  // Issue #1710: source_id query param for per-project API calls
  const sourceIdParam = computed(() => {
    const sid =
      selectedSource.value?.id || (route.params.sourceId as string)
    return sid ? `source_id=${encodeURIComponent(sid)}` : ''
  })

  /** Append ?source_id= to a URL when a source is selected (#1710). */
  function withSourceId(url: string): string {
    if (!sourceIdParam.value) return url
    const sep = url.includes('?') ? '&' : '?'
    return `${url}${sep}${sourceIdParam.value}`
  }

  /** Return source_id as query record for useAnalyticsFetch calls (#1772). */
  const sourceIdQuery = computed(
    (): Record<string, string> => {
      const sid =
        selectedSource.value?.id || (route.params.sourceId as string)
      return sid ? { source_id: sid } : {}
    },
  )

  // Issue #1133: Source registry functions
  async function loadSources() {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        `${backendUrl}/api/analytics/codebase/sources`,
      )
      if (!response.ok) return
      const data = await response.json()
      sources.value = data.sources ?? []
    } catch (err: unknown) {
      logger.warn(
        'Failed to load sources:',
        err instanceof Error ? err.message : String(err),
      )
    }
  }

  function handleSelectSource(source: CodeSource) {
    selectedSource.value = source
    if (source.clone_path) {
      rootPath.value = source.clone_path
      localStorage.setItem(STORAGE_KEY_PATH, source.clone_path)
    }
    showSourceManager.value = false
    notify(
      t('analytics.codebase.notify.selectedSource', { name: source.name }),
      'info',
    )
  }

  function handleClearSource() {
    selectedSource.value = null
  }

  async function handleSourceSaved(source: CodeSource) {
    showAddSourceModal.value = false
    editTargetSource.value = null
    await loadSources()
    notify(
      t('analytics.codebase.notify.sourceSaved', { name: source.name }),
      'success',
    )
  }

  async function handleShareSaved(source: CodeSource) {
    showShareSourceModal.value = false
    shareTargetSource.value = null
    await loadSources()
    notify(
      t('analytics.codebase.notify.accessUpdated', { name: source.name }),
      'success',
    )
  }

  function handleEditSource(source: CodeSource) {
    editTargetSource.value = source
    showAddSourceModal.value = true
    showSourceManager.value = false
  }

  function handleShareSource(source: CodeSource) {
    shareTargetSource.value = source
    showShareSourceModal.value = true
  }

  async function addToKnowledgeBase() {
    if (!rootPath.value) return
    knowledgeBaseAdding.value = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(
        `${backendUrl}/api/analytics/codebase/index`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ root_path: rootPath.value }),
        },
      )
      if (!response.ok) {
        const text = await response.text()
        throw new Error(`HTTP ${response.status}: ${text}`)
      }
      showKnowledgeBaseOptIn.value = false
      notify(
        t('analytics.codebase.notify.knowledgeBaseAdded'),
        'success',
      )
    } catch (err: unknown) {
      logger.error(
        'Failed to add to knowledge base:',
        err instanceof Error ? err.message : String(err),
      )
      notify(
        t('analytics.codebase.notify.knowledgeBaseFailed'),
        'error',
      )
    } finally {
      knowledgeBaseAdding.value = false
    }
  }

  return {
    // State
    rootPath,
    sources,
    selectedSource,
    showSourceManager,
    showAddSourceModal,
    showShareSourceModal,
    editTargetSource,
    shareTargetSource,
    showKnowledgeBaseOptIn,
    knowledgeBaseAdding,
    // Computed
    sourceIdParam,
    sourceIdQuery,
    // Functions
    withSourceId,
    loadSources,
    handleSelectSource,
    handleClearSource,
    handleSourceSaved,
    handleShareSaved,
    handleEditSource,
    handleShareSource,
    addToKnowledgeBase,
    // Constants
    STORAGE_KEY_PATH,
  }
}
