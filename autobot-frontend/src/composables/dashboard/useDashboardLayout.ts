// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Server-persisted dashboard layout per user and page (#18242).
 * GET/PUT/DELETE /users/me/dashboard-layouts/{page}. A failed save keeps the local
 * state and sets `saveError`; the grid shows it, so nothing fails silently.
 *
 * Nothing is written until a load has succeeded (`loaded`): after a failed GET the page
 * shows defaults, and saving or resetting those would overwrite or delete the user's real
 * server layout (#18896 review). `loadError` says why; `load()` retries.
 */
import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'
import { fromLegacyDashboards, fromStoredLayout, type DashboardLayout } from './dashboardLayoutModel'

type LayoutResponse = components['schemas']['DataResponse_DashboardLayoutData_']

export type DashboardPage = 'home' | 'company-os'

const LEGACY_KEY = 'autobot_dashboards'
const logger = createLogger('useDashboardLayout')

export function useDashboardLayout(page: DashboardPage, defaults: () => DashboardLayout) {
  const layout = ref<DashboardLayout>(defaults())
  const loaded = ref(false)
  const loadError = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const url = `${getApiBase()}/users/me/dashboard-layouts/${page}`

  async function put(next: DashboardLayout): Promise<boolean> {
    try {
      await apiClient.put(url, next)
      saveError.value = null
      return true
    } catch (e) {
      saveError.value = e instanceof Error ? e.message : String(e)
      logger.error('Saving dashboard layout failed:', e)
      return false
    }
  }

  // Storage can throw (private mode, blocked site data); that only means "no legacy layout".
  function readLegacy(): DashboardLayout | null {
    if (page !== 'home') return null
    try {
      const raw = localStorage.getItem(LEGACY_KEY)
      return raw ? fromLegacyDashboards(JSON.parse(raw)) : null
    } catch (e) {
      logger.error('Legacy dashboards unreadable; left in place:', e)
      return null
    }
  }

  function clearLegacy(): void {
    try {
      localStorage.removeItem(LEGACY_KEY)
    } catch (e) {
      logger.warn('Could not clear the legacy dashboards key:', e)
    }
  }

  async function migrateLegacy(): Promise<void> {
    const legacy = readLegacy()
    if (!legacy?.dashboards.length) return
    layout.value = legacy
    if (await put(legacy)) clearLegacy()
  }

  async function load(): Promise<void> {
    let body: LayoutResponse
    try {
      body = await apiClient.get(url) // typed by `body: LayoutResponse` (generated contract)
    } catch (e) {
      loadError.value = e instanceof Error ? e.message : String(e)
      logger.error('Loading dashboard layout failed; editing stays off until a load succeeds:', e)
      return
    }
    loadError.value = null
    const stored = body.data ? fromStoredLayout(body.data.layout) : null
    if (stored?.dashboards.length) layout.value = stored
    else await migrateLegacy()
    loaded.value = true
  }

  /** Saves explicitly (the view's Save button); resolves false and sets saveError on failure. */
  async function save(next: DashboardLayout): Promise<boolean> {
    if (!loaded.value) return false
    layout.value = next
    return put(next)
  }

  async function reset(): Promise<boolean> {
    if (!loaded.value) return false
    await apiClient.delete(url)
    // A legacy key left by a failed migration would otherwise restore the old layout next load.
    clearLegacy()
    layout.value = defaults()
    return true
  }

  return { layout, loaded, loadError, saveError, load, save, reset }
}
