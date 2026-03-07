/**
 * Issue #1314: Virtual scrolling composable for chat message list.
 *
 * Wraps @tanstack/vue-virtual to virtualise the message list, only
 * rendering messages within the viewport + a small overscan buffer.
 * Provides stick-to-bottom behaviour for streaming and session changes.
 */

import {
  ref,
  computed,
  watch,
  nextTick,
  onMounted,
  onUnmounted,
  type Ref,
  type ComputedRef,
} from 'vue'
import { useVirtualizer } from '@tanstack/vue-virtual'
import type { ChatMessage } from '@/stores/useChatStore'

interface UseVirtualChatScrollOptions {
  messagesContainerRef: Ref<HTMLElement | undefined>
  filteredMessages: ComputedRef<ChatMessage[]>
  isTyping: ComputedRef<boolean>
  currentSessionId: ComputedRef<string | null>
}

const BOTTOM_THRESHOLD_PX = 40
const OVERSCAN_COUNT = 5

export function useVirtualChatScroll(opts: UseVirtualChatScrollOptions) {
  const {
    messagesContainerRef,
    filteredMessages,
    currentSessionId,
  } = opts

  const scrollContainerRef = ref<HTMLElement | null>(null)
  const isStuckToBottom = ref(true)

  // --- Tiered height estimate by message properties ---
  const estimateSize = (index: number): number => {
    const msg = filteredMessages.value[index]
    if (!msg) return 140

    if (
      msg.metadata?.requires_approval &&
      !msg.metadata?.approval_status
    )
      return 400
    if (msg.type === 'overseer_plan') return 300
    if (msg.type === 'overseer_step') return 180
    if (msg.content && /```[\s\S]{200,}/.test(msg.content)) return 350
    if ((msg.metadata?.citations?.length ?? 0) > 0) return 250
    if ((msg.attachments?.length ?? 0) > 0) return 200
    if (msg.sender === 'user' && (msg.content?.length ?? 0) < 100)
      return 80
    return 140
  }

  // --- Virtualizer ---
  const virtualizer = useVirtualizer(
    computed(() => ({
      count: filteredMessages.value.length,
      getScrollElement: () => scrollContainerRef.value,
      estimateSize,
      overscan: OVERSCAN_COUNT,
    })),
  )

  const virtualItems = computed(() => virtualizer.value.getVirtualItems())
  const totalSize = computed(() => virtualizer.value.getTotalSize())

  const measureElement = (el: Element) => {
    virtualizer.value.measureElement(el)
  }

  // --- Stick-to-bottom scroll tracking ---
  const onScroll = () => {
    const el = scrollContainerRef.value
    if (!el) return
    const distFromBottom =
      el.scrollHeight - el.scrollTop - el.clientHeight
    isStuckToBottom.value = distFromBottom <= BOTTOM_THRESHOLD_PX
  }

  const scrollToBottom = () => {
    if (!isStuckToBottom.value) return
    const count = filteredMessages.value.length
    if (count > 0) {
      virtualizer.value.scrollToIndex(count - 1, {
        align: 'end',
        behavior: 'auto',
      })
    }
  }

  // --- Mount: locate external scroll container ---
  onMounted(() => {
    const el = messagesContainerRef.value?.closest(
      '.overflow-y-auto',
    ) as HTMLElement | null
    scrollContainerRef.value = el
    if (el) {
      el.addEventListener('scroll', onScroll, { passive: true })
    }
    // Initial scroll to bottom
    nextTick(scrollToBottom)
  })

  onUnmounted(() => {
    scrollContainerRef.value?.removeEventListener('scroll', onScroll)
  })

  // --- Session change: reset stick-to-bottom ---
  watch(currentSessionId, () => {
    isStuckToBottom.value = true
    nextTick(scrollToBottom)
  })

  // --- Streaming: re-scroll as last message grows ---
  watch(
    () => {
      const msgs = filteredMessages.value
      const last = msgs[msgs.length - 1]
      return last?.content?.length ?? 0
    },
    () => {
      if (isStuckToBottom.value) {
        nextTick(scrollToBottom)
      }
    },
  )

  return {
    virtualItems,
    totalSize,
    measureElement,
    scrollToBottom,
    isStuckToBottom,
  }
}
