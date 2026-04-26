// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
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
      return (await apiClient.get(
        `${getApiBase()}/research-browser/browser/${sessionId}`
      )) as BrowserSessionResponse
    } catch (err) {
      logger.warn('Could not get session info, using manual mode', err)
      return null
    }
  }

  /**
   * Probe the Playwright health endpoint.
   * Returns the raw Response so callers can inspect `.ok`.
   */
  async function fetchPlaywrightHealth(playwrightApiUrl: string): Promise<Response | null> {
    try {
      return await fetchWithAuth(`${playwrightApiUrl}/health`)
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
      return (await apiClient.post(`${playwrightApiUrl}/navigate`, {
        url,
        session_id: sessionId
      })) as unknown as PlaywrightNavigationResponse
    } catch (err) {
      logger.warn('Playwright navigation failed, relying on VNC', err)
      return null
    }
  }

  /**
   * Playwright back navigation.
   */
  async function navigateBack(): Promise<PlaywrightNavigationResponse> {
    return (await apiClient.post(
      `${getApiBase()}/playwright/back`
    )) as unknown as PlaywrightNavigationResponse
  }

  /**
   * Playwright forward navigation.
   */
  async function navigateForward(): Promise<PlaywrightNavigationResponse> {
    return (await apiClient.post(
      `${getApiBase()}/playwright/forward`
    )) as unknown as PlaywrightNavigationResponse
  }

  /**
   * Playwright page reload.
   */
  async function reloadPage(): Promise<PlaywrightNavigationResponse> {
    return (await apiClient.post(
      `${getApiBase()}/playwright/reload`
    )) as unknown as PlaywrightNavigationResponse
  }

  /**
   * Run a DuckDuckGo web search via Playwright.
   */
  async function webSearch(playwrightApiUrl: string, query: string): Promise<unknown> {
    return await apiClient.post(`${playwrightApiUrl}/search`, {
      query,
      search_engine: 'duckduckgo'
    })
  }

  /**
   * Run Playwright frontend tests against the current origin.
   */
  async function runFrontendTests(playwrightApiUrl: string): Promise<unknown> {
    return await apiClient.post(`${playwrightApiUrl}/test-frontend`, {
      frontend_url: window.location.origin
    })
  }

  /**
   * Send a test automation message via Playwright.
   */
  async function sendTestMessage(playwrightApiUrl: string): Promise<unknown> {
    return await apiClient.post(`${playwrightApiUrl}/send-test-message`, {
      message: 'Test message from browser automation',
      frontend_url: window.location.origin
    })
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
    sendTestMessage
  }
}
