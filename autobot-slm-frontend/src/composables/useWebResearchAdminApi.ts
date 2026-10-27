// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Web research admin API composable (#19217)
 *
 * The one editor for the platform-wide web research settings lives in the SLM. Every
 * route is served by the MAIN backend (api/web_research_settings.py), so the transport
 * is the shared main-backend client (`createAutobotBackendClient`, also behind
 * `useAutobotApi`), in its own composable so that file does not grow. The writes
 * are admin-only on the backend.
 *
 * Contract types come from the generated OpenAPI schema (see autobotAdminModels.ts).
 * PUT, enable and disable answer 200 with `status: "saved_not_applied"` when the value is
 * saved but the running researcher did not take it: callers must surface that, not treat
 * it as a plain success.
 */

import { createAutobotBackendClient } from '@/composables/useAutobotApi'
import type {
  WebResearchCacheClearData,
  WebResearchSettings,
  WebResearchSettingsData,
  WebResearchSettingsUpdate,
  WebResearchSettingsUpdateData,
  WebResearchStatusData,
  WebResearchToggleData,
} from '@/composables/autobotAdminModels'

export type {
  WebResearchCacheClearData,
  WebResearchSettings,
  WebResearchSettingsUpdate,
  WebResearchSettingsUpdateData,
  WebResearchStatusData,
  WebResearchToggleData,
}

export const WEB_RESEARCH_SAVED_NOT_APPLIED = 'saved_not_applied'
export const WEB_RESEARCH_UNAVAILABLE_STATUS = 503

/** True when the backend says the researcher failed to initialise (503 on status/clear/reset). */
export function isWebResearcherUnavailable(err: unknown): boolean {
  return (err as { response?: { status?: number } })?.response?.status === WEB_RESEARCH_UNAVAILABLE_STATUS
}

/** True when a write was saved but the running researcher did not take it. */
export function isSavedNotApplied(result: { status: string }): boolean {
  return result.status === WEB_RESEARCH_SAVED_NOT_APPLIED
}

export function useWebResearchAdminApi() {
  const client = createAutobotBackendClient()

  async function getSettings(): Promise<WebResearchSettings> {
    const response = await client.get<WebResearchSettingsData>('/web-research/settings')
    return response.data.settings
  }

  /** Sends only the fields present in `changes`. */
  async function updateSettings(changes: WebResearchSettingsUpdate): Promise<WebResearchSettingsUpdateData> {
    const response = await client.put<WebResearchSettingsUpdateData>('/web-research/settings', changes)
    return response.data
  }

  async function enable(): Promise<WebResearchToggleData> {
    const response = await client.post<WebResearchToggleData>('/web-research/enable')
    return response.data
  }

  async function disable(): Promise<WebResearchToggleData> {
    const response = await client.post<WebResearchToggleData>('/web-research/disable')
    return response.data
  }

  /** Rejects with a 503 (see isWebResearcherUnavailable) when the researcher is not running. */
  async function getStatus(): Promise<WebResearchStatusData> {
    const response = await client.get<WebResearchStatusData>('/web-research/status')
    return response.data
  }

  async function clearCache(): Promise<WebResearchCacheClearData> {
    const response = await client.post<WebResearchCacheClearData>('/web-research/clear-cache')
    return response.data
  }

  async function resetCircuitBreakers(): Promise<WebResearchCacheClearData> {
    const response = await client.post<WebResearchCacheClearData>('/web-research/reset-circuit-breakers')
    return response.data
  }

  return { getSettings, updateSettings, enable, disable, getStatus, clearCache, resetCircuitBreakers }
}
