// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * LLC Store — Company state management (Issue #9627)
 *
 * Manages:
 * - Selected company ID for LLC context
 * - Company list fetching and caching
 * - Loading states
 */

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import apiClient from '@/services/api'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('LLCStore')

export interface Company {
  id: string
  name: string
  slug: string
  description?: string
  issue_prefix: string
  issue_counter: number
  budget_monthly_cents: number
  spent_monthly_cents: number
  brand_color?: string
  require_approval_for_hires: boolean
  parent_org_id?: string
  llc_status: 'active' | 'paused' | 'inactive'
  pause_reason?: string
  paused_at?: string
  created_at: string
  updated_at: string
}

export const useLLCStore = defineStore('llc', () => {
  // State
  const selectedCompanyId = ref<string | null>(null)
  const companies = ref<Company[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastFetchTime = ref<number>(0)

  // Cache duration: 5 minutes
  const CACHE_DURATION = 5 * 60 * 1000

  // Computed
  const selectedCompany = computed(() => {
    if (!selectedCompanyId.value) return null
    return companies.value.find(c => c.id === selectedCompanyId.value) || null
  })

  const hasCompanies = computed(() => companies.value.length > 0)

  // Actions
  async function fetchCompanies(forceRefresh = false): Promise<void> {
    const now = Date.now()
    const cacheValid = now - lastFetchTime.value < CACHE_DURATION

    if (!forceRefresh && cacheValid && companies.value.length > 0) {
      logger.debug('Using cached companies')
      return
    }

    isLoading.value = true
    error.value = null

    try {
      logger.debug('Fetching companies from API')
      const result = await apiClient.get<Company[]>('/api/llc/companies')
      companies.value = result
      lastFetchTime.value = now
      logger.debug(`Fetched ${result.length} companies`)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch companies'
      error.value = message
      logger.error('Failed to fetch companies:', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  function selectCompany(companyId: string): void {
    const company = companies.value.find(c => c.id === companyId)
    if (!company) {
      logger.warn(`Company ${companyId} not found in cache`)
      return
    }

    selectedCompanyId.value = companyId
    logger.debug(`Selected company: ${company.name} (${companyId})`)
  }

  function clearSelection(): void {
    selectedCompanyId.value = null
    logger.debug('Cleared company selection')
  }

  function clearCache(): void {
    companies.value = []
    lastFetchTime.value = 0
    logger.debug('Cleared company cache')
  }

  // Persist selected company ID to localStorage
  function persistSelection(): void {
    if (selectedCompanyId.value) {
      localStorage.setItem('llc.selectedCompanyId', selectedCompanyId.value)
    } else {
      localStorage.removeItem('llc.selectedCompanyId')
    }
  }

  // Restore selected company ID from localStorage
  function restoreSelection(): void {
    const stored = localStorage.getItem('llc.selectedCompanyId')
    if (stored) {
      selectedCompanyId.value = stored
      logger.debug(`Restored company selection: ${stored}`)
    }
  }

  return {
    // State
    selectedCompanyId,
    companies,
    isLoading,
    error,

    // Computed
    selectedCompany,
    hasCompanies,

    // Actions
    fetchCompanies,
    selectCompany,
    clearSelection,
    clearCache,
    persistSelection,
    restoreSelection,
  }
})
