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

const logger = createLogger('useBrowserAutomation')

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
      const data = await ApiClient.get<BrowserWorkerStatus>(`${getApiBase()}/browser/status`)
      workerStatus.value = data
      logger.debug('Fetched worker status:', data)
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
      const data = await ApiClient.get<{ sessions: BrowserSession[] }>(`${getApiBase()}/browser/sessions`)
      sessions.value = data.sessions || []
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
      await ApiClient.post<unknown>(`${getApiBase()}/browser/navigate`, { session_id: sessionId, url })
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
      await ApiClient.post<unknown>(`${getApiBase()}/browser/click`, { session_id: sessionId, selector })
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
      const data = await ApiClient.post<ScreenshotResult>(`${getApiBase()}/browser/screenshot`, { session_id: sessionId })
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
