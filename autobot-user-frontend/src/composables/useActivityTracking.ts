/**
 * Activity Tracking Composable
 *
 * Issue #874: Frontend Collaborative Session UI (#608 Phase 6)
 *
 * Enhanced wrapper around useSessionActivityLogger with real-time collaboration features.
 * Combines activity logging with WebSocket broadcasting for multi-user sessions.
 */

import { computed, onMounted, onUnmounted, type ComputedRef, type Ref } from 'vue'
import {
  useSessionActivityLogger,
  type ActivityType,
  type SecretType,
  type SecretUsageAction,
  type FileActivitySubtype,
  type DesktopActivitySubtype
} from './useSessionActivityLogger'
import { useSessionCollaboration, type CollaboratorActivity } from './useSessionCollaboration'
import { useChatStore, type SessionActivity } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('ActivityTracking')

/**
 * Activity filter options
 */
export interface ActivityFilters {
  type?: ActivityType
  userId?: string
  startDate?: Date
  endDate?: Date
  hasSecrets?: boolean
}

/**
 * Activity statistics
 */
export interface ActivityStats {
  total: number
  byType: Record<ActivityType, number>
  byUser: Record<string, number>
  secretsUsed: number
  lastActivityAt?: Date
}

/**
 * Return type for the composable
 */
export interface UseActivityTrackingReturn {
  /** All activities for current session */
  activities: ComputedRef<SessionActivity[]>
  /** Recent collaborator activities */
  collaboratorActivities: Ref<CollaboratorActivity[]>
  /** Activity statistics */
  stats: ComputedRef<ActivityStats>
  /** Is tracking active */
  isTracking: ComputedRef<boolean>

  /** Track terminal activity */
  trackTerminal: (command: string, metadata?: Record<string, unknown>) => void
  /** Track file operation */
  trackFile: (operation: FileActivitySubtype, path: string, metadata?: Record<string, unknown>) => void
  /** Track desktop action */
  trackDesktop: (action: DesktopActivitySubtype, details: string, metadata?: Record<string, unknown>) => void
  /** Track browser action */
  trackBrowser: (action: string, metadata?: Record<string, unknown>) => void
  /** Track secret usage */
  trackSecretUsage: (
    action: SecretUsageAction,
    secretId: string,
    secretName: string,
    secretType: SecretType
  ) => void

  /** Get filtered activities */
  getFilteredActivities: (filters: ActivityFilters) => SessionActivity[]
  /** Clear all activities for current session */
  clearActivities: () => void
  /** Export activities as JSON */
  exportActivities: () => string
}

/**
 * Activity Tracking composable
 *
 * @returns Activity tracking utilities
 */
export function useActivityTracking(): UseActivityTrackingReturn {
  const chatStore = useChatStore()
  const activityLogger = useSessionActivityLogger()
  const collaboration = useSessionCollaboration()

  // Is tracking enabled
  const isTracking = computed(() => {
    return !!chatStore.currentSession
  })

  // Get all activities for current session
  const activities = computed<SessionActivity[]>(() => {
    if (!chatStore.currentSession?.id) return []
    return activityLogger.getActivities()
  })

  // Collaborator activities from real-time feed
  const collaboratorActivities = collaboration.recentCollaboratorActivities

  // Compute activity statistics
  const stats = computed<ActivityStats>(() => {
    const acts = activities.value
    const byType: Record<string, number> = {}
    const byUser: Record<string, number> = {}
    let secretsUsed = 0
    let lastActivityAt: Date | undefined

    acts.forEach(activity => {
      // Count by type
      byType[activity.type] = (byType[activity.type] || 0) + 1

      // Count by user
      byUser[activity.userId] = (byUser[activity.userId] || 0) + 1

      // Count secrets
      if (activity.secretsUsed && activity.secretsUsed.length > 0) {
        secretsUsed += activity.secretsUsed.length
      }

      // Track latest activity
      if (!lastActivityAt || activity.timestamp > lastActivityAt) {
        lastActivityAt = activity.timestamp
      }
    })

    return {
      total: acts.length,
      byType: byType as Record<ActivityType, number>,
      byUser,
      secretsUsed,
      lastActivityAt
    }
  })

  /**
   * Track terminal activity and broadcast to collaborators
   */
  const trackTerminal = (command: string, metadata?: Record<string, unknown>): void => {
    const activityId = activityLogger.logTerminalActivity(command, metadata)
    if (activityId && chatStore.currentSession) {
      // Broadcast to collaborators
      const activity: SessionActivity = {
        id: activityId,
        type: 'terminal',
        userId: chatStore.currentSession.owner?.id || 'anonymous',
        content: command,
        timestamp: new Date(),
        metadata
      }
      collaboration.broadcastActivity(activity)
    }
    logger.debug('[Issue #874] Tracked terminal activity:', command.substring(0, 50))
  }

  /**
   * Track file operation and broadcast
   */
  const trackFile = (operation: FileActivitySubtype, path: string, metadata?: Record<string, unknown>): void => {
    const activityId = activityLogger.logFileActivity(operation, path, metadata)
    if (activityId && chatStore.currentSession) {
      const activity: SessionActivity = {
        id: activityId,
        type: 'file',
        userId: chatStore.currentSession.owner?.id || 'anonymous',
        content: `${operation}: ${path}`,
        timestamp: new Date(),
        metadata: { ...metadata, operation, path }
      }
      collaboration.broadcastActivity(activity)
    }
    logger.debug('[Issue #874] Tracked file activity:', { operation, path })
  }

  /**
   * Track desktop action and broadcast
   */
  const trackDesktop = (action: DesktopActivitySubtype, details: string, metadata?: Record<string, unknown>): void => {
    const activityId = activityLogger.logDesktopActivity(action, details, metadata)
    if (activityId && chatStore.currentSession) {
      const activity: SessionActivity = {
        id: activityId,
        type: 'desktop',
        userId: chatStore.currentSession.owner?.id || 'anonymous',
        content: details,
        timestamp: new Date(),
        metadata: { ...metadata, action }
      }
      collaboration.broadcastActivity(activity)
    }
    logger.debug('[Issue #874] Tracked desktop activity:', action)
  }

  /**
   * Track browser action and broadcast
   */
  const trackBrowser = (action: string, metadata?: Record<string, unknown>): void => {
    const activityId = activityLogger.logBrowserActivity(action, metadata)
    if (activityId && chatStore.currentSession) {
      const activity: SessionActivity = {
        id: activityId,
        type: 'browser',
        userId: chatStore.currentSession.owner?.id || 'anonymous',
        content: action,
        timestamp: new Date(),
        metadata
      }
      collaboration.broadcastActivity(activity)
    }
    logger.debug('[Issue #874] Tracked browser activity:', action)
  }

  /**
   * Track secret usage (always logged immediately, not broadcast for security)
   */
  const trackSecretUsage = (
    action: SecretUsageAction,
    secretId: string,
    secretName: string,
    secretType: SecretType
  ): void => {
    activityLogger.logSecretUsage(action, secretId, secretName, secretType)
    logger.debug('[Issue #874] Tracked secret usage:', { action, secretName })
  }

  /**
   * Get filtered activities
   */
  const getFilteredActivities = (filters: ActivityFilters): SessionActivity[] => {
    let filtered = activities.value

    if (filters.type) {
      filtered = filtered.filter(a => a.type === filters.type)
    }

    if (filters.userId) {
      filtered = filtered.filter(a => a.userId === filters.userId)
    }

    if (filters.startDate) {
      filtered = filtered.filter(a => a.timestamp >= filters.startDate!)
    }

    if (filters.endDate) {
      filtered = filtered.filter(a => a.timestamp <= filters.endDate!)
    }

    if (filters.hasSecrets !== undefined) {
      if (filters.hasSecrets) {
        filtered = filtered.filter(a => a.secretsUsed && a.secretsUsed.length > 0)
      } else {
        filtered = filtered.filter(a => !a.secretsUsed || a.secretsUsed.length === 0)
      }
    }

    return filtered
  }

  /**
   * Clear all activities for current session
   */
  const clearActivities = (): void => {
    const sessionId = chatStore.currentSession?.id
    if (!sessionId) return

    // Clear from store
    const session = chatStore.sessions.find(s => s.id === sessionId)
    if (session && session.activities) {
      session.activities = []
    }

    logger.info('[Issue #874] Cleared activities for session:', sessionId)
  }

  /**
   * Export activities as JSON
   */
  const exportActivities = (): string => {
    const data = {
      sessionId: chatStore.currentSession?.id,
      sessionTitle: chatStore.currentSession?.title,
      exportedAt: new Date().toISOString(),
      stats: stats.value,
      activities: activities.value.map(a => ({
        ...a,
        timestamp: a.timestamp.toISOString()
      }))
    }
    return JSON.stringify(data, null, 2)
  }

  // Auto-sync activities on interval
  let syncInterval: ReturnType<typeof setInterval> | null = null

  onMounted(() => {
    // Start periodic sync
    syncInterval = setInterval(() => {
      activityLogger.syncActivitiesToBackend()
    }, 30000) // Every 30 seconds

    logger.debug('[Issue #874] Activity tracking initialized')
  })

  onUnmounted(() => {
    if (syncInterval) {
      clearInterval(syncInterval)
      syncInterval = null
    }

    // Final sync before unmount
    activityLogger.syncActivitiesToBackend()
  })

  return {
    activities,
    collaboratorActivities,
    stats,
    isTracking,
    trackTerminal,
    trackFile,
    trackDesktop,
    trackBrowser,
    trackSecretUsage,
    getFilteredActivities,
    clearActivities,
    exportActivities
  }
}
