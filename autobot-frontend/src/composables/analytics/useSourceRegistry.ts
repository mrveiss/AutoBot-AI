// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Composable: useSourceRegistry
 *
 * Encapsulates code source registry state and operations:
 * source listing, selection, editing, sharing, and knowledge base opt-in.
 *
 * Issues #1133, #1710, #2228, #2230: Extracted from CodebaseAnalytics.vue
 */

import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useSourcesListEndpoint } from '@/composables/analytics/useSourcesListEndpoint'
import apiClient from '@/utils/ApiClient'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type { ToastType } from '@/composables/useToast'

const logger = createLogger('useSourceRegistry')

// Issue #1133 / #2238: CodeSource type extracted to shared types
import type { CodeSource } from '@/types/analytics'
export type { CodeSource }

/** Secret credential entry returned by GET /api/secrets */
export interface RegistrySecret {
  id: string
  name: string
  type: string
  scope: string
}

/** Payload shape for POST/PUT /api/analytics/codebase/sources */
export interface SourceSavePayload {
  name: string
  source_type: 'github' | 'local'
  repo: string
  branch: string
  access: 'private' | 'shared' | 'public'
  credential_id: string | null
}

async function _getBackendUrl(): Promise<string> {
  return appConfig.getServiceUrl('backend')
}

/**
 * Load credentials available for source authentication.
 * Extracted from AddSourceModal.vue (#6069).
 */
export async function fetchSourceSecrets(): Promise<RegistrySecret[]> {
  const backendUrl = await _getBackendUrl()
  const data = await apiClient.get<{ secrets?: RegistrySecret[] }>(`${backendUrl}/api/secrets`)
  return data.secrets ?? []
}

/** Payload shape for POST /api/analytics/codebase/sources/:id/share */
export interface SourceSharePayload {
  access: 'private' | 'shared' | 'public'
  user_ids: string[]
}

/**
 * Update access control for a code source.
 * Extracted from ShareSourceModal.vue (#6070).
 */
export async function shareCodeSource(
  sourceId: string,
  payload: SourceSharePayload,
): Promise<CodeSource> {
  const backendUrl = await _getBackendUrl()
  return await apiClient.post<CodeSource>(
    `${backendUrl}/api/analytics/codebase/sources/${sourceId}/share`,
    payload,
  )
}

/**
 * Create or update a code source entry in the registry.
 * Uses POST for new entries, PUT for existing ones (when `id` is provided).
 * Extracted from AddSourceModal.vue (#6069).
 */
export async function saveCodeSource(
  payload: SourceSavePayload,
  id?: string,
): Promise<CodeSource> {
  const backendUrl = await _getBackendUrl()
  const url = id
    ? `${backendUrl}/api/analytics/codebase/sources/${id}`
    : `${backendUrl}/api/analytics/codebase/sources`
  return id
    ? await apiClient.put<CodeSource>(url, payload)
    : await apiClient.post<CodeSource>(url, payload)
}

export interface UseSourceRegistryDeps {
  t: (key: string, params?: Record<string, unknown>) => string
  showToast: (msg: string, type?: ToastType, duration?: number) => number | void
  notify: (msg: string, type?: ToastType) => void
}

export const STORAGE_KEY_PATH = 'codebase-analytics-path'

export function useSourceRegistry(deps: UseSourceRegistryDeps) {
  const { t, notify } = deps
  const route = useRoute()

  // Load path from localStorage if available, otherwise use default
  const savedPath = localStorage.getItem(STORAGE_KEY_PATH)
  const rootPath = ref(savedPath || '/opt/autobot')

  // Issue #1133: Source registry state. #5276: `sources` + `loadSources`
  // delegated to the shared `useSourcesListEndpoint` composable (was
  // duplicated across this file and `CodebaseAnalyticsLanding.vue`).
  const { sources, loadSources } = useSourcesListEndpoint()
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

  // Issue #6068: Load a single source by ID and populate selectedSource +
  // rootPath. Returns true on success, false on failure (caller handles
  // navigation).
  async function loadSourceById(sourceId: string): Promise<boolean> {
    try {
      const endpoint = useFetchEndpoint<CodeSource, CodeSource>({
        path: `/api/analytics/codebase/sources/${encodeURIComponent(sourceId)}`,
        pickData: (raw) => raw,
        label: 'Load source by ID',
      })
      await endpoint.load()
      if (endpoint.error.value || !endpoint.data.value) {
        notify(t('analytics.codebase.notify.sourceNotFound'), 'error')
        return false
      }
      const source = endpoint.data.value
      selectedSource.value = source
      rootPath.value = source.clone_path || ''
      localStorage.setItem(STORAGE_KEY_PATH, rootPath.value)
      return true
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error('Failed to load source metadata:', msg)
      notify(t('analytics.codebase.notify.sourceNotFound'), 'error')
      return false
    }
  }

  // #5153 B: migrated to useFetchEndpoint with POST body factory.
  // onError surfaces the user-visible toast; onSuccess hides the opt-in
  // banner and emits the success toast.
  const addKnowledgeBaseEndpoint = useFetchEndpoint<
    Record<string, unknown>,
    true
  >({
    path: '/api/analytics/codebase/index',
    method: 'POST',
    body: () => ({ root_path: rootPath.value }),
    pickData: () => true, // endpoint returns status; presence = success
    onSuccess: () => {
      showKnowledgeBaseOptIn.value = false
      notify(t('analytics.codebase.notify.knowledgeBaseAdded'), 'success')
    },
    onError: () => {
      notify(t('analytics.codebase.notify.knowledgeBaseFailed'), 'error')
    },
    onResponse: async (response) => {
      // Preserve the original "HTTP N: <body-text>" error shape.
      const text = await response.text().catch(() => '')
      return `HTTP ${response.status}${text ? `: ${text}` : ''}`
    },
    label: 'Add to knowledge base',
  })

  async function addToKnowledgeBase() {
    if (!rootPath.value) return
    knowledgeBaseAdding.value = true
    try {
      await addKnowledgeBaseEndpoint.load()
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
    loadSourceById,
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
