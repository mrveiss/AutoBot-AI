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
   * overrides a newer list that confirmed it. A failed probe that is not a refusal sets
   * ``selectionUnverified``; ``fetchCompanies`` resets it on every run.
   */
  async function dropSelectionIfGone(): Promise<void> {
    const id = selectedCompanyId.value
    if (!id || companies.value.some((c) => c.id === id)) return
    try {
      await useApiClient().get(`${COMPANIES_ENDPOINT}${encodeURIComponent(id)}`, orgScope(id))
    } catch (err) {
      // A selection switched while the probe was in flight is someone else's; leave it.
      if (
        isHttpError(err) &&
        SELECTION_REFUSED_STATUSES.includes(err.status) &&
        selectedCompanyId.value === id &&
        !companies.value.some((c) => c.id === id)
      ) {
        selectedCompanyId.value = ''
        return
      }
      if (!(isHttpError(err) && SELECTION_REFUSED_STATUSES.includes(err.status))) {
        selectionUnverified.value = selectedCompanyId.value === id
      }
      logger.warn('company probe failed; keeping the selection:', err)
    }
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
    isLoading.value = true
    error.value = null
    unavailable.value = false
    selectionUnverified.value = false
    try {
      const endpoint = includeArchived
        ? `${COMPANIES_ENDPOINT}?include_archived=true`
        : COMPANIES_ENDPOINT
      const resp = await api.get<LlcCompany[]>(endpoint)
      companies.value = Array.isArray(resp) ? resp : []
      await dropSelectionIfGone()
    } catch (err) {
      const message = err instanceof Error ? err.message : ''
      // HTTP 503 = LLC data layer disabled in this deployment (no company mode).
      // Treat as "unavailable", not a user-facing error.
      if (isHttpError(err) && err.status === 503) {
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
    await api.delete(`${COMPANIES_ENDPOINT}${id}`, orgScope(id))
    companies.value = companies.value.filter((c) => c.id !== id)
    if (selectedCompanyId.value === id) selectedCompanyId.value = ''
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
