// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#9627: Pinia store for the LLC company selector — single source of truth
// for which company the LLC views operate on. The selected id persists across
// reloads so deep LLC navigation survives a refresh.

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useLlcCompanyStore')

const COMPANIES_ENDPOINT = '/api/llc/companies/'

/** Subset of the backend CompanyRead schema the selector needs. */
export interface LlcCompany {
  id: string
  name: string
  slug?: string
  description?: string | null
  llc_status?: string
  brand_color?: string | null
}

export const useLlcCompanyStore = defineStore('llcCompany', () => {
  const companies = ref<LlcCompany[]>([])
  const selectedCompanyId = ref<string>('')
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  // True when the backend reports LLC is not enabled for this deployment
  // (no PostgreSQL company mode → HTTP 503). This is an expected state, NOT an
  // error to surface to end users.
  const unavailable = ref(false)

  const selectedCompany = computed(
    () => companies.value.find((c) => c.id === selectedCompanyId.value) ?? null,
  )

  const hasCompanies = computed(() => companies.value.length > 0)

  /**
   * Load the company list from the backend (parsed JSON, no envelope).
   *
   * #12212: ARCHIVED companies are hidden by default; pass
   * ``includeArchived`` to surface them (the selector's "show archived" toggle)
   * so retired companies stay recoverable.
   */
  async function fetchCompanies(includeArchived = false): Promise<void> {
    const api = useApiClient()
    isLoading.value = true
    error.value = null
    unavailable.value = false
    try {
      const endpoint = includeArchived
        ? `${COMPANIES_ENDPOINT}?include_archived=true`
        : COMPANIES_ENDPOINT
      const resp = await api.get<LlcCompany[]>(endpoint)
      companies.value = Array.isArray(resp) ? resp : []
      // Drop a persisted selection that no longer exists on the backend.
      if (
        selectedCompanyId.value &&
        !companies.value.some((c) => c.id === selectedCompanyId.value)
      ) {
        selectedCompanyId.value = ''
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : ''
      // HTTP 503 = LLC data layer disabled in this deployment (no company mode).
      // Treat as "unavailable", not a user-facing error.
      if (message.startsWith('HTTP 503')) {
        unavailable.value = true
      } else {
        error.value = message || 'Failed to load companies'
      }
      logger.error('fetchCompanies failed:', err)
    } finally {
      isLoading.value = false
    }
  }

  /** Set the active company id (route guards keep this in sync on URL nav). */
  function selectCompany(id: string): void {
    selectedCompanyId.value = id
  }

  function clearSelection(): void {
    selectedCompanyId.value = ''
  }

  /**
   * Patch a company's llc_status in-place after a status transition (#12231),
   * so the selector badge reflects the new state without a full refetch.
   */
  function applyStatus(id: string, status: string): void {
    const company = companies.value.find((c) => c.id === id)
    if (company) company.llc_status = status
  }

  /**
   * Soft-delete a company (#12212) via ``DELETE /api/llc/companies/{id}`` and
   * drop it from the in-memory list on success. The row's own id is sent as the
   * ``X-Organization-Id`` tenant scope so the backend ``assert_company_access``
   * guard authorises the delete regardless of which company is currently
   * selected. Clears the persisted selection if the deleted company was active.
   * Re-throws so the caller can surface a specific error (e.g. 409 has children).
   */
  async function deleteCompany(id: string): Promise<void> {
    const api = useApiClient()
    await api.delete(`${COMPANIES_ENDPOINT}${id}`, {
      headers: { 'X-Organization-Id': id },
    })
    companies.value = companies.value.filter((c) => c.id !== id)
    if (selectedCompanyId.value === id) selectedCompanyId.value = ''
  }

  return {
    companies,
    selectedCompanyId,
    isLoading,
    error,
    unavailable,
    selectedCompany,
    hasCompanies,
    fetchCompanies,
    selectCompany,
    clearSelection,
    applyStatus,
    deleteCompany,
  }
}, {
  persist: {
    key: 'autobot-llc-company',
    storage: localStorage,
    pick: ['selectedCompanyId'], // companies/loading/error are session state
  },
})
