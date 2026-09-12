// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Session Collaboration Composable
 *
 * Issue #608: User-Centric Session Tracking - Phase 5
 * #16443: rewritten onto the REAL backend. The previous version sent
 * invented message shapes (`{type: "session_join", ...}`) over
 * `globalWebSocketService`'s generic `/ws/live` channel, whose protocol only
 * understands `{action: "subscribe"|"unsubscribe"|"command"|"ping"}` --
 * every message this composable sent was silently dropped server-side
 * (logged at DEBUG, never delivered; see api/live_events.py's
 * `_handle_message`). Nothing here sends a `/ws/live`-shaped message anymore;
 * see __tests__/useSessionCollaboration.test.ts's
 * "never sends one of the old fake /ws/live message shapes" test.
 *
 * Real backend surface used instead:
 * - REST, `api/collaboration.py`: invite / remove / list participants /
 *   share a secret with the session (persists via Secret.share_with()).
 * - WebSocket, `api/presence_ws.py` + `websocket/presence.py`
 *   (`/ws/sessions/{id}/presence`, authenticated + authorized as of #16455):
 *   join/leave presence events, plus a generic `{"type":"broadcast","payload"}`
 *   relay any connected participant can send, forwarded live to the others.
 *   Activity broadcast and secret-share notifications both ride this relay
 *   (`payload.kind`) for LIVE delivery. #16460 added the durable copy:
 *   `GET /sessions/{id}/events` backfills `recentCollaboratorActivities` /
 *   `secretNotifications` with everything that happened before this client
 *   joined; `GET /sessions/invitations/mine` + `POST .../invitations/respond`
 *   back `pendingInvitations` / `respondToInvitation` below.
 *
 * Known gap: neither `GET .../participants` nor the presence WebSocket
 * returns a display username for anyone but the caller -- only user_id.
 * `UserPresence.username` falls back to the raw user_id until a real
 * user-lookup exists (also #16460's territory).
 *
 * Usage:
 * ```typescript
 * import { useSessionCollaboration } from '@/composables/useSessionCollaboration'
 *
 * const { sessionPresence, inviteCollaborator, joinSession, leaveSession } = useSessionCollaboration()
 * ```
 */

import { ref, computed, onMounted, onScopeDispose, getCurrentInstance, getCurrentScope, watch, type Ref, type ComputedRef } from 'vue'
import { useChatStore, type UserContext, type SessionActivity } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'
import { buildAuthenticatedWsUrl } from '@/utils/buildAuthenticatedWsUrl'
import { getApiBase } from '@/config/ssot-config'
import { apiService, type PendingInvitationResponse } from '@/services/api'

const logger = createLogger('SessionCollaboration')

/**
 * Presence state for a user in session
 */
export interface UserPresence {
  userId: string
  /** Best-effort display name -- falls back to userId (see module docstring). */
  username: string
  status: 'online' | 'away' | 'offline'
  lastSeen: Date
  currentTab?: 'chat' | 'terminal' | 'files' | 'browser' | 'desktop'
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

/** Shape of a message sent over the presence WebSocket's generic relay. */
interface PresenceBroadcastEnvelope {
  type: 'broadcast'
  payload: Record<string, unknown>
}

/** A pending invitation to collaborate on someone else's session (#16460). */
export interface PendingInvitation {
  sessionId: string
  fromUserId: string
  permission: string
  invitedAt: string
  expiresAt: string | null
}

/**
 * Return type for the composable
 */
export interface UseSessionCollaborationReturn {
  /** Current user's presence state */
  myPresence: Ref<UserPresence | null>
  /** All participants' presence in current session (online only -- see module docstring) */
  sessionPresence: ComputedRef<UserPresence[]>
  /** Recent activities from collaborators (live + backfilled on join, #16460) */
  recentCollaboratorActivities: Ref<CollaboratorActivity[]>
  /** Secret sharing notifications (live + backfilled on join, #16460) */
  secretNotifications: Ref<SecretSharingNotification[]>
  /** Whether the presence WebSocket is connected */
  isConnected: ComputedRef<boolean>
  /** Pending invitations addressed to the current user, across all sessions */
  pendingInvitations: Ref<PendingInvitation[]>

  /** Join a session for collaboration */
  joinSession: (sessionId: string) => void
  /** Leave current session */
  leaveSession: () => void
  /** Update my presence status (local + best-effort broadcast to others) */
  updatePresence: (status: UserPresence['status'], currentTab?: UserPresence['currentTab']) => void
  /** Invite a user to collaborate. 'collaborator' maps to the backend's EDITOR permission. */
  inviteCollaborator: (userId: string, role?: 'collaborator' | 'viewer') => Promise<boolean>
  /** Broadcast an activity to collaborators */
  broadcastActivity: (activity: SessionActivity) => void
  /** Share a secret with session participants (persists via the backend).
   *  Omit participantIds to share with every editor+ participant. */
  shareSecretWithSession: (secretId: string, participantIds?: string[]) => Promise<boolean>
  /** Clear secret notifications */
  clearSecretNotifications: () => void
  /** Refresh `pendingInvitations` from the backend */
  refreshPendingInvitations: () => Promise<void>
  /** Accept or decline a pending invitation */
  respondToInvitation: (sessionId: string, accept: boolean) => Promise<boolean>
}

// Module-level state (shared across instances, matching the pre-#16443 design)
const presenceMap = ref<Map<string, UserPresence>>(new Map())
const recentActivities = ref<CollaboratorActivity[]>([])
const secretNotifications = ref<SecretSharingNotification[]>([])
const currentSessionId = ref<string | null>(null)
const myPresence = ref<UserPresence | null>(null)
const wsConnected = ref(false)
const pendingInvitations = ref<PendingInvitation[]>([])
let presenceSocket: WebSocket | null = null

// #16443 review: multiple components call useSessionCollaboration() for the
// SAME session (ParticipantList, PresenceIndicator, ActivityFeed,
// SecretNotifications, ChatCollaborationPanel all do). Each instantiation
// registers its own onScopeDispose -- with the connection now real (it was
// inert under the old fake protocol, so this never mattered before), the
// first one of those components to unmount would close the socket out from
// under every other still-mounted consumer. Reference-counted: the socket
// closes only when the last instance disposes.
let activeInstanceCount = 0

function _presenceWsUrl(sessionId: string): string | null {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const base = `${wsProtocol}//${window.location.host}${getApiBase()}/ws/sessions/${sessionId}/presence`
  return buildAuthenticatedWsUrl(base)
}

/**
 * Session Collaboration composable
 *
 * @returns Collaboration utilities
 */
export function useSessionCollaboration(): UseSessionCollaborationReturn {
  const chatStore = useChatStore()

  const getCurrentUser = (): UserContext | null => {
    const session = chatStore.currentSession
    return session?.owner || null
  }

  const sessionPresence = computed<UserPresence[]>(() => {
    if (!currentSessionId.value) return []
    return Array.from(presenceMap.value.values())
  })

  const isConnected = computed(() => wsConnected.value)

  const _upsertPresence = (userId: string, patch: Partial<UserPresence>): void => {
    const existing = presenceMap.value.get(userId)
    presenceMap.value.set(userId, {
      userId,
      username: existing?.username ?? userId,
      currentTab: existing?.currentTab,
      // Any upsert means "just seen" -- status/lastSeen default fresh, not
      // carried over from `existing`, unless `patch` explicitly overrides them.
      status: 'online',
      lastSeen: new Date(),
      ...patch
    })
  }

  const _handleBroadcastPayload = (senderId: string, payload: Record<string, unknown>): void => {
    const currentUser = getCurrentUser()
    const isOwnMessage = !!currentUser && senderId === currentUser.id

    switch (payload.kind) {
      case 'activity': {
        if (isOwnMessage) return
        recentActivities.value.unshift({
          sessionId: currentSessionId.value || '',
          userId: senderId,
          username: (payload.username as string) || senderId,
          activity: {
            ...(payload.activity as SessionActivity),
            timestamp: new Date((payload.activity as { timestamp: string })?.timestamp)
          },
          timestamp: new Date()
        })
        if (recentActivities.value.length > 50) {
          recentActivities.value = recentActivities.value.slice(0, 50)
        }
        break
      }
      case 'secret_shared': {
        if (isOwnMessage) return
        secretNotifications.value.unshift({
          secretId: payload.secret_id as string,
          secretName: payload.secret_name as string,
          secretType: payload.secret_type as string,
          sharedBy: payload.shared_by as string,
          sharedByUsername: (payload.shared_by_username as string) || (payload.shared_by as string),
          sessionId: (payload.session_id as string) || currentSessionId.value || '',
          action: 'shared',
          timestamp: new Date()
        })
        break
      }
      case 'presence_update': {
        _upsertPresence(senderId, {
          status: (payload.status as UserPresence['status']) || 'online',
          currentTab: payload.current_tab as UserPresence['currentTab']
        })
        break
      }
      default:
        logger.debug('Unrecognized presence broadcast kind:', payload.kind)
    }
  }

  const _handlePresenceSocketMessage = (event: MessageEvent<string>): void => {
    let data: Record<string, unknown>
    try {
      data = JSON.parse(event.data)
    } catch {
      return
    }

    switch (data.type) {
      case 'presence_sync': {
        const onlineUsers = (data.online_users as string[]) || []
        presenceMap.value.clear()
        onlineUsers.forEach(userId => _upsertPresence(userId, {}))
        break
      }
      case 'user_joined':
        _upsertPresence(data.user_id as string, {})
        logger.debug(`User ${data.user_id} joined session`)
        break
      case 'user_left':
        presenceMap.value.delete(data.user_id as string)
        logger.debug(`User ${data.user_id} left session`)
        break
      case 'user_message':
        _handleBroadcastPayload(data.user_id as string, (data.payload as Record<string, unknown>) || {})
        break
      case 'pong':
      case 'ping':
        break
      default:
        logger.debug('Unrecognized presence message type:', data.type)
    }
  }

  const _sendBroadcast = (payload: Record<string, unknown>): void => {
    if (!presenceSocket || presenceSocket.readyState !== WebSocket.OPEN) return
    const envelope: PresenceBroadcastEnvelope = { type: 'broadcast', payload }
    presenceSocket.send(JSON.stringify(envelope))
  }

  /**
   * Backfill activity/notification history from the durable copy (#16460) --
   * covers everything that happened in this session before this client
   * joined (or while it was disconnected), which the live relay alone can't.
   */
  const _backfillEvents = async (sessionId: string): Promise<void> => {
    try {
      const { events } = await apiService.getSessionEvents(sessionId)
      // Oldest first, matching how live events arrive (unshift onto the front).
      for (const event of [...events].reverse()) {
        if (event.kind === 'activity') {
          recentActivities.value.unshift({
            sessionId: event.session_id,
            userId: event.user_id ?? '',
            username: event.username || event.user_id || '',
            activity: {
              ...(event.payload.activity as SessionActivity),
              timestamp: new Date((event.payload.activity as { timestamp: string })?.timestamp)
            },
            timestamp: new Date(event.timestamp)
          })
        } else if (event.kind === 'secret_shared') {
          secretNotifications.value.unshift({
            secretId: event.payload.secret_id as string,
            secretName: event.payload.secret_name as string,
            secretType: event.payload.secret_type as string,
            sharedBy: event.payload.shared_by as string,
            sharedByUsername: (event.payload.shared_by_username as string) || (event.payload.shared_by as string),
            sessionId: event.session_id,
            action: 'shared',
            timestamp: new Date(event.timestamp)
          })
        }
      }
      if (recentActivities.value.length > 50) {
        recentActivities.value = recentActivities.value.slice(0, 50)
      }
    } catch (error) {
      logger.error('Failed to backfill session events:', error)
    }
  }

  /**
   * Join a session for collaboration -- opens the real presence WebSocket.
   */
  const joinSession = (sessionId: string): void => {
    // Idempotent: several components mounted at once each call joinSession
    // for the same session via the auto-join watcher below. Reopening the
    // socket on every one of them would thrash the connection for no reason.
    if (currentSessionId.value === sessionId && presenceSocket) return

    const user = getCurrentUser()
    if (!user) {
      logger.warn('Cannot join session: no current user')
      return
    }

    if (currentSessionId.value) {
      leaveSession()
    }

    const wsUrl = _presenceWsUrl(sessionId)
    if (!wsUrl) {
      logger.debug('No auth token available yet; deferring presence connect')
      return
    }

    currentSessionId.value = sessionId
    myPresence.value = {
      userId: user.id,
      username: user.username,
      status: 'online',
      lastSeen: new Date(),
      currentTab: 'chat'
    }

    presenceSocket = new WebSocket(wsUrl)
    presenceSocket.onopen = () => {
      wsConnected.value = true
      logger.debug(`Joined session ${sessionId} for collaboration`)
    }
    presenceSocket.onmessage = _handlePresenceSocketMessage
    presenceSocket.onclose = () => {
      wsConnected.value = false
    }
    presenceSocket.onerror = () => {
      logger.warn('Presence WebSocket error')
    }

    void _backfillEvents(sessionId)
  }

  /**
   * Leave current session
   */
  const leaveSession = (): void => {
    if (presenceSocket) {
      presenceSocket.onopen = null
      presenceSocket.onmessage = null
      presenceSocket.onclose = null
      presenceSocket.onerror = null
      presenceSocket.close()
      presenceSocket = null
    }
    wsConnected.value = false
    presenceMap.value.clear()
    currentSessionId.value = null
    myPresence.value = null
    logger.debug('Left collaboration session')
  }

  /**
   * Update my presence status: local state always; best-effort broadcast to
   * other connected participants (there is no server-side persistence of
   * status/tab, so a participant who joins later won't see history of it).
   */
  const updatePresence = (
    status: UserPresence['status'],
    currentTab?: UserPresence['currentTab']
  ): void => {
    if (!myPresence.value) return

    myPresence.value.status = status
    myPresence.value.lastSeen = new Date()
    if (currentTab) {
      myPresence.value.currentTab = currentTab
    }

    _sendBroadcast({
      kind: 'presence_update',
      status,
      current_tab: currentTab
    })
  }

  /**
   * Invite a user to collaborate. Real REST call -- POST /sessions/{id}/invite.
   */
  const inviteCollaborator = async (
    userId: string,
    role: 'collaborator' | 'viewer' = 'collaborator'
  ): Promise<boolean> => {
    if (!currentSessionId.value) {
      logger.warn('Cannot invite: no current session')
      return false
    }

    try {
      // The UI's "collaborator" role maps to the backend's EDITOR permission
      // level (owner/editor/viewer) -- "collaborator" reads as "can edit".
      const permission = role === 'collaborator' ? 'editor' : 'viewer'
      await apiService.inviteToSession(currentSessionId.value, userId, permission)
      logger.debug(`Sent invitation to user ${userId}`)
      return true
    } catch (error) {
      logger.error('Failed to invite collaborator:', error)
      return false
    }
  }

  /**
   * Broadcast an activity to collaborators over the presence relay.
   */
  const broadcastActivity = (activity: SessionActivity): void => {
    const user = getCurrentUser()
    if (!user || !currentSessionId.value) return

    _sendBroadcast({
      kind: 'activity',
      username: user.username,
      activity
    })
  }

  /**
   * Share a secret with session participants. Real REST call --
   * POST /sessions/{id}/secrets/share -- persists via Secret.share_with()
   * and the backend broadcasts a live notification (id/name/sharer only,
   * never the value) to connected participants.
   */
  const shareSecretWithSession = async (secretId: string, participantIds?: string[]): Promise<boolean> => {
    if (!currentSessionId.value) return false

    try {
      await apiService.shareSecretWithSession(currentSessionId.value, secretId, participantIds)
      logger.debug(`Shared secret ${secretId} with session`)
      return true
    } catch (error) {
      logger.error('Failed to share secret with session:', error)
      return false
    }
  }

  /**
   * Clear secret notifications
   */
  const clearSecretNotifications = (): void => {
    secretNotifications.value = []
  }

  /**
   * Refresh `pendingInvitations` from GET /sessions/invitations/mine (#16460).
   */
  const refreshPendingInvitations = async (): Promise<void> => {
    try {
      const { invitations } = await apiService.getMyInvitations()
      pendingInvitations.value = invitations.map((inv: PendingInvitationResponse) => ({
        sessionId: inv.session_id,
        fromUserId: inv.from_user_id,
        permission: inv.permission,
        invitedAt: inv.invited_at,
        expiresAt: inv.expires_at
      }))
    } catch (error) {
      logger.error('Failed to refresh pending invitations:', error)
    }
  }

  /**
   * Accept or decline a pending invitation -- POST
   * /sessions/{id}/invitations/respond (#16460). Removes it from
   * `pendingInvitations` locally on success rather than a full refetch.
   */
  const respondToInvitation = async (sessionId: string, accept: boolean): Promise<boolean> => {
    try {
      const response = await apiService.respondToInvitation(sessionId, accept)
      if (response.success) {
        pendingInvitations.value = pendingInvitations.value.filter(inv => inv.sessionId !== sessionId)
      }
      return response.success
    } catch (error) {
      logger.error('Failed to respond to invitation:', error)
      return false
    }
  }

  // Auto-join when the current chat session is collaborative
  watch(
    () => chatStore.currentSession?.id,
    (newSessionId, oldSessionId) => {
      if (newSessionId && newSessionId !== oldSessionId) {
        const session = chatStore.currentSession
        if (session?.mode === 'collaborative') {
          joinSession(newSessionId)
        }
      }
    }
  )

  if (getCurrentInstance()) {
    onMounted(() => {
      logger.debug('Session collaboration initialized')
    })
  }

  if (getCurrentScope()) {
    activeInstanceCount++
    onScopeDispose(() => {
      activeInstanceCount--
      if (activeInstanceCount <= 0) {
        activeInstanceCount = 0
        leaveSession()
      }
    })
  }

  return {
    myPresence,
    sessionPresence,
    recentCollaboratorActivities: recentActivities,
    secretNotifications,
    isConnected,
    pendingInvitations,
    joinSession,
    leaveSession,
    updatePresence,
    inviteCollaborator,
    broadcastActivity,
    shareSecretWithSession,
    clearSecretNotifications,
    refreshPendingInvitations,
    respondToInvitation
  }
}

/**
 * Cleanup function to stop collaboration and clear state.
 * Call this when the app is being destroyed.
 */
export function cleanupCollaboration(): void {
  if (presenceSocket) {
    presenceSocket.close()
    presenceSocket = null
  }
  activeInstanceCount = 0
  wsConnected.value = false
  presenceMap.value.clear()
  recentActivities.value = []
  secretNotifications.value = []
  pendingInvitations.value = []
  currentSessionId.value = null
  myPresence.value = null
}
