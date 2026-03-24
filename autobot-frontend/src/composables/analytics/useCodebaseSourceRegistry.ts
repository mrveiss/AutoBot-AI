// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Composable: useCodebaseSourceRegistry
 * Source CRUD operations and selection for code source registry.
 * Issue #2228/#2230: Extracted from CodebaseAnalytics.vue script section.
 */
import type { Ref } from 'vue'
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
import type { CodeSource } from '@/types/codebaseAnalytics'

const logger = createLogger('useCodebaseSourceRegistry')
const STORAGE_KEY_PATH = 'codebase-analytics-path'

export interface SourceRegistryDeps {
  rootPath: Ref<string>
  sources: Ref<CodeSource[]>
  selectedSource: Ref<CodeSource | null>
  showSourceManager: Ref<boolean>
  showAddSourceModal: Ref<boolean>
  showShareSourceModal: Ref<boolean>
  editTargetSource: Ref<CodeSource | null>
  shareTargetSource: Ref<CodeSource | null>
  showKnowledgeBaseOptIn: Ref<boolean>
  knowledgeBaseAdding: Ref<boolean>
  notify: (message: string, type: 'info' | 'success' | 'warning' | 'error') => void
  t: (key: string, params?: Record<string, unknown>) => string
}

export function useCodebaseSourceRegistry(deps: SourceRegistryDeps) {
  async function loadSources(): Promise<void> {
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/sources`)
      if (!response.ok) return
      const data = await response.json()
      deps.sources.value = data.sources ?? []
    } catch (err: unknown) { logger.warn('Failed to load sources:', err instanceof Error ? err.message : String(err)) }
  }

  function handleSelectSource(source: CodeSource): void {
    deps.selectedSource.value = source
    if (source.clone_path) { deps.rootPath.value = source.clone_path; localStorage.setItem(STORAGE_KEY_PATH, source.clone_path) }
    deps.showSourceManager.value = false
    deps.notify(deps.t('analytics.codebase.notify.selectedSource', { name: source.name }), 'info')
  }

  function handleClearSource(): void { deps.selectedSource.value = null }

  async function handleSourceSaved(source: CodeSource): Promise<void> {
    deps.showAddSourceModal.value = false; deps.editTargetSource.value = null
    await loadSources()
    deps.notify(deps.t('analytics.codebase.notify.sourceSaved', { name: source.name }), 'success')
  }

  async function handleShareSaved(source: CodeSource): Promise<void> {
    deps.showShareSourceModal.value = false; deps.shareTargetSource.value = null
    await loadSources()
    deps.notify(deps.t('analytics.codebase.notify.accessUpdated', { name: source.name }), 'success')
  }

  function handleEditSource(source: CodeSource): void {
    deps.editTargetSource.value = source; deps.showAddSourceModal.value = true; deps.showSourceManager.value = false
  }

  function handleShareSource(source: CodeSource): void {
    deps.shareTargetSource.value = source; deps.showShareSourceModal.value = true
  }

  async function addToKnowledgeBase(): Promise<void> {
    if (!deps.rootPath.value) return
    deps.knowledgeBaseAdding.value = true
    try {
      const backendUrl = await appConfig.getServiceUrl('backend')
      const response = await fetchWithAuth(`${backendUrl}/api/analytics/codebase/index`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ root_path: deps.rootPath.value }) })
      if (!response.ok) { const text = await response.text(); throw new Error(`HTTP ${response.status}: ${text}`) }
      deps.showKnowledgeBaseOptIn.value = false
      deps.notify(deps.t('analytics.codebase.notify.knowledgeBaseAdded'), 'success')
    } catch (err: unknown) {
      logger.error('Failed to add to knowledge base:', err instanceof Error ? err.message : String(err))
      deps.notify(deps.t('analytics.codebase.notify.knowledgeBaseFailed'), 'error')
    } finally { deps.knowledgeBaseAdding.value = false }
  }

  return { loadSources, handleSelectSource, handleClearSource, handleSourceSaved, handleShareSaved, handleEditSource, handleShareSource, addToKnowledgeBase }
}
