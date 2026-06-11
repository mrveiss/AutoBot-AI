// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * useLlcCompanyContext composable (GH#9861, GH#9627)
 *
 * Single source of truth for the "active company" an LLC view operates on.
 * The LLC company-scoped views (org chart, goal tree, dashboard) are reached
 * from a top-level nav entry that carries no company id, so the id must be
 * resolved at mount time. Resolution order:
 *
 *   1. route param  `:companyId`   (e.g. /llc/companies/:companyId/...)
 *   2. route query  `?company=...` (e.g. picked from the company hierarchy)
 *   3. company selector store      (GH#9627 — persisted user selection)
 *   4. first company from GET /api/llc/companies/ (sensible default)
 *
 * This mirrors the backend, which scopes to the caller's org when no
 * company_id is supplied. Whatever id wins is written back to the
 * llcCompany store so the selector and LLC sidebar stay in sync.
 */

import { ref } from 'vue'
import { useRoute } from 'vue-router'
import { useApiClient } from '@/plugins/api'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useLlcCompanyContext')

interface CompanyListEntry {
  id: string
}

export function useLlcCompanyContext() {
  const route = useRoute()
  const api = useApiClient()
  const companyStore = useLlcCompanyStore()
  const companyId = ref<string>('')

  /** Resolve and cache the active company id. Returns '' if none exists. */
  async function resolveCompanyId(): Promise<string> {
    const fromParam = (route.params.companyId as string | undefined) ?? ''
    const fromQuery = (route.query.company as string | undefined) ?? ''
    let id = fromParam || fromQuery || companyStore.selectedCompanyId
    if (!id) {
      try {
        const companies = await api.get<CompanyListEntry[]>('/api/llc/companies/')
        id = Array.isArray(companies) && companies.length > 0 ? companies[0].id : ''
      } catch (err: unknown) {
        logger.error('Failed to resolve default company:', err)
        id = ''
      }
    }
    companyId.value = id
    if (id) companyStore.selectCompany(id)
    return id
  }

  return { companyId, resolveCompanyId }
}
