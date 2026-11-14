// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#9627: Pinia store for the LLC company selector — single source of truth
// for which company the LLC views operate on. The selected id persists across
// reloads so deep LLC navigation survives a refresh.

import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import { isHttpError } from '@autobot/ui'
import { useApiClient } from '@/plugins/api'
import { createLogger } from '@/utils/debugUtils'
import { orgScope } from '@/utils/orgContext'

const logger = createLogger('useLlcCompanyStore')

const COMPANIES_ENDPOINT = '/api/llc/companies/'

// Probe statuses that mean the backend will not serve this company to this user, however often
// retried: 404 not found, 403 not a member, 422 not a valid company id.
const SELECTION_REFUSED_STATUSES: readonly number[] = [404, 403, 422]

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
  // True only when the latest probe of the current selection failed without a refusal, so the
  // selection is kept but unverified. Not an error: the list itself loaded.
  const selectionUnverified = ref(false)

  // Newest fetchCompanies run; a probe from an older run may change nothing.
  let fetchRun = 0

  const selectedCompany = computed(
    () => companies.value.find((c) => c.id === selectedCompanyId.value) ?? null,
  )

  const hasCompanies = computed(() => companies.value.length > 0)

  /**
   * Drop a persisted selection the backend refuses for this user (#21531).
   *
   * The list is narrower than "exists": it holds only ROOT companies and hides ARCHIVED ones, so
   * a selected subsidiary or archived company is absent from it although the route names it.
   * Absence is therefore probed by id. The selection is cleared only when the backend refuses the
   * company in a way retrying cannot change (``SELECTION_REFUSED_STATUSES``); success, 5xx, 401,
   * 408/429 and non-HTTP errors keep it. The probed company is not added to ``companies``: the
   * selector must not start listing archived or subsidiary entries. A refusal is acted on only
   * while the id is still selected and still absent from the CURRENT list, so a late probe never
   * overrides a newer list that confirmed it. Only the newest run's probe may clear the selection
   * or set ``selectionUnverified``; the flag describes the current selection and is reset
   * whenever the selection changes and at the start of every ``fetchCompanies`` run.
   */
  async function dropSelectionIfGone(run: number): Promise<void> {
    const id = selectedCompanyId.value
    if (!id || companies.value.some((c) => c.id === id)) return
    try {
      await useApiClient().get(`${COMPANIES_ENDPOINT}${encodeURIComponent(id)}`, orgScope(id))
    } catch (err) {
      if (run !== fetchRun) return
      const stillAbsent = selectedCompanyId.value === id && !companies.value.some((c) => c.id === id)
      const refused = isHttpError(err) && SELECTION_REFUSED_STATUSES.includes(err.status)
      if (refused && stillAbsent) {
        selectedCompanyId.value = ''
        selectionUnverified.value = false
        return
      }
      if (!refused && stillAbsent) selectionUnverified.value = true
      logger.warn('company probe failed; keeping the selection:', err)
    }
  }

  /** Publish a failed list load as ``unavailable`` (HTTP 503: LLC disabled) or ``error``. */
  function recordLoadFailure(err: unknown): void {
    if (isHttpError(err) && err.status === 503) {
      unavailable.value = true
      return
    }
    error.value = (err instanceof Error ? err.message : '') || 'Failed to load companies'
  }

  /**
   * Load the company list from the backend (parsed JSON, no envelope).
   *
   * #12212: ARCHIVED companies are hidden by default; pass
   * ``includeArchived`` to surface them (the selector's "show archived" toggle)
   * so retired companies stay recoverable.
   */
  async function fetchCompanies(includeArchived = false): Promise<void> {
    const api = useApiClient()
    const run = ++fetchRun
    isLoading.value = true
    error.value = null
    unavailable.value = false
    selectionUnverified.value = false
    try {
      const endpoint = includeArchived
        ? `${COMPANIES_ENDPOINT}?include_archived=true`
        : COMPANIES_ENDPOINT
      const resp = await api.get<LlcCompany[]>(endpoint)
      // Only the newest run may publish: a superseded list must not overwrite a newer one.
      if (run !== fetchRun) return
      companies.value = Array.isArray(resp) ? resp : []
      await dropSelectionIfGone(run)
    } catch (err) {
      logger.error('fetchCompanies failed:', err)
      if (run === fetchRun) recordLoadFailure(err)
    } finally {
      if (run === fetchRun) isLoading.value = false
    }
  }

  /** Set the active company id (route guards keep this in sync on URL nav). */
  function selectCompany(id: string): void {
    selectedCompanyId.value = id
    selectionUnverified.value = false
  }

  function clearSelection(): void {
    selectedCompanyId.value = ''
    selectionUnverified.value = false
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
    await api.delete(`${COMPANIES_ENDPOINT}${id}`, orgScope(id))
    companies.value = companies.value.filter((c) => c.id !== id)
    if (selectedCompanyId.value === id) {
      selectedCompanyId.value = ''
      selectionUnverified.value = false
    }
  }

  return {
    companies,
    selectedCompanyId,
    isLoading,
    error,
    unavailable,
    selectionUnverified,
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
