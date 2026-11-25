// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/useChatStore'
import { useCommandPaletteHotkey, useKeyboardShortcut } from '@/composables/useKeyboard'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('useGlobalShortcuts')

export interface GlobalShortcutsOptions {
  /** Ref to the CommandPalette component instance with an `open()` method */
  commandPaletteRef: Ref<{ open: () => void } | null>
}

/**
 * Registers app-wide keyboard shortcuts for power-user navigation.
 *
 * Shortcuts:
 *   Ctrl/Cmd+K  — open command palette
 *   Ctrl/Cmd+N  — new chat (navigates to /chat)
 *   Ctrl/Cmd+Shift+O — new chat, also from inside the composer
 *   Ctrl/Cmd+1–9 — switch to nth conversation in the chat store
 *   Escape      — handled per-component; this composable does not capture it globally
 *
 * Call once from App.vue inside a component setup context.
 */
export function useGlobalShortcuts({ commandPaletteRef }: GlobalShortcutsOptions): void {
  const router = useRouter()
  const chatStore = useChatStore()

  // Ctrl/Cmd+K — command palette
  useCommandPaletteHotkey(() => {
    logger.debug('Ctrl/Cmd+K: opening command palette')
    commandPaletteRef.value?.open()
  })

  // Ctrl/Cmd+N and Ctrl/Cmd+Shift+O — new chat. The second is the one the Chat mockup shows on the
  // New chat button (#18243); it also works while the composer has focus.
  const newChat = (): void => {
    logger.debug('new chat shortcut')
    chatStore.createNewSession()
    router.push('/chat')
  }
  useKeyboardShortcut('ctrl+n', newChat, { preventDefault: true })
  useKeyboardShortcut('meta+n', newChat, { preventDefault: true })
  useKeyboardShortcut('ctrl+shift+o', newChat, { preventDefault: true, allowInInput: true })
  useKeyboardShortcut('meta+shift+o', newChat, { preventDefault: true, allowInInput: true })

  // Ctrl/Cmd+1–9 — switch to numbered conversation
  for (let i = 1; i <= 9; i++) {
    const digit = String(i)
    const index = i - 1

    useKeyboardShortcut(`ctrl+${digit}`, () => {
      const sessions = chatStore.sessions
      if (index < sessions.length) {
        logger.debug(`Ctrl+${digit}: switching to session ${index}`)
        chatStore.switchToSession(sessions[index].id)
        router.push('/chat')
      }
    }, { preventDefault: true })

    useKeyboardShortcut(`meta+${digit}`, () => {
      const sessions = chatStore.sessions
      if (index < sessions.length) {
        logger.debug(`Cmd+${digit}: switching to session ${index}`)
        chatStore.switchToSession(sessions[index].id)
        router.push('/chat')
      }
    }, { preventDefault: true })
  }
}
