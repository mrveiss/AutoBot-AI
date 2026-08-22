/**
 * Session synchronization across clients (#14820, #14821).
 *
 * AutoBot is one host with many clients. Session state used to live in the
 * browser — ids minted locally, messages appended locally, `localStorage` as
 * the source of truth — so two tabs on one account held two independent truths
 * that could never converge.
 *
 * This composable makes the backend authoritative for one conversation:
 * subscribe to its `session:` and `chat:` channels, apply what the server
 * publishes, and rebuild from the REST snapshot whenever the server says our
 * view cannot be trusted.
 *
 * `localStorage` remains, demoted to a cache: useful for an instant first
 * paint and for offline reads, never the authority.
 */

import { onUnmounted, ref, watch, type Ref } from 'vue'
import liveEventService, { type LiveEvent } from '@/services/LiveEventService'
import { useChatStore } from '@/stores/useChatStore'
import { createLogger } from '@/utils/debugUtils'
import type { ChatMessage, MessageSender } from '@/types/api'
import apiClient from '@/utils/ApiClient'

const logger = createLogger('SessionSync')

/** Event types published on the session/chat channels by the backend. */
const SESSION_UPDATED = 'session.updated'
const SESSION_DELETED = 'session.deleted'
const CHAT_MESSAGE_ADDED = 'chat.message_added'
const CHAT_CLEARED = 'chat.cleared'

interface BackendMessage {
  id?: string
  message_id?: string
  sender?: string
  text?: string
  message_type?: string
  timestamp?: string
}

/**
 * Convert one backend message record into the store's shape.
 *
 * Returns null when the record carries no usable identity — a message we
 * cannot identify cannot be deduplicated, and appending it blindly is how
 * duplicate bubbles appear.
 */
function toChatMessage(raw: BackendMessage): ChatMessage | null {
  const id = raw.id ?? raw.message_id
  if (!id) {
    logger.warn('Dropping remote message with no id', raw)
    return null
  }
  // The backend stores the body as `text`; the canonical frontend field is
  // `content` (see types/api.ts). Mapping it here keeps the rest of the store
  // working in one vocabulary.
  return {
    id,
    content: raw.text ?? '',
    sender: (raw.sender ?? 'bot') as MessageSender,
    timestamp: raw.timestamp ? new Date(raw.timestamp) : new Date(),
    message_type: raw.message_type,
  }
}

/**
 * Keep `sessionId` synchronized with the backend for as long as the caller is
 * mounted. Pass a ref to follow the active session as the user switches.
 */
export function useSessionSync(sessionId: Ref<string | null>) {
  const chatStore = useChatStore()

  /** True once a server snapshot has been applied for the current session. */
  const synchronized = ref(false)
  /** Set when the last resync attempt failed — the view may be stale. */
  const syncError = ref<string | null>(null)

  let disposers: Array<() => void> = []

  /**
   * Rebuild this session's contents from the server.
   *
   * Called on subscribe and whenever the server sends a resync directive. On
   * failure it records the error rather than leaving a stale view looking
   * authoritative — an empty result and a failed fetch must not be
   * indistinguishable.
   */
  async function resync(id: string): Promise<void> {
    try {
      const response = await apiClient.get(`/api/chat/sessions/${encodeURIComponent(id)}`)
      const payload = response?.data as { data?: { messages?: BackendMessage[] } } | undefined
      const rawMessages = payload?.data?.messages
      if (!Array.isArray(rawMessages)) {
        syncError.value = 'Server snapshot contained no messages array'
        synchronized.value = false
        logger.warn('Resync returned an unexpected shape for session', id)
        return
      }
      const messages = rawMessages
        .map(toChatMessage)
        .filter((m): m is ChatMessage => m !== null)
      chatStore.applyServerSnapshot(id, messages)
      synchronized.value = true
      syncError.value = null
      logger.debug(`Resynchronized session ${id} with ${messages.length} messages`)
    } catch (error: unknown) {
      synchronized.value = false
      syncError.value = error instanceof Error ? error.message : String(error)
      logger.error(`Failed to resync session ${id}:`, error)
    }
  }

  function handleSessionEvent(event: LiveEvent): void {
    const id = sessionId.value
    if (!id) return
    if (event.event_type === SESSION_UPDATED) {
      const changes = event.payload?.changes as { title?: string } | undefined
      if (changes?.title) chatStore.updateSessionTitle(id, changes.title)
    } else if (event.event_type === SESSION_DELETED) {
      logger.debug(`Session ${id} deleted on another client`)
      chatStore.deleteSession(id)
    }
  }

  function handleChatEvent(event: LiveEvent): void {
    const id = sessionId.value
    if (!id) return
    if (event.event_type === CHAT_MESSAGE_ADDED) {
      const raw = event.payload?.message as BackendMessage | undefined
      if (!raw) return
      const message = toChatMessage(raw)
      if (!message) return
      // #14821: our own message coming back is a confirmation, not new content.
      if (!chatStore.confirmMessage(message.id, message.id)) {
        chatStore.applyRemoteMessage(id, message)
      }
    } else if (event.event_type === CHAT_CLEARED) {
      chatStore.applyServerSnapshot(id, [])
    }
  }

  function teardown(): void {
    disposers.forEach((dispose) => {
      try {
        dispose()
      } catch (error: unknown) {
        logger.debug('Error disposing session subscription:', error)
      }
    })
    disposers = []
  }

  async function attach(id: string): Promise<void> {
    teardown()
    synchronized.value = false

    const sessionChannel = `session:${id}`
    const chatChannel = `chat:${id}`

    disposers.push(liveEventService.subscribe(sessionChannel, handleSessionEvent))
    disposers.push(liveEventService.subscribe(chatChannel, handleChatEvent))

    // #14818: when the server cannot replay what we missed, the local view is
    // untrustworthy — rebuild from the snapshot rather than carrying on.
    disposers.push(
      liveEventService.onResync(chatChannel, () => {
        logger.debug(`Resync directive for ${chatChannel}`)
        void resync(id)
      })
    )
    disposers.push(
      liveEventService.onResync(sessionChannel, () => {
        void resync(id)
      })
    )

    await resync(id)
  }

  watch(
    sessionId,
    (id) => {
      if (id) {
        void attach(id)
      } else {
        teardown()
        synchronized.value = false
      }
    },
    { immediate: true }
  )

  onUnmounted(teardown)

  return { synchronized, syncError, resync }
}
