/**
 * Session Collaboration Composable
 *
 * Issue #608: User-Centric Session Tracking - Phase 5
 *
 * Provides real-time collaboration features for chat sessions:
 * - Presence tracking (who's online in session)
 * - Activity sync between collaborators
 * - Invitation system
 * - Secret sharing notifications
 *
 * Usage:
 * ```typescript
 * import { useSessionCollaboration } from '@/composables/useSessionCollaboration'
 *
 * const {
 *   presence,
 *   inviteCollaborator,
 *   leaveSession,
 *   onActivityUpdate
 * } = useSessionCollaboration()
 * ```
 */

import { ref, computed, onMounted, onUnmounted, watch, type Ref, type ComputedRef } from 'vue'
import { useChatStore, type UserContext, type SessionActivity } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'
import globalWebSocketService from '@/services/GlobalWebSocketService.js'

// Create scoped logger
const logger = createLogger('SessionCollaboration')

/**
 * Presence state for a user in session
 */
export interface UserPresence {
  userId: string
  username: string
  status: 'online' | 'away' | 'offline'
  lastSeen: Date
  currentTab?: 'chat' | 'terminal' | 'files' | 'browser' | 'desktop'
  cursorPosition?: { x: number; y: number }
}

/**
 * Collaboration invitation
 */
export interface CollaborationInvitation {
  id: string
  sessionId: string
  sessionName: string
  fromUserId: string
  fromUsername: string
  toUserId: string
  role: 'collaborator' | 'viewer'
  createdAt: Date
  expiresAt: Date
  status: 'pending' | 'accepted' | 'declined' | 'expired'
}

/**
 * Activity update from collaborator
 */
export interface CollaboratorActivity {
  sessionId: string
  userId: string
  username: string
  activity: SessionActivity
  timestamp: Date
}

/**
 * Secret sharing notification
 */
export interface SecretSharingNotification {
  secretId: string
  secretName: string
  secretType: string
  sharedBy: string
  sharedByUsername: string
  sessionId: string
  action: 'shared' | 'revoked'
  timestamp: Date
}

/**
 * WebSocket message types for collaboration
 */
type CollaborationMessageType =
  | 'session_join'
  | 'session_leave'
  | 'presence_update'
  | 'activity_broadcast'
  | 'invitation_send'
  | 'invitation_response'
  | 'secret_shared'
  | 'secret_revoked'
  | 'cursor_move'

interface CollaborationMessage {
  type: CollaborationMessageType
  sessionId: string
  payload: Record<string, unknown>
  timestamp: string
}

/**
 * Return type for the composable
 */
export interface UseSessionCollaborationReturn {
  /** Current user's presence state */
  myPresence: Ref<UserPresence | null>
  /** All participants' presence in current session */
  sessionPresence: ComputedRef<UserPresence[]>
  /** Pending invitations for current user */
  pendingInvitations: Ref<CollaborationInvitation[]>
  /** Recent activities from collaborators */
  recentCollaboratorActivities: Ref<CollaboratorActivity[]>
  /** Secret sharing notifications */
  secretNotifications: Ref<SecretSharingNotification[]>
  /** Whether collaboration is connected */
  isConnected: ComputedRef<boolean>

  /** Join a session for collaboration */
  joinSession: (sessionId: string) => void
  /** Leave current session */
  leaveSession: () => void
  /** Update my presence status */
  updatePresence: (status: UserPresence['status'], currentTab?: UserPresence['currentTab']) => void
  /** Invite a user to collaborate */
  inviteCollaborator: (userId: string, role?: 'collaborator' | 'viewer') => boolean
  /** Respond to an invitation */
  respondToInvitation: (invitationId: string, accept: boolean) => boolean
  /** Broadcast an activity to collaborators */
  broadcastActivity: (activity: SessionActivity) => void
  /** Share a secret with session participants */
  shareSecretWithSession: (secretId: string, secretName: string, secretType: string) => void
  /** Clear secret notifications */
  clearSecretNotifications: () => void
}

// Module-level state (shared across instances)
const presenceMap = ref<Map<string, UserPresence>>(new Map())
const pendingInvitations = ref<CollaborationInvitation[]>([])
const recentActivities = ref<CollaboratorActivity[]>([])
const secretNotifications = ref<SecretSharingNotification[]>([])
const currentSessionId = ref<string | null>(null)
const myPresence = ref<UserPresence | null>(null)
let presenceInterval: ReturnType<typeof setInterval> | null = null
let unsubscribers: Array<() => void> = []

/**
 * Session Collaboration composable
 *
 * @returns Collaboration utilities
 */
export function useSessionCollaboration(): UseSessionCollaborationReturn {
  const chatStore = useChatStore()

  // Get current user from store
  const getCurrentUser = (): UserContext | null => {
    const session = chatStore.currentSession
    return session?.owner || null
  }

  // Computed: all presence entries for current session
  const sessionPresence = computed<UserPresence[]>(() => {
    if (!currentSessionId.value) return []
    return Array.from(presenceMap.value.values())
  })

  // Computed: is WebSocket connected
  const isConnected = computed(() => (globalWebSocketService as any).isConnected?.value ?? false)

  /**
   * Handle incoming WebSocket messages for collaboration
   */
  const handleCollaborationMessage = (message: CollaborationMessage) => {
    if (message.sessionId !== currentSessionId.value) return

    switch (message.type) {
      case 'session_join':
        handleUserJoined(message.payload as unknown as UserPresence)
        break
      case 'session_leave':
        handleUserLeft(message.payload.userId as string)
        break
      case 'presence_update':
        handlePresenceUpdate(message.payload as unknown as UserPresence)
        break
      case 'activity_broadcast':
        handleActivityBroadcast(message.payload as unknown as CollaboratorActivity)
        break
      case 'invitation_send':
        handleInvitationReceived(message.payload as unknown as CollaborationInvitation)
        break
      case 'invitation_response':
        handleInvitationResponse(message.payload as { invitationId: string; accepted: boolean })
        break
      case 'secret_shared':
      case 'secret_revoked':
        handleSecretNotification(message.payload as unknown as SecretSharingNotification)
        break
      case 'cursor_move':
        handleCursorMove(message.payload as { userId: string; position: { x: number; y: number } })
        break
    }
  }

  /**
   * Handle user joining session
   */
  const handleUserJoined = (presence: UserPresence) => {
    presenceMap.value.set(presence.userId, {
      ...presence,
      lastSeen: new Date(presence.lastSeen)
    })
    logger.debug(`[Issue #608] User ${presence.username} joined session`)
  }

  /**
   * Handle user leaving session
   */
  const handleUserLeft = (userId: string) => {
    const user = presenceMap.value.get(userId)
    if (user) {
      logger.debug(`[Issue #608] User ${user.username} left session`)
      presenceMap.value.delete(userId)
    }
  }

  /**
   * Handle presence update
   */
  const handlePresenceUpdate = (presence: UserPresence) => {
    presenceMap.value.set(presence.userId, {
      ...presence,
      lastSeen: new Date(presence.lastSeen)
    })
  }

  /**
   * Handle activity broadcast from collaborator
   */
  const handleActivityBroadcast = (activity: CollaboratorActivity) => {
    // Don't show my own activities
    const currentUser = getCurrentUser()
    if (currentUser && activity.userId === currentUser.id) return

    recentActivities.value.unshift({
      ...activity,
      timestamp: new Date(activity.timestamp)
    })

    // Keep only last 50 activities
    if (recentActivities.value.length > 50) {
      recentActivities.value = recentActivities.value.slice(0, 50)
    }

    logger.debug(`[Issue #608] Activity from ${activity.username}: ${activity.activity.type}`)
  }

  /**
   * Handle invitation received
   */
  const handleInvitationReceived = (invitation: CollaborationInvitation) => {
    pendingInvitations.value.push({
      ...invitation,
      createdAt: new Date(invitation.createdAt),
      expiresAt: new Date(invitation.expiresAt)
    })
    logger.debug(`[Issue #608] Received invitation from ${invitation.fromUsername}`)
  }

  /**
   * Handle invitation response
   */
  const handleInvitationResponse = (response: { invitationId: string; accepted: boolean }) => {
    const index = pendingInvitations.value.findIndex(i => i.id === response.invitationId)
    if (index !== -1) {
      pendingInvitations.value[index].status = response.accepted ? 'accepted' : 'declined'
    }
  }

  /**
   * Handle secret sharing notification
   */
  const handleSecretNotification = (notification: SecretSharingNotification) => {
    secretNotifications.value.unshift({
      ...notification,
      timestamp: new Date(notification.timestamp)
    })
    logger.debug(`[Issue #608] Secret ${notification.action}: ${notification.secretName}`)
  }

  /**
   * Handle cursor movement from collaborator
   */
  const handleCursorMove = (data: { userId: string; position: { x: number; y: number } }) => {
    const presence = presenceMap.value.get(data.userId)
    if (presence) {
      presence.cursorPosition = data.position
      presenceMap.value.set(data.userId, presence)
    }
  }

  /**
   * Send presence update to server
   */
  const sendPresenceUpdate = () => {
    if (!myPresence.value || !currentSessionId.value) return

    const message: CollaborationMessage = {
      type: 'presence_update',
      sessionId: currentSessionId.value,
      payload: myPresence.value as unknown as Record<string, unknown>,
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)
  }

  /**
   * Join a session for collaboration
   */
  const joinSession = (sessionId: string) => {
    const user = getCurrentUser()
    if (!user) {
      logger.warn('[Issue #608] Cannot join session: no current user')
      return
    }

    // Leave previous session if any
    if (currentSessionId.value) {
      leaveSession()
    }

    currentSessionId.value = sessionId
    myPresence.value = {
      userId: user.id,
      username: user.username,
      status: 'online',
      lastSeen: new Date(),
      currentTab: 'chat'
    }

    // Send join message
    const message: CollaborationMessage = {
      type: 'session_join',
      sessionId,
      payload: myPresence.value as unknown as Record<string, unknown>,
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)

    // Start presence heartbeat
    if (presenceInterval) {
      clearInterval(presenceInterval)
    }
    presenceInterval = setInterval(sendPresenceUpdate, 30000) // Every 30 seconds

    logger.debug(`[Issue #608] Joined session ${sessionId} for collaboration`)
  }

  /**
   * Leave current session
   */
  const leaveSession = () => {
    if (!currentSessionId.value || !myPresence.value) return

    const message: CollaborationMessage = {
      type: 'session_leave',
      sessionId: currentSessionId.value,
      payload: { userId: myPresence.value.userId },
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)

    // Clear state
    if (presenceInterval) {
      clearInterval(presenceInterval)
      presenceInterval = null
    }
    presenceMap.value.clear()
    currentSessionId.value = null
    myPresence.value = null

    logger.debug('[Issue #608] Left collaboration session')
  }

  /**
   * Update my presence status
   */
  const updatePresence = (
    status: UserPresence['status'],
    currentTab?: UserPresence['currentTab']
  ) => {
    if (!myPresence.value) return

    myPresence.value.status = status
    myPresence.value.lastSeen = new Date()
    if (currentTab) {
      myPresence.value.currentTab = currentTab
    }

    sendPresenceUpdate()
  }

  /**
   * Invite a user to collaborate
   */
  const inviteCollaborator = (userId: string, role: 'collaborator' | 'viewer' = 'collaborator'): boolean => {
    const user = getCurrentUser()
    const session = chatStore.currentSession
    if (!user || !session || !currentSessionId.value) {
      logger.warn('[Issue #608] Cannot invite: no current user or session')
      return false
    }

    const invitation: CollaborationInvitation = {
      id: `inv-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      sessionId: currentSessionId.value,
      sessionName: session.title || 'Unnamed Session',
      fromUserId: user.id,
      fromUsername: user.username,
      toUserId: userId,
      role,
      createdAt: new Date(),
      expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000), // 24 hours
      status: 'pending'
    }

    const message: CollaborationMessage = {
      type: 'invitation_send',
      sessionId: currentSessionId.value,
      payload: invitation as unknown as Record<string, unknown>,
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)
    logger.debug(`[Issue #608] Sent invitation to user ${userId}`)
    return true
  }

  /**
   * Respond to an invitation
   */
  const respondToInvitation = (invitationId: string, accept: boolean): boolean => {
    const invitation = pendingInvitations.value.find(i => i.id === invitationId)
    if (!invitation) return false

    invitation.status = accept ? 'accepted' : 'declined'

    const message: CollaborationMessage = {
      type: 'invitation_response',
      sessionId: invitation.sessionId,
      payload: { invitationId, accepted: accept },
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)

    // If accepted, join the session
    if (accept) {
      joinSession(invitation.sessionId)
    }

    logger.debug(`[Issue #608] ${accept ? 'Accepted' : 'Declined'} invitation ${invitationId}`)
    return true
  }

  /**
   * Broadcast an activity to collaborators
   */
  const broadcastActivity = (activity: SessionActivity) => {
    const user = getCurrentUser()
    if (!user || !currentSessionId.value) return

    const collaboratorActivity: CollaboratorActivity = {
      sessionId: currentSessionId.value,
      userId: user.id,
      username: user.username,
      activity,
      timestamp: new Date()
    }

    const message: CollaborationMessage = {
      type: 'activity_broadcast',
      sessionId: currentSessionId.value,
      payload: collaboratorActivity as unknown as Record<string, unknown>,
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)
  }

  /**
   * Share a secret with session participants
   */
  const shareSecretWithSession = (secretId: string, secretName: string, secretType: string) => {
    const user = getCurrentUser()
    if (!user || !currentSessionId.value) return

    const notification: SecretSharingNotification = {
      secretId,
      secretName,
      secretType,
      sharedBy: user.id,
      sharedByUsername: user.username,
      sessionId: currentSessionId.value,
      action: 'shared',
      timestamp: new Date()
    }

    const message: CollaborationMessage = {
      type: 'secret_shared',
      sessionId: currentSessionId.value,
      payload: notification as unknown as Record<string, unknown>,
      timestamp: new Date().toISOString()
    }

    globalWebSocketService.send(message as any)
    logger.debug(`[Issue #608] Shared secret ${secretName} with session`)
  }

  /**
   * Clear secret notifications
   */
  const clearSecretNotifications = () => {
    secretNotifications.value = []
  }

  // Subscribe to WebSocket messages on mount
  onMounted(() => {
    // Subscribe to collaboration messages
    const unsubMessage = globalWebSocketService.subscribe('collaboration', handleCollaborationMessage)
    unsubscribers.push(unsubMessage)

    // Also subscribe to specific message types that might come separately
    const messageTypes: CollaborationMessageType[] = [
      'session_join',
      'session_leave',
      'presence_update',
      'activity_broadcast',
      'invitation_send',
      'invitation_response',
      'secret_shared',
      'secret_revoked',
      'cursor_move'
    ]

    messageTypes.forEach(type => {
      const unsub = globalWebSocketService.subscribe(type, (data: Record<string, unknown>) => {
        handleCollaborationMessage({
          type,
          sessionId: data.sessionId as string,
          payload: data,
          timestamp: data.timestamp as string || new Date().toISOString()
        })
      })
      unsubscribers.push(unsub)
    })

    logger.debug('[Issue #608] Session collaboration initialized')
  })

  // Watch for session changes
  watch(
    () => chatStore.currentSession?.id,
    (newSessionId, oldSessionId) => {
      if (newSessionId && newSessionId !== oldSessionId) {
        // Auto-join if collaborative session
        const session = chatStore.currentSession
        if (session?.mode === 'collaborative') {
          joinSession(newSessionId)
        }
      }
    }
  )

  // Cleanup on unmount
  onUnmounted(() => {
    leaveSession()
    unsubscribers.forEach(unsub => unsub())
    unsubscribers = []
  })

  return {
    myPresence,
    sessionPresence,
    pendingInvitations,
    recentCollaboratorActivities: recentActivities,
    secretNotifications,
    isConnected,
    joinSession,
    leaveSession,
    updatePresence,
    inviteCollaborator,
    respondToInvitation,
    broadcastActivity,
    shareSecretWithSession,
    clearSecretNotifications
  }
}

/**
 * Cleanup function to stop collaboration and clear state
 * Call this when the app is being destroyed
 */
export function cleanupCollaboration(): void {
  if (presenceInterval) {
    clearInterval(presenceInterval)
    presenceInterval = null
  }
  presenceMap.value.clear()
  pendingInvitations.value = []
  recentActivities.value = []
  secretNotifications.value = []
  currentSessionId.value = null
  myPresence.value = null
}
