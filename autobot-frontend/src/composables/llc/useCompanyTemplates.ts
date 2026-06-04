// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * useCompanyTemplates composable (GH#9164)
 *
 * Provides API access to LLC company template library:
 * - List built-in templates
 * - Get template details
 * - Search templates (custom templates from DB)
 * - Import template into company
 */

import { ref } from 'vue'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import type { AxiosError } from 'axios'

const logger = createLogger('useCompanyTemplates')

export type TemplateCategory =
  | 'software-team'
  | 'marketing-agency'
  | 'consulting-firm'
  | 'research-lab'
  | 'startup'
  | 'custom'

export interface CompanyTemplate {
  key: string
  name: string
  description: string
  category: TemplateCategory
  tags: string[]
  icon?: string
  estimated_agents?: number
  estimated_monthly_cost_cents?: number
  variables?: Record<string, { description: string; default?: string; required?: boolean }>
  agents?: Array<{
    name: string
    title: string
    role: string
    adapter_type: string
  }>
  goals?: Array<{
    level: string
    title: string
    description: string
  }>
  work_items?: Array<{
    type: string
    title: string
    description: string
  }>
  kb_collections?: Array<{
    name: string
    description: string
  }>
}

export interface TemplateImportRequest {
  target_company_id: string
  variable_values?: Record<string, string>
  secret_mappings?: Record<string, string>
}

export interface TemplateImportResult {
  company_id: string
  agents_created: number
  goals_created: number
  work_items_created: number
  kb_collections_created: number
}

export function useCompanyTemplates() {
  const api = useApiClient()

  const templates = ref<CompanyTemplate[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function listBuiltInTemplates(): Promise<CompanyTemplate[]> {
    loading.value = true
    error.value = null
    try {
      const response = await api.get<CompanyTemplate[]>('/api/llc/templates/built-in')
      templates.value = response
      return response
    } catch (err) {
      const msg = (err as AxiosError)?.message ?? String(err)
      logger.error('Failed to list built-in templates', err)
      error.value = `Failed to load templates: ${msg}`
      throw err
    } finally {
      loading.value = false
    }
  }

  async function getBuiltInTemplate(templateKey: string): Promise<CompanyTemplate> {
    loading.value = true
    error.value = null
    try {
      const response = await api.get<CompanyTemplate>(
        `/api/llc/templates/built-in/${encodeURIComponent(templateKey)}`
      )
      return response
    } catch (err) {
      const msg = (err as AxiosError)?.message ?? String(err)
      logger.error(`Failed to get template ${templateKey}`, err)
      error.value = `Failed to load template: ${msg}`
      throw err
    } finally {
      loading.value = false
    }
  }

  async function importTemplate(
    templateId: string,
    request: TemplateImportRequest
  ): Promise<TemplateImportResult> {
    loading.value = true
    error.value = null
    try {
      const response = await api.post<TemplateImportResult>(
        `/api/llc/templates/${encodeURIComponent(templateId)}/import`,
        request
      )
      return response
    } catch (err) {
      const msg = (err as AxiosError)?.message ?? String(err)
      logger.error(`Failed to import template ${templateId}`, err)
      error.value = `Failed to import template: ${msg}`
      throw err
    } finally {
      loading.value = false
    }
  }

  return {
    templates,
    loading,
    error,
    listBuiltInTemplates,
    getBuiltInTemplate,
    importTemplate,
  }
}
