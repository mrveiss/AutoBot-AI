// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Workflow Templates API composable
 * Issue #778 - Workflow Templates Enhancement
 *
 * GET-fetchers route through `useFetchEndpoint` (POC migrated in #5154,
 * rehomed from `analytics/useAnalyticsEndpoint` in #5153 scope C). The
 * rehomed composable defaults `scopeToSource: false` and makes `deps`
 * optional, so non-analytics callers like this one no longer need the
 * `scopeToSource: false` + `noScope` shim per call site.
 *
 * POSTs (`createWorkflowFromTemplate`, `executeTemplate`) are intentionally
 * left untouched — `useFetchEndpoint` also supports POST now (#5157) but
 * these endpoints have non-standard response handling (direct `.json()`
 * return) that doesn't fit `pickData`.
 */

import { ref, computed, watch } from 'vue'
import { createLogger } from '@/utils/debugUtils'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { useFetchEndpoint } from '@/composables/api/useFetchEndpoint'
import { useLoadingState } from '@/composables/useLoadingState'
import type {
  WorkflowTemplateSummary,
  WorkflowTemplateDetail,
  TemplateCategoryInfo,
  TemplateStatsResponse,
  TemplatePreviewResponse,
  CreateWorkflowResponse,
  TemplateCategory
} from '@/types/workflowTemplates'

const logger = createLogger('useWorkflowTemplates')

export function useWorkflowTemplates() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  // State
  const templates = ref<WorkflowTemplateSummary[]>([])
  const categories = ref<TemplateCategoryInfo[]>([])
  const stats = ref<TemplateStatsResponse['statistics'] | null>(null)
  const selectedTemplate = ref<WorkflowTemplateDetail | null>(null)
  const preview = ref<TemplatePreviewResponse | null>(null)

  // ---------------------------------------------------------------------------
  // GET endpoints (#5154 — routed through useAnalyticsEndpoint)
  // ---------------------------------------------------------------------------
  // Per-instance endpoints whose path is known at composable-construction time.
  // Endpoints that need a path parameter (`fetchTemplateDetail`,
  // `previewTemplate`) are constructed inside their wrapper function below.

  const templatesEndpoint = useFetchEndpoint<
    { templates?: WorkflowTemplateSummary[] },
    WorkflowTemplateSummary[]
  >({
    path: '/api/templates/templates',
    label: 'Templates list',
    pickData: (raw) => raw.templates ?? [],
    onSuccess: (d) => { templates.value = d },
    onError: (msg) => { error.value = `Failed to fetch templates: ${msg}` },
  })

  const searchEndpoint = useFetchEndpoint<
    { results?: WorkflowTemplateSummary[] },
    WorkflowTemplateSummary[]
  >({
    path: '/api/templates/templates/search',
    label: 'Templates search',
    pickData: (raw) => raw.results ?? [],
    onError: (msg) => { error.value = `Failed to search templates: ${msg}` },
  })

  const categoriesEndpoint = useFetchEndpoint<
    { categories?: TemplateCategoryInfo[] },
    TemplateCategoryInfo[]
  >({
    path: '/api/templates/templates/categories',
    label: 'Templates categories',
    pickData: (raw) => raw.categories ?? [],
    onSuccess: (d) => { categories.value = d },
    // Original `fetchCategories` logs but does NOT surface to error.value.
    onError: () => { /* logger.error already fired inside endpoint */ },
  })

  const statsEndpoint = useFetchEndpoint<
    { statistics?: TemplateStatsResponse['statistics'] },
    TemplateStatsResponse['statistics']
  >({
    path: '/api/templates/templates/stats',
    label: 'Templates stats',
    pickData: (raw) => raw.statistics ?? null,
    onSuccess: (d) => { stats.value = d },
    // Original `fetchStats` logs but does NOT surface to error.value.
    onError: () => { /* logger.error already fired inside endpoint */ },
  })

  // Loading state for POST mutations
  const { isLoading: mutationLoading, wrap: wrapMutation } = useLoadingState()

  // Bridge per-endpoint loading flags into the composable-level `loading` ref
  // so the public API (consumers reading `loading.value`) is preserved.
  // Endpoints that only set state (templates/categories/stats) AND on-demand
  // endpoints (search/detail/preview) flip the same flag.
  const ondemandLoading = ref(false)
  watch(
    [
      templatesEndpoint.loading,
      searchEndpoint.loading,
      categoriesEndpoint.loading,
      statsEndpoint.loading,
      ondemandLoading,
      mutationLoading,
    ],
    (flags: boolean[]) => {
      loading.value = flags.some(Boolean)
    },
  )

  // ---------------------------------------------------------------------------
  // Public API — wrappers preserve names, signatures, and return types verbatim.
  // ---------------------------------------------------------------------------

  async function fetchTemplates(
    category?: TemplateCategory,
    tags?: string[],
    complexity?: string
  ): Promise<void> {
    error.value = null
    const query: Record<string, string> = {}
    if (category) query.category = category
    if (tags?.length) query.tags = tags.join(',')
    if (complexity) query.complexity = complexity
    await templatesEndpoint.load(query)
  }

  async function fetchTemplateDetail(
    templateId: string
  ): Promise<WorkflowTemplateDetail | null> {
    error.value = null
    ondemandLoading.value = true
    try {
      const detailEndpoint = useFetchEndpoint<
        { template?: WorkflowTemplateDetail },
        WorkflowTemplateDetail
      >({
        path: `/api/templates/templates/${templateId}`,
        label: 'Template detail',
        pickData: (raw) => raw.template ?? null,
        onSuccess: (d) => { selectedTemplate.value = d },
        // Original assigned `data.template` (possibly undefined) unconditionally.
        // Preserve "clear on missing" behaviour via onNoData.
        onNoData: () => { selectedTemplate.value = null },
        onError: (msg) => { error.value = `Failed to fetch template: ${msg}` },
      })
      await detailEndpoint.load()
      return detailEndpoint.data.value
    } finally {
      ondemandLoading.value = false
    }
  }

  async function searchTemplates(
    query: string
  ): Promise<WorkflowTemplateSummary[]> {
    error.value = null
    await searchEndpoint.load({ q: query })
    return searchEndpoint.data.value ?? []
  }

  async function fetchCategories(): Promise<void> {
    await categoriesEndpoint.load()
  }

  async function fetchStats(): Promise<void> {
    await statsEndpoint.load()
  }

  async function previewTemplate(
    templateId: string,
    variables?: Record<string, string>
  ): Promise<TemplatePreviewResponse | null> {
    error.value = null
    ondemandLoading.value = true
    try {
      const query: Record<string, string> = {}
      if (variables && Object.keys(variables).length > 0) {
        query.variables = JSON.stringify(variables)
      }
      const previewEndpoint = useFetchEndpoint<
        TemplatePreviewResponse,
        TemplatePreviewResponse
      >({
        path: `/api/templates/templates/${templateId}/preview`,
        label: 'Template preview',
        pickData: (raw) => raw,
        onSuccess: (d) => { preview.value = d },
        onError: (msg) => { error.value = `Failed to preview template: ${msg}` },
      })
      await previewEndpoint.load(query)
      return previewEndpoint.data.value
    } finally {
      ondemandLoading.value = false
    }
  }

  // ---------------------------------------------------------------------------
  // POST endpoints — migrated to ApiClient (#6029).
  // ---------------------------------------------------------------------------

  async function createWorkflowFromTemplate(
    templateId: string,
    variables?: Record<string, string>
  ): Promise<CreateWorkflowResponse | null> {
    error.value = null
    return wrapMutation(async () => {
      return await apiClient.post<CreateWorkflowResponse>(
        `${getApiBase()}/templates/templates/${templateId}/create-workflow`,
        { template_id: templateId, variables: variables || {}, auto_approve: false }
      )
    }).catch((e) => {
      error.value = `Failed to create workflow: ${e}`
      logger.error('createWorkflowFromTemplate failed:', e)
      return null
    })
  }

  async function executeTemplate(
    templateId: string,
    variables?: Record<string, string>,
    autoApprove = false
  ): Promise<CreateWorkflowResponse | null> {
    error.value = null
    return wrapMutation(async () => {
      return await apiClient.post<CreateWorkflowResponse>(
        `${getApiBase()}/templates/templates/${templateId}/execute`,
        { template_id: templateId, variables: variables || {}, auto_approve: autoApprove }
      )
    }).catch((e) => {
      error.value = `Failed to execute template: ${e}`
      logger.error('executeTemplate failed:', e)
      return null
    })
  }

  async function initializeTemplates(): Promise<void> {
    await Promise.all([fetchTemplates(), fetchCategories(), fetchStats()])
  }

  // Computed
  const totalTemplates = computed(() => stats.value?.total_templates || templates.value.length)
  const categoryNames = computed(() => categories.value.map(c => c.display_name))

  return {
    // State
    loading,
    error,
    templates,
    categories,
    stats,
    selectedTemplate,
    preview,
    // Computed
    totalTemplates,
    categoryNames,
    // Actions
    fetchTemplates,
    fetchTemplateDetail,
    searchTemplates,
    fetchCategories,
    fetchStats,
    previewTemplate,
    createWorkflowFromTemplate,
    executeTemplate,
    initializeTemplates
  }
}
