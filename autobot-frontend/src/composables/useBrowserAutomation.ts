// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Browser Automation Composable
 * Issue #900 - Browser Automation Dashboard
 */

import { ref, onMounted, onUnmounted } from 'vue'
import ApiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'

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
  const scripts = ref<AutomationScript[]>([])
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  let pollingInterval: ReturnType<typeof setInterval> | null = null

  // ===== API Methods =====

  async function fetchWorkerStatus(): Promise<void> {
    try {
      const data = await ApiClient.get('/api/browser/status')
      workerStatus.value = data
      logger.debug('Fetched worker status:', data)
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch worker status'
      logger.error('Failed to fetch worker status:', err)
      error.value = message
    }
  }

  async function launchSession(url?: string): Promise<BrowserSession | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/browser/launch', { url: url || 'about:blank' })
      sessions.value.push(data.session)
      currentSession.value = data.session
      logger.debug('Launched browser session:', data.session)
      return data.session
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to launch session'
      logger.error('Failed to launch session:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function closeSession(sessionId: string): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      await ApiClient.post('/api/browser/close', { session_id: sessionId })
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      if (currentSession.value?.id === sessionId) {
        currentSession.value = null
      }
      logger.debug('Closed session:', sessionId)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to close session'
      logger.error('Failed to close session:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function fetchSessions(): Promise<void> {
    try {
      const data = await ApiClient.get('/api/browser/sessions')
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
      const data = await ApiClient.get(`/api/browser/session/${sessionId}`)
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
    isLoading.value = true
    error.value = null
    try {
      await ApiClient.post('/api/browser/navigate', { session_id: sessionId, url })
      logger.debug('Navigated to:', url)
      await fetchSessions()
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to navigate'
      logger.error('Failed to navigate:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function click(sessionId: string, selector: string): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      await ApiClient.post('/api/browser/click', { session_id: sessionId, selector })
      logger.debug('Clicked element:', selector)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to click'
      logger.error('Failed to click:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function type(sessionId: string, selector: string, text: string): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      await ApiClient.post('/api/browser/type', { session_id: sessionId, selector, text })
      logger.debug('Typed text into:', selector)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to type'
      logger.error('Failed to type:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  async function takeScreenshot(sessionId: string): Promise<ScreenshotResult | null> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/browser/screenshot', { session_id: sessionId })
      screenshots.value.unshift(data)
      logger.debug('Captured screenshot')
      return data
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to take screenshot'
      logger.error('Failed to take screenshot:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function executeScript(sessionId: string, script: string): Promise<unknown> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/browser/execute', { session_id: sessionId, script })
      logger.debug('Executed script, result:', data.result)
      return data.result
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to execute script'
      logger.error('Failed to execute script:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function runAutomationScript(script: string): Promise<unknown> {
    isLoading.value = true
    error.value = null
    try {
      const data = await ApiClient.post('/api/browser/automation/run', { script })
      logger.debug('Automation script completed:', data)
      return data.result
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to run automation'
      logger.error('Failed to run automation:', err)
      error.value = message
      return null
    } finally {
      isLoading.value = false
    }
  }

  async function deleteSession(sessionId: string): Promise<boolean> {
    isLoading.value = true
    error.value = null
    try {
      await ApiClient.delete(`/api/browser/session/${sessionId}`)
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
      logger.debug('Deleted session:', sessionId)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete session'
      logger.error('Failed to delete session:', err)
      error.value = message
      return false
    } finally {
      isLoading.value = false
    }
  }

  // ===== Polling Methods =====

  function startPolling(): void {
    if (pollingInterval) return
    logger.debug(`Starting polling with interval: ${pollInterval}ms`)
    pollingInterval = setInterval(() => {
      fetchWorkerStatus()
      fetchSessions()
    }, pollInterval)
  }

  function stopPolling(): void {
    if (pollingInterval) {
      clearInterval(pollingInterval)
      pollingInterval = null
      logger.debug('Polling stopped')
    }
  }

  // ===== Lifecycle =====

  onMounted(() => {
    if (autoFetch) {
      Promise.all([fetchWorkerStatus(), fetchSessions()])
    }
    if (pollInterval > 0) {
      startPolling()
    }
  })

  onUnmounted(() => {
    stopPolling()
  })

  return {
    // State
    workerStatus,
    sessions,
    currentSession,
    screenshots,
    scripts,
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
    startPolling,
    stopPolling,
  }
}

export default useBrowserAutomation
