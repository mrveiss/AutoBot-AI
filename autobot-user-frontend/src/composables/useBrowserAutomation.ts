// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * Browser Automation Composable
 * Centralized Playwright API interactions for browser automation
 */

import { ref } from 'vue'
import apiClient from '@/utils/ApiClient'
import { createLogger } from '@/utils/debugUtils'
import type {
  AutomationTask,
  MediaItem,
  AutomationRecording,
  BrowserSession,
  TaskStatus,
  TaskType
} from '@/types/browser'

const logger = createLogger('useBrowserAutomation')

export function useBrowserAutomation() {
  const isLoading = ref(false)
  const error = ref<string | null>(null)

  // Task Management
  const tasks = ref<AutomationTask[]>([])

  const createTask = async (
    type: TaskType,
    name: string,
    params: Record<string, unknown>,
    description?: string
  ): Promise<AutomationTask> => {
    const task: AutomationTask = {
      id: `task-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      type,
      status: 'queued',
      name,
      description,
      params,
      createdAt: new Date(),
      progress: 0
    }

    tasks.value.push(task)
    logger.info(`Created task: ${task.id}`, { type, name })

    // Execute task asynchronously
    executeTask(task)

    return task
  }

  const executeTask = async (task: AutomationTask) => {
    try {
      task.status = 'running'
      task.startedAt = new Date()

      let result: unknown = null

      switch (task.type) {
        case 'navigate':
          result = await apiClient.post('/api/playwright/navigate', {
            url: task.params.url,
            wait_until: task.params.waitUntil || 'networkidle',
            timeout: task.params.timeout || 30000
          })
          break

        case 'screenshot':
          result = await apiClient.post('/api/playwright/screenshot', {
            url: task.params.url,
            full_page: task.params.fullPage !== false,
            wait_timeout: task.params.waitTimeout || 5000
          })
          break

        case 'search':
          result = await apiClient.post('/api/playwright/search', {
            query: task.params.query,
            search_engine: task.params.searchEngine || 'duckduckgo',
            max_results: task.params.maxResults || 5
          })
          break

        case 'test':
          result = await apiClient.post('/api/playwright/test-frontend', {
            frontend_url: task.params.frontendUrl || window.location.origin
          })
          break

        case 'script':
          // Execute custom script (sequence of actions)
          result = await executeScript(task.params.actions)
          break

        default:
          throw new Error(`Unknown task type: ${task.type}`)
      }

      task.result = result
      task.status = 'completed'
      task.completedAt = new Date()
      task.progress = 100

      logger.info(`Task completed: ${task.id}`, { result })
    } catch (err: unknown) {
      task.status = 'failed'
      task.error = (err as Error).message || 'Task execution failed'
      task.completedAt = new Date()

      logger.error(`Task failed: ${task.id}`, err)
    }
  }

  const executeScript = async (actions: Array<Record<string, unknown>>): Promise<unknown> => {
    const results = []
    for (const action of actions) {
      let result: unknown = null

      switch (action.type) {
        case 'navigate':
          result = await apiClient.post('/api/playwright/navigate', {
            url: action.url
          })
          break

        case 'screenshot':
          result = await apiClient.post('/api/playwright/screenshot', {
            url: action.url || window.location.href
          })
          break

        case 'wait':
          await new Promise(resolve => setTimeout(resolve, action.duration || 1000))
          result = { waited: action.duration }
          break

        default:
          logger.warn(`Unknown action type: ${action.type}`)
      }

      results.push(result)
    }

    return results
  }

  const cancelTask = (taskId: string) => {
    const task = tasks.value.find(t => t.id === taskId)
    if (task && (task.status === 'queued' || task.status === 'running')) {
      task.status = 'cancelled'
      task.completedAt = new Date()
      logger.info(`Task cancelled: ${taskId}`)
    }
  }

  const getTaskById = (taskId: string): AutomationTask | undefined => {
    return tasks.value.find(t => t.id === taskId)
  }

  const clearCompletedTasks = () => {
    tasks.value = tasks.value.filter(
      t => t.status === 'queued' || t.status === 'running'
    )
    logger.info('Cleared completed tasks')
  }

  // Media Gallery
  const mediaItems = ref<MediaItem[]>([])

  const captureScreenshot = async (url: string, pageTitle?: string): Promise<MediaItem> => {
    isLoading.value = true
    error.value = null

    try {
      const result = await apiClient.post('/api/playwright/screenshot', {
        url,
        full_page: true,
        wait_timeout: 5000
      })

      const mediaItem: MediaItem = {
        id: `media-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        type: 'screenshot',
        url: result.screenshot_url || result.path || '',
        filename: `screenshot-${Date.now()}.png`,
        size: result.size || 0,
        width: result.width,
        height: result.height,
        capturedAt: new Date(),
        pageUrl: url,
        pageTitle
      }

      mediaItems.value.unshift(mediaItem)
      logger.info('Screenshot captured', { mediaItem })

      return mediaItem
    } catch (err: unknown) {
      error.value = (err as Error).message || 'Failed to capture screenshot'
      logger.error('Screenshot capture failed', err)
      throw err
    } finally {
      isLoading.value = false
    }
  }

  const deleteMediaItem = (mediaId: string) => {
    mediaItems.value = mediaItems.value.filter(m => m.id !== mediaId)
    logger.info(`Media item deleted: ${mediaId}`)
  }

  const clearMediaGallery = () => {
    mediaItems.value = []
    logger.info('Media gallery cleared')
  }

  // Automation Recording
  const recordings = ref<AutomationRecording[]>([])
  const currentRecording = ref<AutomationRecording | null>(null)
  const isRecording = ref(false)

  const startRecording = (name: string, description?: string) => {
    currentRecording.value = {
      id: `rec-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name,
      description,
      actions: [],
      createdAt: new Date(),
      updatedAt: new Date(),
      duration: 0
    }
    isRecording.value = true
    logger.info('Started recording', { name })
  }

  const stopRecording = (): AutomationRecording | null => {
    if (currentRecording.value) {
      const recording = { ...currentRecording.value }
      recordings.value.unshift(recording)
      currentRecording.value = null
      isRecording.value = false
      logger.info('Stopped recording', { id: recording.id })
      return recording
    }
    return null
  }

  const addRecordingAction = (
    type: string,
    description: string,
    data: Record<string, unknown> = {}
  ) => {
    if (currentRecording.value) {
      const action = {
        id: `action-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
        type,
        description,
        timestamp: Date.now(),
        ...data
      }

      currentRecording.value.actions.push(action)
      currentRecording.value.updatedAt = new Date()
      currentRecording.value.duration = Date.now() - currentRecording.value.createdAt.getTime()

      logger.debug('Action recorded', { action })
    }
  }

  const playbackRecording = async (recordingId: string) => {
    const recording = recordings.value.find(r => r.id === recordingId)
    if (!recording) {
      throw new Error(`Recording not found: ${recordingId}`)
    }

    logger.info('Playing back recording', { id: recordingId })

    const task = await createTask(
      'script',
      `Playback: ${recording.name}`,
      { actions: recording.actions },
      `Playing back recorded automation`
    )

    return task
  }

  const deleteRecording = (recordingId: string) => {
    recordings.value = recordings.value.filter(r => r.id !== recordingId)
    logger.info(`Recording deleted: ${recordingId}`)
  }

  // Browser Session Management
  const sessions = ref<BrowserSession[]>([])

  const createSession = (name: string, url: string, persistent: boolean = false): BrowserSession => {
    const session: BrowserSession = {
      id: `session-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      name,
      url,
      status: 'active',
      createdAt: new Date(),
      lastActivityAt: new Date(),
      persistent
    }

    sessions.value.push(session)
    logger.info('Session created', { id: session.id, name })

    return session
  }

  const closeSession = (sessionId: string) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.status = 'closed'
      logger.info(`Session closed: ${sessionId}`)
    }
  }

  const deleteSession = (sessionId: string) => {
    sessions.value = sessions.value.filter(s => s.id !== sessionId)
    logger.info(`Session deleted: ${sessionId}`)
  }

  const updateSessionActivity = (sessionId: string) => {
    const session = sessions.value.find(s => s.id === sessionId)
    if (session) {
      session.lastActivityAt = new Date()
      session.status = 'active'
    }
  }

  // Playwright Service Status
  const checkPlaywrightStatus = async () => {
    try {
      const status = await apiClient.get('/api/playwright/status')
      logger.info('Playwright status', status)
      return status
    } catch (err: unknown) {
      logger.error('Failed to check Playwright status', err)
      throw err
    }
  }

  const checkPlaywrightHealth = async () => {
    try {
      const health = await apiClient.get('/api/playwright/health')
      return health
    } catch (err: unknown) {
      logger.error('Playwright health check failed', err)
      throw err
    }
  }

  return {
    // State
    isLoading,
    error,
    tasks,
    mediaItems,
    recordings,
    currentRecording,
    isRecording,
    sessions,

    // Task Management
    createTask,
    cancelTask,
    getTaskById,
    clearCompletedTasks,

    // Media Gallery
    captureScreenshot,
    deleteMediaItem,
    clearMediaGallery,

    // Recording
    startRecording,
    stopRecording,
    addRecordingAction,
    playbackRecording,
    deleteRecording,

    // Session Management
    createSession,
    closeSession,
    deleteSession,
    updateSessionActivity,

    // Service Status
    checkPlaywrightStatus,
    checkPlaywrightHealth
  }
}
