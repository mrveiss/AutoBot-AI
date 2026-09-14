// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #16443: useSessionCollaboration.ts rewritten onto the real backend.
 *
 * The single most important invariant this file pins: nothing here ever
 * sends one of the OLD invented `/ws/live` message shapes
 * (`{type: "session_join", ...}` etc.) -- every one of those was silently
 * dropped server-side (api/live_events.py's protocol only understands
 * `{action: "subscribe"|"unsubscribe"|"command"|"ping"}`). The rewrite talks
 * to two real things instead: REST (`api/collaboration.py`, via
 * `apiService`) and the presence WebSocket (`api/presence_ws.py` +
 * `websocket/presence.py`, `{type: "presence_sync"|"user_joined"|
 * "user_left"|"user_message"}` in, `{type: "broadcast", payload}` out).
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { MockWebSocket } from '../../test/mocks/websocket-mock'

const CURRENT_USER = { id: 'user-me', username: 'me' }

vi.mock('@/stores/useChatStore', () => ({
  useChatStore: () => ({
    currentSession: {
      id: 'session-1',
      mode: 'collaborative',
      owner: CURRENT_USER
    }
  })
}))

vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api'
}))

vi.mock('@/utils/buildAuthenticatedWsUrl', () => ({
  buildAuthenticatedWsUrl: (base: string) => `${base}?token=fake-test-token`
}))

const inviteToSession = vi.fn()
const shareSecretWithSession = vi.fn()
const getSessionEvents = vi.fn()
const getMyInvitations = vi.fn()
const respondToInvitation = vi.fn()

vi.mock('@/services/api', () => ({
  apiService: {
    inviteToSession: (...args: unknown[]) => inviteToSession(...args),
    shareSecretWithSession: (...args: unknown[]) => shareSecretWithSession(...args),
    getSessionEvents: (...args: unknown[]) => getSessionEvents(...args),
    getMyInvitations: (...args: unknown[]) => getMyInvitations(...args),
    respondToInvitation: (...args: unknown[]) => respondToInvitation(...args)
  }
}))

// Imported after the mocks above so the module under test picks them up.
import { useSessionCollaboration, cleanupCollaboration } from '../useSessionCollaboration'

describe('useSessionCollaboration (#16443)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockWebSocket.mockImplementation()
    MockWebSocket.clearInstances()
    inviteToSession.mockReset().mockResolvedValue({ success: true })
    shareSecretWithSession.mockReset().mockResolvedValue({ success: true })
    getSessionEvents.mockReset().mockResolvedValue({ session_id: 'session-1', events: [], has_more: false })
    getMyInvitations.mockReset().mockResolvedValue({ invitations: [] })
    respondToInvitation.mockReset().mockResolvedValue({ success: true, session_id: 'session-1', accepted: true, permission: 'viewer' })
  })

  afterEach(() => {
    cleanupCollaboration()
    MockWebSocket.restoreImplementation()
    MockWebSocket.clearInstances()
    vi.useRealTimers()
  })

  it('connects to the real presence WebSocket, not /ws/live', async () => {
    const { joinSession } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    expect(MockWebSocket.instances).toHaveLength(1)
    const socket = MockWebSocket.getLatestInstance()!
    expect(socket.url).toContain('/ws/sessions/session-1/presence')
    expect(socket.url).not.toContain('/ws/live')
  })

  it('never sends one of the old fake /ws/live message shapes', async () => {
    const FAKE_TYPES = [
      'session_join', 'session_leave', 'presence_update', 'activity_broadcast',
      'invitation_send', 'invitation_response', 'secret_shared', 'secret_revoked', 'cursor_move'
    ]

    const { joinSession, updatePresence, broadcastActivity } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    updatePresence('away', 'terminal')
    broadcastActivity({ id: 'a1', type: 'terminal', userId: CURRENT_USER.id, content: 'ls', timestamp: new Date() })

    const socket = MockWebSocket.getLatestInstance()!
    for (const call of socket.send.mock.calls) {
      const sent = JSON.parse(call[0] as string)
      // Every real message this composable sends is either a `broadcast`
      // envelope or nothing at all -- never a bare top-level fake type.
      expect(sent.type).toBe('broadcast')
      expect(FAKE_TYPES).not.toContain(sent.payload?.kind)
    }
  })

  it('populates sessionPresence from a real presence_sync message', async () => {
    const { joinSession, sessionPresence } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    MockWebSocket.getLatestInstance()!.simulateMessage({
      type: 'presence_sync',
      online_users: ['user-a', 'user-b'],
      timestamp: new Date().toISOString()
    })

    expect(sessionPresence.value.map(p => p.userId).sort()).toEqual(['user-a', 'user-b'])
  })

  it('adds and removes participants on user_joined / user_left', async () => {
    const { joinSession, sessionPresence } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)
    const socket = MockWebSocket.getLatestInstance()!

    socket.simulateMessage({ type: 'user_joined', user_id: 'user-a', timestamp: new Date().toISOString() })
    expect(sessionPresence.value.map(p => p.userId)).toContain('user-a')

    socket.simulateMessage({ type: 'user_left', user_id: 'user-a', timestamp: new Date().toISOString() })
    expect(sessionPresence.value.map(p => p.userId)).not.toContain('user-a')
  })

  it('surfaces a secret_shared broadcast from someone else as a notification', async () => {
    const { joinSession, secretNotifications } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    MockWebSocket.getLatestInstance()!.simulateMessage({
      type: 'user_message',
      user_id: 'someone-else',
      payload: {
        kind: 'secret_shared',
        secret_id: 'sec-1',
        secret_name: 'prod-db-password', // pragma: allowlist secret
        secret_type: 'password', // pragma: allowlist secret
        shared_by: 'someone-else',
        shared_by_username: 'alice',
        session_id: 'session-1'
      },
      timestamp: new Date().toISOString()
    })

    expect(secretNotifications.value).toHaveLength(1)
    expect(secretNotifications.value[0].secretId).toBe('sec-1')
    expect(secretNotifications.value[0].secretName).toBe('prod-db-password')
  })

  it('does not surface my own secret_shared broadcast as a notification', async () => {
    const { joinSession, secretNotifications } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    MockWebSocket.getLatestInstance()!.simulateMessage({
      type: 'user_message',
      user_id: CURRENT_USER.id,
      payload: {
        kind: 'secret_shared',
        secret_id: 'sec-1',
        secret_name: 'prod-db-password', // pragma: allowlist secret
        secret_type: 'password', // pragma: allowlist secret
        shared_by: CURRENT_USER.id,
        shared_by_username: CURRENT_USER.username,
        session_id: 'session-1'
      },
      timestamp: new Date().toISOString()
    })

    expect(secretNotifications.value).toHaveLength(0)
  })

  it('inviteCollaborator maps "collaborator" to the backend EDITOR permission via REST', async () => {
    const { joinSession, inviteCollaborator } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    const result = await inviteCollaborator('user-x', 'collaborator')

    expect(result).toBe(true)
    expect(inviteToSession).toHaveBeenCalledWith('session-1', 'user-x', 'editor')
  })

  it('inviteCollaborator maps "viewer" through unchanged and returns false on failure', async () => {
    inviteToSession.mockRejectedValue(new Error('403'))
    const { joinSession, inviteCollaborator } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    const result = await inviteCollaborator('user-x', 'viewer')

    expect(result).toBe(false)
    expect(inviteToSession).toHaveBeenCalledWith('session-1', 'user-x', 'viewer')
  })

  it('shareSecretWithSession calls the real REST endpoint with participant ids', async () => {
    const { joinSession, shareSecretWithSession: share } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)

    const result = await share('sec-1', ['user-a', 'user-b'])

    expect(result).toBe(true)
    expect(shareSecretWithSession).toHaveBeenCalledWith('session-1', 'sec-1', ['user-a', 'user-b'])
  })

  it('backfills recentCollaboratorActivities and secretNotifications from GET .../events on join (#16460)', async () => {
    getSessionEvents.mockResolvedValue({
      session_id: 'session-1',
      has_more: false,
      events: [
        {
          id: 'evt-2',
          session_id: 'session-1',
          kind: 'secret_shared',
          user_id: 'someone-else',
          username: 'alice',
          payload: {
            secret_id: 'sec-1',
            secret_name: 'prod-db-password', // pragma: allowlist secret
            secret_type: 'password', // pragma: allowlist secret
            shared_by: 'someone-else',
            shared_by_username: 'alice'
          },
          timestamp: '2026-09-12T10:01:00Z'
        },
        {
          id: 'evt-1',
          session_id: 'session-1',
          kind: 'activity',
          user_id: 'someone-else',
          username: 'alice',
          payload: { activity: { type: 'terminal', content: 'ls', timestamp: '2026-09-12T10:00:00Z' } },
          timestamp: '2026-09-12T10:00:00Z'
        }
      ]
    })

    const { joinSession, recentCollaboratorActivities, secretNotifications } = useSessionCollaboration()
    joinSession('session-1')
    await vi.advanceTimersByTimeAsync(20)
    await Promise.resolve()
    await Promise.resolve()

    expect(getSessionEvents).toHaveBeenCalledWith('session-1')
    expect(recentCollaboratorActivities.value).toHaveLength(1)
    expect(recentCollaboratorActivities.value[0].userId).toBe('someone-else')
    expect(secretNotifications.value).toHaveLength(1)
    expect(secretNotifications.value[0].secretId).toBe('sec-1')
  })

  it('refreshPendingInvitations populates pendingInvitations from GET /sessions/invitations/mine (#16460)', async () => {
    getMyInvitations.mockResolvedValue({
      invitations: [
        { session_id: 'session-9', from_user_id: 'owner-9', permission: 'viewer', invited_at: '2026-09-12T00:00:00Z', expires_at: null }
      ]
    })

    const { refreshPendingInvitations, pendingInvitations } = useSessionCollaboration()
    await refreshPendingInvitations()

    expect(pendingInvitations.value).toHaveLength(1)
    expect(pendingInvitations.value[0].sessionId).toBe('session-9')
    expect(pendingInvitations.value[0].fromUserId).toBe('owner-9')
  })

  it('respondToInvitation calls REST and drops the invitation from pendingInvitations on success (#16460)', async () => {
    getMyInvitations.mockResolvedValue({
      invitations: [
        { session_id: 'session-9', from_user_id: 'owner-9', permission: 'viewer', invited_at: '2026-09-12T00:00:00Z', expires_at: null }
      ]
    })
    respondToInvitation.mockResolvedValue({ success: true, session_id: 'session-9', accepted: true, permission: 'viewer' })

    const { refreshPendingInvitations, respondToInvitation: respond, pendingInvitations } = useSessionCollaboration()
    await refreshPendingInvitations()
    expect(pendingInvitations.value).toHaveLength(1)

    const result = await respond('session-9', true)

    expect(result).toBe(true)
    expect(respondToInvitation).toHaveBeenCalledWith('session-9', true)
    expect(pendingInvitations.value).toHaveLength(0)
  })
})
