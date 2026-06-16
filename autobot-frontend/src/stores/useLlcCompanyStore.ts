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

  const selectedCompany = computed(
    () => companies.value.find((c) => c.id === selectedCompanyId.value) ?? null,
  )

  const hasCompanies = computed(() => companies.value.length > 0)

  /** Load the company list from the backend (parsed JSON, no envelope). */
  async function fetchCompanies(): Promise<void> {
    const api = useApiClient()
    isLoading.value = true
    error.value = null
    try {
      const resp = await api.get<LlcCompany[]>(COMPANIES_ENDPOINT)
      companies.value = Array.isArray(resp) ? resp : []
      // Drop a persisted selection that no longer exists on the backend.
      if (
        selectedCompanyId.value &&
        !companies.value.some((c) => c.id === selectedCompanyId.value)
      ) {
        selectedCompanyId.value = ''
      }
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Failed to load companies'
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

  return {
    companies,
    selectedCompanyId,
    isLoading,
    error,
    selectedCompany,
    hasCompanies,
    fetchCompanies,
    selectCompany,
    clearSelection,
  }
}, {
  persist: {
    key: 'autobot-llc-company',
    storage: localStorage,
    pick: ['selectedCompanyId'], // companies/loading/error are session state
  },
})
