// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Browser Session Data Composable
 * Issue #6074 - Extract fetchWithAuth/apiClient calls from PopoutChromiumBrowser
 *
 * Centralises all HTTP interactions for the Playwright/VNC browser panel so that
 * PopoutChromiumBrowser.vue contains no direct fetchWithAuth or apiClient calls.
 */

import { fetchWithAuth } from '@/utils/fetchWithAuth'
import apiClient from '@/utils/ApiClient'
import { getApiBase } from '@/config/ssot-config'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useBrowserSessionData')

// ===== Type Definitions =====

export interface PlaywrightNavigationResponse {
  final_url?: string
  url?: string
  title?: string
  status?: string
  [key: string]: unknown
}

export interface BrowserSessionResponse {
  url?: string
  [key: string]: unknown
}

export interface RegionRect {
  x: number
  y: number
  w: number
  h: number
}

/** DOM region returned by POST /playwright/snapshot-with-regions (#5136). */
export interface PageRegion {
  selector: string
  xpath: string
  rect: RegionRect
  textPreview: string
  role: string
}

export interface SnapshotWithRegionsResult {
  screenshot: string
  regions: PageRegion[]
  viewport: Record<string, unknown>
}

// ===== Composable =====

export function useBrowserSessionData() {
  /**
   * Fetch an existing research-browser session by ID.
   * Returns the parsed JSON session object, or null when the session ID
   * indicates a non-API mode (manual-browser / unified-browser).
   */
  async function fetchSession(sessionId: string): Promise<BrowserSessionResponse | null> {
    if (!sessionId || sessionId === 'manual-browser' || sessionId === 'unified-browser') {
      return null
    }
    try {
      return await apiClient.get<BrowserSessionResponse>(
        `${getApiBase()}/research-browser/browser/${sessionId}`
      )
    } catch (err) {
      logger.warn('Could not get session info, using manual mode', err)
      return null
    }
  }

  /**
   * Probe the Playwright health endpoint.
   * Returns the raw Response so callers can inspect `.ok`.
   * fetchWithAuth retained: caller inspects raw Response.ok to distinguish
   * healthy vs. unavailable — apiClient throws on non-2xx losing that distinction — exempt from Wave 5 (#6224)
   */
  async function fetchPlaywrightHealth(playwrightApiUrl: string): Promise<Response | null> {
    try {
      return await fetchWithAuth(`${playwrightApiUrl}/health`) // fetchWithAuth retained: raw Response.ok needed by caller — exempt from Wave 5 (#6224)
    } catch (err) {
      logger.warn('Playwright health check failed', err)
      return null
    }
  }

  /**
   * Navigate Playwright to a URL.
   */
  async function navigateTo(
    playwrightApiUrl: string,
    url: string,
    sessionId: string
  ): Promise<PlaywrightNavigationResponse | null> {
    try {
      return await apiClient.post<PlaywrightNavigationResponse>(`${playwrightApiUrl}/navigate`, {
        url,
        session_id: sessionId
      })
    } catch (err) {
      logger.warn('Playwright navigation failed, relying on VNC', err)
      return null
    }
  }

  /**
   * Playwright back navigation.
   */
  async function navigateBack(): Promise<PlaywrightNavigationResponse> {
    return await apiClient.post<PlaywrightNavigationResponse>(
      `${getApiBase()}/playwright/back`
    )
  }

  /**
   * Playwright forward navigation.
   */
  async function navigateForward(): Promise<PlaywrightNavigationResponse> {
    return await apiClient.post<PlaywrightNavigationResponse>(
      `${getApiBase()}/playwright/forward`
    )
  }

  /**
   * Playwright page reload.
   */
  async function reloadPage(): Promise<PlaywrightNavigationResponse> {
    return await apiClient.post<PlaywrightNavigationResponse>(
      `${getApiBase()}/playwright/reload`
    )
  }

  /**
   * Run a DuckDuckGo web search via Playwright.
   */
  async function webSearch(playwrightApiUrl: string, query: string): Promise<unknown> {
    return await apiClient.post<unknown>(`${playwrightApiUrl}/search`, {
      query,
      search_engine: 'duckduckgo'
    })
  }

  /**
   * Run Playwright frontend tests against the current origin.
   */
  async function runFrontendTests(playwrightApiUrl: string): Promise<unknown> {
    return await apiClient.post<unknown>(`${playwrightApiUrl}/test-frontend`, {
      frontend_url: window.location.origin
    })
  }

  /**
   * Send a test automation message via Playwright.
   */
  async function sendTestMessage(playwrightApiUrl: string): Promise<unknown> {
    return await apiClient.post<unknown>(`${playwrightApiUrl}/send-test-message`, {
      message: 'Test message from browser automation',
      frontend_url: window.location.origin
    })
  }

  /**
   * Take a screenshot of a research browser session and return detected DOM regions.
   *
   * Calls POST /playwright/snapshot-with-regions (#5136 / #6446). Returns a
   * base64 PNG screenshot together with a list of interactive DOM regions so
   * the caller can display an overlay for scraping-template creation.
   *
   * The backend wraps the response in DataResponse[SnapshotWithRegionsResponse],
   * so the parsed JSON shape is { data: { screenshot, regions, viewport } }.
   * Backend sends `text_preview` (snake_case) — mapped here to `textPreview`.
   */
  async function snapshotWithRegions(
    sessionId: string,
    goal = ''
  ): Promise<SnapshotWithRegionsResult> {
    const envelope = await apiClient.post<{ data: Record<string, unknown> }>(
      `${getApiBase()}/playwright/snapshot-with-regions`,
      { session_id: sessionId, goal }
    )
    const payload = envelope?.data ?? (envelope as unknown as Record<string, unknown>)
    const rawRegions = (payload.regions as Array<Record<string, unknown>>) ?? []
    return {
      screenshot: (payload.screenshot as string) ?? '',
      regions: rawRegions.map(r => ({
        selector: (r.selector as string) ?? '',
        xpath: (r.xpath as string) ?? '',
        rect: (r.rect as RegionRect) ?? { x: 0, y: 0, w: 0, h: 0 },
        textPreview: (r.text_preview as string) ?? '',
        role: (r.role as string) ?? '',
      })),
      viewport: (payload.viewport as Record<string, unknown>) ?? {},
    }
  }

  async function aiProposeRegions(
    sessionId: string,
    goal: string
  ): Promise<PageRegion[]> {
    const envelope = await apiClient.post<{ data: Record<string, unknown> }>(
      `${getApiBase()}/playwright/ai-propose-regions`,
      { session_id: sessionId, goal }
    )
    const payload = envelope?.data ?? (envelope as unknown as Record<string, unknown>)
    const rawRegions = (payload.proposed_regions as Array<Record<string, unknown>>) ?? []
    return rawRegions.map(r => ({
      selector: (r.selector as string) ?? '',
      xpath: (r.xpath as string) ?? '',
      rect: (r.rect as RegionRect) ?? { x: 0, y: 0, w: 0, h: 0 },
      textPreview: (r.text_preview as string) ?? '',
      role: (r.role as string) ?? '',
    }))
  }

  return {
    fetchSession,
    fetchPlaywrightHealth,
    navigateTo,
    navigateBack,
    navigateForward,
    reloadPage,
    webSearch,
    runFrontendTests,
    sendTestMessage,
    snapshotWithRegions,
    aiProposeRegions,
  }
}
