// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Scrape Template API composable (GH#5136 Phase 5).
 *
 * Wraps the REST endpoints introduced in Phase 4:
 *   GET    /scrape-templates/
 *   POST   /scrape-templates/{id}/run?url=...
 *   DELETE /scrape-templates/{id}
 *   POST   /scrape-templates/         (used for duplicate)
 */

import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useScrapeTemplates')

// ===== Type Definitions =====

export interface ScrapeRegion {
  label: string
  selector?: string | null
  xpath?: string | null
}

export interface ScrapeTemplate {
  id: string
  name: string
  url_pattern: string
  regions: ScrapeRegion[]
  created_by: string
  created_at: string
}

export interface ListTemplatesResponse {
  templates: ScrapeTemplate[]
  count: number
}

export interface RunTemplateResponse {
  template_id: string
  url: string
  results: Record<string, string | null>
}

// ===== Composable =====

export function useScrapeTemplates() {
  const base = () => `${getApiBase()}/scrape-templates`

  /** List all templates for the current user. */
  async function listTemplates(): Promise<ScrapeTemplate[]> {
    try {
      const resp = (await apiClient.get<ListTemplatesResponse>(`${base()}/`)) as ListTemplatesResponse
      return resp.templates ?? []
    } catch (err) {
      logger.warn('Failed to list scrape templates', err)
      return []
    }
  }

  /**
   * Execute a template against a target URL.
   * Returns the extraction results keyed by region label.
   */
  async function runTemplate(id: string, url: string): Promise<RunTemplateResponse> {
    return (await apiClient.post<RunTemplateResponse>(
      `${base()}/${id}/run?url=${encodeURIComponent(url)}`
    )) as RunTemplateResponse
  }

  /** Delete a template by ID. */
  async function deleteTemplate(id: string): Promise<void> {
    await apiClient.delete(`${base()}/${id}`)
  }

  /**
   * Duplicate a template: create a new one with "(copy)" appended to the name.
   * Returns the newly created template.
   */
  async function duplicateTemplate(template: ScrapeTemplate): Promise<ScrapeTemplate> {
    const body = {
      name: `${template.name} (copy)`,
      url_pattern: template.url_pattern,
      regions: template.regions,
    }
    return (await apiClient.post<ScrapeTemplate>(`${base()}/`, body)) as ScrapeTemplate
  }

  return {
    listTemplates,
    runTemplate,
    deleteTemplate,
    duplicateTemplate,
  }
}
