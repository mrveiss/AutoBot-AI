/**
 * Session Activity Logger Composable
 *
 * Issue #608: User-Centric Session Tracking - Phase 3
 *
 * Provides a centralized way to log user activities within chat sessions.
 * Activities are tracked in the Pinia store and optionally synced to the backend.
 *
 * Usage:
 * ```typescript
 * import { useSessionActivityLogger } from '@/composables/useSessionActivityLogger'
 *
 * const { logTerminalActivity, logFileActivity, logDesktopActivity } = useSessionActivityLogger()
 *
 * // Log terminal command execution
 * logTerminalActivity('ls -la', { exitCode: 0 })
 *
 * // Log file operation
 * logFileActivity('upload', '/path/to/file.txt', { size: 1024 })
 *
 * // Log desktop automation
 * logDesktopActivity('connect', 'Connected to VNC', { host: '172.16.168.20' })
 * ```
 */

import { inject } from 'vue'
import { useChatStore, type SessionActivity } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'
import type { ApiClientType } from '@/plugins/api'

// Create scoped logger
const logger = createLogger('SessionActivityLogger')

/**
 * Activity types supported by the logger
 */
export type ActivityType = SessionActivity['type']

/**
 * Terminal activity subtypes
 */
export type TerminalActivitySubtype =
  | 'command'
  | 'automated_command'
  | 'interrupt'
  | 'control_transfer'
  | 'workflow_start'
  | 'workflow_complete'

/**
 * File activity subtypes
 */
export type FileActivitySubtype =
  | 'upload'
  | 'download'
  | 'view'
  | 'delete'
  | 'rename'
  | 'create_folder'
  | 'navigate'

/**
 * Desktop activity subtypes
 */
export type DesktopActivitySubtype =
  | 'connect'
  | 'disconnect'
  | 'reconnect'
  | 'fullscreen'
  | 'screenshot'

/**
 * Secret usage action types
 * Issue #608: Phase 4 - Secrets vault integration
 */
export type SecretUsageAction =
  | 'access'
  | 'inject'
  | 'copy'
  | 'reveal'

/**
 * Secret type matching backend enum
 */
export type SecretType = 'ssh_key' | 'password' | 'api_key' | 'token' | 'certificate' | 'database_url' | 'other'

/**
 * Options for activity logging
 */
export interface ActivityLogOptions {
  /** Sync activity to backend immediately (default: false for batching) */
  syncImmediately?: boolean
  /** Secrets used during this activity (for tracking) */
  secretsUsed?: string[]
  /** User ID override (defaults to current user) */
  userId?: string
}

/**
 * Return type for the composable
 */
export interface UseSessionActivityLoggerReturn {
  /**
   * Log a terminal activity
   */
  logTerminalActivity: (
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ) => string | null

  /**
   * Log a file operation activity
   */
  logFileActivity: (
    subtype: FileActivitySubtype,
    path: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ) => string | null

  /**
   * Log a desktop/VNC activity
   */
  logDesktopActivity: (
    subtype: DesktopActivitySubtype,
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ) => string | null

  /**
   * Log a browser automation activity
   */
  logBrowserActivity: (
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ) => string | null

  /**
   * Log secret usage within a session
   * Issue #608: Phase 4 - Secrets vault integration
   */
  logSecretUsage: (
    action: SecretUsageAction,
    secretId: string,
    secretName: string,
    secretType: SecretType,
    metadata?: Record<string, unknown>
  ) => string | null

  /**
   * Link a secret to the current session
   * Issue #608: Phase 4 - Secrets vault integration
   */
  linkSecretToSession: (
    secretId: string,
    secretName: string,
    secretType: SecretType,
    scope: 'user' | 'session' | 'shared'
  ) => boolean

  /**
   * Get activities for the current session
   */
  getActivities: (filters?: {
    type?: ActivityType
    userId?: string
  }) => SessionActivity[]

  /**
   * Sync pending activities to backend
   */
  syncActivitiesToBackend: () => Promise<boolean>
}

// Track pending activities for batch sync
const pendingActivities: Array<{
  sessionId: string
  activity: SessionActivity
}> = []

// Batch sync interval (5 seconds)
let syncIntervalId: ReturnType<typeof setInterval> | null = null

/**
 * Session Activity Logger composable
 *
 * @returns Activity logging utilities
 */
export function useSessionActivityLogger(): UseSessionActivityLoggerReturn {
  const chatStore = useChatStore()
  const apiClient = inject<ApiClientType>('apiClient')

  // Get current user ID from store or fallback
  const getCurrentUserId = (): string => {
    const currentSession = chatStore.currentSession
    return currentSession?.owner?.id || 'anonymous'
  }

  // Get current session ID
  const getCurrentSessionId = (): string | null => {
    return chatStore.currentSession?.id || null
  }

  /**
   * Internal function to log any activity type
   */
  const logActivity = (
    type: ActivityType,
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ): string | null => {
    const sessionId = getCurrentSessionId()
    if (!sessionId) {
      logger.warn('[Issue #608] Cannot log activity: no active session')
      return null
    }

    const userId = options?.userId || getCurrentUserId()

    // Add activity to store
    const activityId = chatStore.addSessionActivity(sessionId, {
      type,
      userId,
      content,
      secretsUsed: options?.secretsUsed,
      metadata
    })

    if (activityId) {
      logger.debug(`[Issue #608] Logged ${type} activity: ${content.substring(0, 50)}...`)

      // Track for batch sync unless immediate sync requested
      if (options?.syncImmediately && apiClient) {
        syncSingleActivity(sessionId, activityId)
      } else {
        const session = chatStore.sessions.find(s => s.id === sessionId)
        const activity = session?.activities?.find(a => a.id === activityId)
        if (activity) {
          pendingActivities.push({ sessionId, activity })
          startBatchSyncIfNeeded()
        }
      }
    }

    return activityId
  }

  /**
   * Sync a single activity immediately
   */
  const syncSingleActivity = async (
    sessionId: string,
    activityId: string
  ): Promise<void> => {
    if (!apiClient) return

    const session = chatStore.sessions.find(s => s.id === sessionId)
    const activity = session?.activities?.find(a => a.id === activityId)
    if (!activity) return

    try {
      await apiClient.post(`/chat/sessions/${sessionId}/activities`, {
        activity_id: activity.id,
        type: activity.type,
        user_id: activity.userId,
        content: activity.content,
        secrets_used: activity.secretsUsed || [],
        metadata: activity.metadata || {},
        timestamp: activity.timestamp.toISOString()
      })
      logger.debug(`[Issue #608] Synced activity ${activityId} to backend`)
    } catch (error) {
      logger.warn(`[Issue #608] Failed to sync activity ${activityId}:`, error)
    }
  }

  /**
   * Start batch sync interval if not already running
   */
  const startBatchSyncIfNeeded = (): void => {
    if (syncIntervalId) return

    syncIntervalId = setInterval(async () => {
      if (pendingActivities.length > 0) {
        await syncActivitiesToBackend()
      }
    }, 5000) // Sync every 5 seconds
  }

  /**
   * Log terminal activity
   */
  const logTerminalActivity = (
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ): string | null => {
    return logActivity('terminal', content, metadata, options)
  }

  /**
   * Log file activity
   */
  const logFileActivity = (
    subtype: FileActivitySubtype,
    path: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ): string | null => {
    const content = `${subtype}: ${path}`
    return logActivity('file', content, { ...metadata, subtype, path }, options)
  }

  /**
   * Log desktop/VNC activity
   */
  const logDesktopActivity = (
    subtype: DesktopActivitySubtype,
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ): string | null => {
    return logActivity('desktop', content, { ...metadata, subtype }, options)
  }

  /**
   * Log browser automation activity
   */
  const logBrowserActivity = (
    content: string,
    metadata?: Record<string, unknown>,
    options?: ActivityLogOptions
  ): string | null => {
    return logActivity('browser', content, metadata, options)
  }

  /**
   * Log secret usage within a session
   * Issue #608: Phase 4 - Secrets vault integration
   */
  const logSecretUsage = (
    action: SecretUsageAction,
    secretId: string,
    secretName: string,
    secretType: SecretType,
    metadata?: Record<string, unknown>
  ): string | null => {
    const sessionId = getCurrentSessionId()
    if (!sessionId) {
      logger.warn('[Issue #608] Cannot log secret usage: no active session')
      return null
    }

    const content = `Secret ${action}: ${secretName} (${secretType})`

    // Increment usage count in the store
    chatStore.incrementSecretUsage(sessionId, secretId)

    // Log as terminal activity with secret reference
    return logActivity('terminal', content, {
      ...metadata,
      subtype: 'secret_usage',
      action,
      secretId,
      secretName,
      secretType
    }, {
      secretsUsed: [secretId],
      syncImmediately: true // Secret usage is important, sync immediately
    })
  }

  /**
   * Link a secret to the current session
   * Issue #608: Phase 4 - Secrets vault integration
   */
  const linkSecretToSession = (
    secretId: string,
    secretName: string,
    secretType: SecretType,
    scope: 'user' | 'session' | 'shared'
  ): boolean => {
    const sessionId = getCurrentSessionId()
    if (!sessionId) {
      logger.warn('[Issue #608] Cannot link secret: no active session')
      return false
    }

    const userId = getCurrentUserId()

    // Map SecretType to SessionSecret type
    const sessionSecretType = secretType === 'ssh_key' ? 'ssh_key' :
                              secretType === 'api_key' ? 'api_key' :
                              secretType === 'token' ? 'token' :
                              secretType === 'password' ? 'password' :
                              secretType === 'certificate' ? 'certificate' : 'api_key'

    return chatStore.addSessionSecret(sessionId, {
      id: secretId,
      name: secretName,
      type: sessionSecretType,
      scope,
      ownerId: userId
    })
  }

  /**
   * Get activities for the current session
   */
  const getActivities = (filters?: {
    type?: ActivityType
    userId?: string
  }): SessionActivity[] => {
    const sessionId = getCurrentSessionId()
    if (!sessionId) return []

    return chatStore.getSessionActivities(sessionId, filters)
  }

  /**
   * Sync all pending activities to backend
   */
  const syncActivitiesToBackend = async (): Promise<boolean> => {
    if (!apiClient || pendingActivities.length === 0) {
      return true
    }

    // Group activities by session
    const bySession = new Map<string, SessionActivity[]>()
    for (const { sessionId, activity } of pendingActivities) {
      if (!bySession.has(sessionId)) {
        bySession.set(sessionId, [])
      }
      bySession.get(sessionId)!.push(activity)
    }

    // Clear pending list
    pendingActivities.length = 0

    // Sync each session's activities
    let success = true
    for (const [sessionId, activities] of bySession) {
      try {
        await apiClient.post(`/chat/sessions/${sessionId}/activities/batch`, {
          activities: activities.map(a => ({
            activity_id: a.id,
            type: a.type,
            user_id: a.userId,
            content: a.content,
            secrets_used: a.secretsUsed || [],
            metadata: a.metadata || {},
            timestamp: a.timestamp.toISOString()
          }))
        })
        logger.debug(`[Issue #608] Synced ${activities.length} activities for session ${sessionId}`)
      } catch (error) {
        logger.warn(`[Issue #608] Failed to sync activities for session ${sessionId}:`, error)
        // Re-add to pending for retry
        activities.forEach(activity => {
          pendingActivities.push({ sessionId, activity })
        })
        success = false
      }
    }

    return success
  }

  return {
    logTerminalActivity,
    logFileActivity,
    logDesktopActivity,
    logBrowserActivity,
    logSecretUsage,
    linkSecretToSession,
    getActivities,
    syncActivitiesToBackend
  }
}

/**
 * Cleanup function to stop batch sync and flush pending activities
 * Call this when the app is being destroyed
 */
export function cleanupActivityLogger(): void {
  if (syncIntervalId) {
    clearInterval(syncIntervalId)
    syncIntervalId = null
  }
  // Clear pending activities
  pendingActivities.length = 0
}
