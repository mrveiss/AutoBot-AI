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
 *
 * A network error or a 5xx answer (a backend restart) is retried with backoff before `loadError`
 * is set (#21462); `loaded` stays false throughout, so nothing is saved between attempts. A 4xx is
 * final. A `load()` while one is running joins it; disposing the scope stops the loop.
 */
import { getCurrentScope, onScopeDispose, ref } from 'vue'
import { backoffDelay, isHttpError } from '@autobot/ui'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'
import type { components } from '@/types/generated/api'
import { fromLegacyDashboards, fromStoredLayout, type DashboardLayout } from './dashboardLayoutModel'

type LayoutResponse = components['schemas']['DataResponse_DashboardLayoutData_']

export type DashboardPage = 'home' | 'company-os'

const LEGACY_KEY = 'autobot_dashboards'
const logger = createLogger('useDashboardLayout')

const HTTP_SERVER_ERROR_MIN = 500
/**
 * Retries after the first attempt. 2s,4s,8s,16s,20s,20s waits = 70s, plus the client's own GET
 * retries per attempt, covers a ~80s backend restart with ~7 requests, not a hammering loop.
 */
export const LOAD_RETRIES = 6
export const LOAD_RETRY_BASE_MS = 2000
export const LOAD_RETRY_MAX_MS = 20000

export interface LoadRetryOptions {
  retries?: number
  baseMs?: number
  maxMs?: number
}

/** Network errors and 5xx may pass on their own; any other HTTP status is the request's fault. */
function isRetryable(e: unknown): boolean {
  return !isHttpError(e) || e.status >= HTTP_SERVER_ERROR_MIN
}

export function useDashboardLayout(
  page: DashboardPage,
  defaults: () => DashboardLayout,
  { retries = LOAD_RETRIES, baseMs = LOAD_RETRY_BASE_MS, maxMs = LOAD_RETRY_MAX_MS }: LoadRetryOptions = {},
) {
  const layout = ref<DashboardLayout>(defaults())
  const loaded = ref(false)
  const loadError = ref<string | null>(null)
  const saveError = ref<string | null>(null)
  const url = `${getApiBase()}/users/me/dashboard-layouts/${page}`
  let disposed = false
  let running: Promise<void> | null = null
  let wake: (() => void) | null = null

  if (getCurrentScope()) {
    onScopeDispose(() => {
      disposed = true
      wake?.()
    })
  }

  // Resolves after `ms`, or at once when the scope is disposed.
  function sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      const timer = setTimeout(done, ms)
      function done() {
        clearTimeout(timer)
        wake = null
        resolve()
      }
      wake = done
    })
  }

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

  async function getLayout(): Promise<LayoutResponse> {
    for (let attempt = 0; ; attempt++) {
      try {
        const body: LayoutResponse = await apiClient.get(url) // typed by the generated contract
        return body
      } catch (e) {
        if (disposed || attempt >= retries || !isRetryable(e)) throw e
        logger.warn(`Loading dashboard layout failed (attempt ${attempt + 1}); retrying:`, e)
        await sleep(backoffDelay(attempt, { base: baseMs, max: maxMs }))
        if (disposed) throw e
      }
    }
  }

  async function runLoad(): Promise<void> {
    loadError.value = null
    let body: LayoutResponse
    try {
      body = await getLayout()
    } catch (e) {
      if (disposed) return
      loadError.value = e instanceof Error ? e.message : String(e)
      logger.error('Loading dashboard layout failed; editing stays off until a load succeeds:', e)
      return
    }
    if (disposed) return
    const stored = body.data ? fromStoredLayout(body.data.layout) : null
    if (stored?.dashboards.length) layout.value = stored
    else await migrateLegacy()
    loaded.value = true
  }

  /** One loop at a time: a call while a load is running joins it. */
  function load(): Promise<void> {
    running ??= runLoad().finally(() => {
      running = null
    })
    return running
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
