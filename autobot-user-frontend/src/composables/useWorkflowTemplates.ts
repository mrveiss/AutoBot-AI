// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Workflow Templates API composable
 * Issue #778 - Workflow Templates Enhancement
 */

import { ref, computed } from 'vue'
import appConfig from '@/config/AppConfig.js'
import { createLogger } from '@/utils/debugUtils'
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

  async function getBackendUrl(): Promise<string> {
    return await appConfig.getServiceUrl('backend')
  }

  async function fetchTemplates(
    category?: TemplateCategory,
    tags?: string[],
    complexity?: string
  ): Promise<void> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const params = new URLSearchParams()
      if (category) params.append('category', category)
      if (tags?.length) params.append('tags', tags.join(','))
      if (complexity) params.append('complexity', complexity)

      const url = `${backendUrl}/api/templates/templates${params.toString() ? '?' + params.toString() : ''}`
      const response = await fetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      templates.value = data.templates || []
    } catch (e) {
      error.value = `Failed to fetch templates: ${e}`
      logger.error('fetchTemplates failed:', e)
    } finally {
      loading.value = false
    }
  }

  async function fetchTemplateDetail(templateId: string): Promise<WorkflowTemplateDetail | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/templates/templates/${templateId}`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      selectedTemplate.value = data.template
      return data.template
    } catch (e) {
      error.value = `Failed to fetch template: ${e}`
      logger.error('fetchTemplateDetail failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function searchTemplates(query: string): Promise<WorkflowTemplateSummary[]> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/templates/templates/search?q=${encodeURIComponent(query)}`
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      return data.results || []
    } catch (e) {
      error.value = `Failed to search templates: ${e}`
      logger.error('searchTemplates failed:', e)
      return []
    } finally {
      loading.value = false
    }
  }

  async function fetchCategories(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/templates/templates/categories`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      categories.value = data.categories || []
    } catch (e) {
      logger.error('fetchCategories failed:', e)
    }
  }

  async function fetchStats(): Promise<void> {
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(`${backendUrl}/api/templates/templates/stats`)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      stats.value = data.statistics
    } catch (e) {
      logger.error('fetchStats failed:', e)
    }
  }

  async function previewTemplate(
    templateId: string,
    variables?: Record<string, string>
  ): Promise<TemplatePreviewResponse | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      let url = `${backendUrl}/api/templates/templates/${templateId}/preview`
      if (variables && Object.keys(variables).length > 0) {
        url += `?variables=${encodeURIComponent(JSON.stringify(variables))}`
      }
      const response = await fetch(url)
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      preview.value = data
      return data
    } catch (e) {
      error.value = `Failed to preview template: ${e}`
      logger.error('previewTemplate failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function createWorkflowFromTemplate(
    templateId: string,
    variables?: Record<string, string>
  ): Promise<CreateWorkflowResponse | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/templates/templates/${templateId}/create-workflow`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            template_id: templateId,
            variables: variables || {},
            auto_approve: false
          })
        }
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json()
    } catch (e) {
      error.value = `Failed to create workflow: ${e}`
      logger.error('createWorkflowFromTemplate failed:', e)
      return null
    } finally {
      loading.value = false
    }
  }

  async function executeTemplate(
    templateId: string,
    variables?: Record<string, string>,
    autoApprove = false
  ): Promise<CreateWorkflowResponse | null> {
    loading.value = true
    error.value = null
    try {
      const backendUrl = await getBackendUrl()
      const response = await fetch(
        `${backendUrl}/api/templates/templates/${templateId}/execute`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            template_id: templateId,
            variables: variables || {},
            auto_approve: autoApprove
          })
        }
      )
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      return await response.json()
    } catch (e) {
      error.value = `Failed to execute template: ${e}`
      logger.error('executeTemplate failed:', e)
      return null
    } finally {
      loading.value = false
    }
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
