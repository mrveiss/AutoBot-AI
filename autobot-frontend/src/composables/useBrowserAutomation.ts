// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Browser Automation Composable
 * Issue #900 - Browser Automation Dashboard
 */

import { ref, onMounted, getCurrentInstance } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import { getApiBase } from '@/config/ssot-config'
import { usePollingJob } from '@/composables/usePollingJob'
import { useLoadingState } from '@/composables/useLoadingState'
import type { components } from '@/types/generated/api'

const logger = createLogger('useBrowserAutomation')

// Backend response shapes (source of truth: generated api.ts)
type BrowserMcpStatusResponse = components['schemas']['BrowserMcpStatusResponse']
type BrowserSessionListData = components['schemas']['BrowserSessionListData']
type DataResponseBrowserSessionList = components['schemas']['DataResponse_BrowserSessionListData_']

// ===== Type Definitions =====

export interface BrowserWorkerStatus {
  status: 'online' | 'offline' | 'degraded'
  active_sessions: number
  max_sessions: number
  cpu_usage: number
  memory_usage: number
  uptime_seconds: number
}

export interface BrowserSession {
  id: string
  url: string
  title: string
  status: 'active' | 'idle' | 'error'
  created_at: string
  last_activity: string
  viewport: {
    width: number
    height: number
  }
}

export interface BrowserAction {
  type: 'navigate' | 'click' | 'type' | 'screenshot' | 'execute'
  session_id: string
  params: Record<string, unknown>
}

/** Wire shape returned by POST /api/browser/mcp/screenshot (#12894). */
interface BrowserScreenshotResponse {
  success: boolean
  action: string
  base64_image?: string
  mime_type: string
  timestamp: string
}

export interface ScreenshotResult {
  session_id: string
  image_data: string
  timestamp: string
  format: 'png' | 'jpeg'
}

export interface AutomationScript {
  id: string
  name: string
  description: string
  script: string
  status: 'idle' | 'running' | 'completed' | 'failed'
  last_run?: string
  result?: unknown
}

export interface UseBrowserAutomationOptions {
  autoFetch?: boolean
  pollInterval?: number
}

// ===== Response Mapping Helpers =====

/**
 * Map the Browser MCP bridge status (`/api/browser/mcp/status`) onto the
 * dashboard's BrowserWorkerStatus shape. The MCP bridge only reports Browser
 * VM connectivity, so resource metrics (cpu/memory/uptime) and session caps
 * that the bridge does not expose degrade to safe defaults rather than being
 * fabricated. active_sessions is populated separately from fetchSessions().
 */
function mapMcpStatusToWorkerStatus(data: BrowserMcpStatusResponse): BrowserWorkerStatus {
  const vmStatus = String((data.browser_vm as Record<string, unknown>)?.status ?? '')
  let status: BrowserWorkerStatus['status'] = 'offline'
  if (vmStatus === 'healthy') {
    status = 'online'
  } else if (vmStatus === 'degraded') {
    status = 'degraded'
  }

  return {
    status,
    active_sessions: 0, // populated by fetchSessions() (MCP status has no count)
    max_sessions: 0, // not reported by the MCP bridge
    cpu_usage: 0, // not reported by the MCP bridge
    memory_usage: 0, // not reported by the MCP bridge
    uptime_seconds: 0, // not reported by the MCP bridge
  }
}

/**
 * Map a single research-browser session record onto BrowserSession.
 * The backend session dict (research_browser.py list_sessions) exposes
 * session_id/current_url/status/created_at/last_activity; page title and
 * viewport are not tracked server-side and degrade to safe defaults.
 */
function mapSessionRecord(record: Record<string, unknown>): BrowserSession {
  const rawStatus = String(record.status ?? '')
  let status: BrowserSession['status'] = 'idle'
  if (rawStatus === 'error' || rawStatus === 'failed') {
    status = 'error'
  } else if (rawStatus === 'active' || rawStatus === 'running' || rawStatus === 'navigating') {
    status = 'active'
  }

  const createdAt = typeof record.created_at === 'string' ? record.created_at : ''

  return {
    id: String(record.session_id ?? ''),
    url: typeof record.current_url === 'string' ? record.current_url : '',
    title: '', // not tracked server-side
    status,
    created_at: createdAt,
    last_activity: typeof record.last_activity === 'string' ? record.last_activity : createdAt,
    viewport: { width: 0, height: 0 }, // not tracked server-side
  }
}

// ===== Composable Implementation =====

export function useBrowserAutomation(options: UseBrowserAutomationOptions = {}) {
  const { autoFetch = true, pollInterval = 5000 } = options

  // State
  const workerStatus = ref<BrowserWorkerStatus | null>(null)
  const sessions = ref<BrowserSession[]>([])
  const currentSession = ref<BrowserSession | null>(null)
  const screenshots = ref<ScreenshotResult[]>([])
  const { isLoading, wrap } = useLoadingState()
  const error = ref<string | null>(null)

  // ===== API Methods =====

  async function fetchWorkerStatus(): Promise<void> {
    try {
      const data = await ApiClient.get<BrowserMcpStatusResponse>(`${getApiBase()}/browser/mcp/status`)
      const mapped = mapMcpStatusToWorkerStatus(data)
      // Preserve the active_sessions count already derived from fetchSessions().
      mapped.active_sessions = sessions.value.length
      workerStatus.value = mapped
      logger.debug('Fetched worker status:', mapped)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch worker status'
      logger.error('Failed to fetch worker status:', err)
      error.value = message
    }
  }

  async function launchSession(url?: string): Promise<BrowserSession | null> {
    error.value = null
    return wrap(async () => {
      const data = await ApiClient.post<{ session: BrowserSession }>(`${getApiBase()}/browser/launch`, { url: url || 'about:blank' })
      sessions.value.push(data.session)
      currentSession.value = data.session
      logger.debug('Launched browser session:', data.session)
      return data.session
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to launch session'
      logger.error('Failed to launch session:', err)
      error.value = message
      return null
    })
  }

  async function closeSession(sessionId: string): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      await ApiClient.post<unknown>(`${getApiBase()}/browser/close`, { session_id: sessionId })
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      if (currentSession.value?.id === sessionId) {
        currentSession.value = null
      }
      logger.debug('Closed session:', sessionId)
      return true
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to close session'
      logger.error('Failed to close session:', err)
      error.value = message
      return false
    })
  }

  async function fetchSessions(): Promise<void> {
    try {
      // research-browser is a distinct router prefix from /browser (MCP bridge).
      // ApiClient.get returns parsed JSON directly; DataResponse wraps the
      // payload under `data`.
      const response = await ApiClient.get<DataResponseBrowserSessionList>(
        `${getApiBase()}/research-browser/sessions`,
      )
      const listData: BrowserSessionListData | null | undefined = response?.data
      const records = listData?.sessions ?? []
      sessions.value = records.map(mapSessionRecord)
      // Keep the worker-status session count in sync when it is present.
      if (workerStatus.value) {
        workerStatus.value.active_sessions = sessions.value.length
      }
      logger.debug('Fetched sessions:', sessions.value.length)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch sessions'
      logger.error('Failed to fetch sessions:', err)
      error.value = message
    }
  }

  async function getSession(sessionId: string): Promise<BrowserSession | null> {
    try {
      const data = await ApiClient.get<BrowserSession>(`${getApiBase()}/browser/session/${sessionId}`)
      currentSession.value = data
      logger.debug('Fetched session details:', data)
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch session'
      logger.error('Failed to fetch session:', err)
      error.value = message
      return null
    }
  }

  async function navigate(sessionId: string, url: string): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      await ApiClient.post<unknown>(`${getApiBase()}/browser/mcp/navigate`, { session_id: sessionId, url })
      logger.debug('Navigated to:', url)
      await fetchSessions()
      return true
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to navigate'
      logger.error('Failed to navigate:', err)
      error.value = message
      return false
    })
  }

  async function click(sessionId: string, selector: string): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      await ApiClient.post<unknown>(`${getApiBase()}/browser/mcp/click`, { session_id: sessionId, selector })
      logger.debug('Clicked element:', selector)
      return true
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to click'
      logger.error('Failed to click:', err)
      error.value = message
      return false
    })
  }

  async function type(sessionId: string, selector: string, text: string): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      await ApiClient.post<unknown>(`${getApiBase()}/browser/type`, { session_id: sessionId, selector, text })
      logger.debug('Typed text into:', selector)
      return true
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to type'
      logger.error('Failed to type:', err)
      error.value = message
      return false
    })
  }

  async function takeScreenshot(sessionId: string): Promise<ScreenshotResult | null> {
    error.value = null
    return wrap(async () => {
      // #12894: the route moved to /browser/mcp/screenshot AND its response
      // shape differs from the old one — it returns base64_image/mime_type
      // where callers here consume image_data/format. Rewiring the URL alone
      // would have left every consumer reading undefined, so map it.
      const raw = await ApiClient.post<BrowserScreenshotResponse>(
        `${getApiBase()}/browser/mcp/screenshot`,
        { session_id: sessionId },
      )
      const data: ScreenshotResult = {
        session_id: sessionId,
        image_data: raw.base64_image ?? '',
        timestamp: raw.timestamp,
        format: raw.mime_type === 'image/jpeg' ? 'jpeg' : 'png',
      }
      screenshots.value.unshift(data)
      logger.debug('Captured screenshot')
      return data
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to take screenshot'
      logger.error('Failed to take screenshot:', err)
      error.value = message
      return null
    })
  }

  async function executeScript(sessionId: string, script: string): Promise<unknown> {
    error.value = null
    return wrap(async () => {
      const data = await ApiClient.post<{ result: unknown }>(`${getApiBase()}/browser/execute`, { session_id: sessionId, script })
      logger.debug('Executed script, result:', data.result)
      return data.result
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to execute script'
      logger.error('Failed to execute script:', err)
      error.value = message
      return null
    })
  }

  async function runAutomationScript(script: string): Promise<unknown> {
    error.value = null
    return wrap(async () => {
      const data = await ApiClient.post<{ result: unknown }>(`${getApiBase()}/browser/automation/run`, { script })
      logger.debug('Automation script completed:', data)
      return data.result
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to run automation'
      logger.error('Failed to run automation:', err)
      error.value = message
      return null
    })
  }

  async function deleteSession(sessionId: string): Promise<boolean> {
    error.value = null
    return wrap(async () => {
      await ApiClient.delete<unknown>(`${getApiBase()}/browser/session/${sessionId}`)
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      logger.debug('Deleted session:', sessionId)
      return true
    }).catch((err) => {
      const message = err instanceof Error ? err.message : 'Failed to delete session'
      logger.error('Failed to delete session:', err)
      error.value = message
      return false
    })
  }

  // ===== Polling Methods =====

  const { start: startPolling, stop: stopPolling } = usePollingJob<void>(
    async () => {
      await Promise.all([fetchWorkerStatus(), fetchSessions()])
    },
    { intervalMs: pollInterval }
  )

  // ===== Lifecycle =====

  if (getCurrentInstance()) {
    onMounted(() => {
      if (autoFetch) {
        Promise.all([fetchWorkerStatus(), fetchSessions()])
      }
      if (pollInterval > 0) {
        logger.debug(`Starting polling with interval: ${pollInterval}ms`)
        startPolling('')
      }
    })
  }

  return {
    // State
    workerStatus,
    sessions,
    currentSession,
    screenshots,
    isLoading,
    error,

    // Methods
    fetchWorkerStatus,
    launchSession,
    closeSession,
    fetchSessions,
    getSession,
    navigate,
    click,
    type,
    takeScreenshot,
    executeScript,
    runAutomationScript,
    deleteSession,
    startPolling: () => startPolling(''),
    stopPolling,
  }
}

export default useBrowserAutomation
