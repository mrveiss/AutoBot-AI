// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The composer's text box behaviour (#18243, moved unchanged in behaviour out of ChatInput.vue):
 * the character limit, auto-resize, Enter to send (Shift+Enter for a new line), and the slash
 * command dropdown with its keyboard navigation (GH#4449).
 */
import { computed, nextTick, ref, type Ref } from 'vue'
import { useSlashCommands } from '@/composables/useSlashCommands'
import type { SlashCommandPreset } from '@/types/api'

export const MAX_CHARACTERS = 4000
const NEAR_LIMIT_RATIO = 0.9
const MAX_INPUT_HEIGHT_PX = 150

export interface ComposerInputDeps {
  messageText: Ref<string>
  messageInput: Ref<HTMLTextAreaElement | undefined>
  canSend: Ref<boolean>
  sendMessage: () => void
}

function autoResize(target: HTMLTextAreaElement): void {
  target.style.height = 'auto'
  target.style.height = Math.min(target.scrollHeight, MAX_INPUT_HEIGHT_PX) + 'px'
}

/** Collapse the textarea back to one row (after a send clears it). */
export function resetTextareaHeight(messageInput: Ref<HTMLTextAreaElement | undefined>): void {
  nextTick(() => {
    if (messageInput.value) messageInput.value.style.height = 'auto'
  })
}

export function useComposerInput(deps: ComposerInputDeps) {
  const { messageText, messageInput } = deps
  const isInputFocused = ref(false)
  const slash = useSlashCommands(messageText)

  const characterCount = computed(() => messageText.value.length)
  const isNearLimit = computed(() => characterCount.value > MAX_CHARACTERS * NEAR_LIMIT_RATIO)
  const isTypingIndicatorVisible = computed(() => messageText.value.length > 0 && isInputFocused.value)

  function applySlashPreset(preset: SlashCommandPreset): void {
    messageText.value = slash.applyPreset(preset)
    slash.close()
  }

  /** Arrow keys move, Escape closes, Tab/Enter insert; true when the key was consumed. */
  function handleSlashKey(event: KeyboardEvent): boolean {
    if (!slash.showDropdown.value) return false
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      if (event.key === 'ArrowDown') slash.moveDown()
      else slash.moveUp()
      return true
    }
    if (event.key === 'Escape') {
      event.preventDefault()
      slash.close()
      return true
    }
    if (event.key !== 'Tab' && !(event.key === 'Enter' && !event.shiftKey)) return false
    const preset = slash.confirmSelection()
    if (!preset) return false
    event.preventDefault()
    applySlashPreset(preset)
    return true
  }

  function handleKeydown(event: KeyboardEvent): void {
    if (handleSlashKey(event)) return
    // Shift+Enter creates a new line, Enter sends
    if (event.key === 'Enter' && deps.canSend.value && !event.shiftKey) {
      event.preventDefault()
      deps.sendMessage()
      return
    }
    autoResize(event.target as HTMLTextAreaElement)
  }

  function handleInput(event: Event): void {
    const target = event.target as HTMLTextAreaElement
    if (target.value.length > MAX_CHARACTERS) {
      target.value = target.value.slice(0, MAX_CHARACTERS)
      messageText.value = target.value
    }
    autoResize(target)
    slash.onInput()
  }

  function focusInput(): void {
    nextTick(() => messageInput.value?.focus())
  }

  return {
    isInputFocused, characterCount, isNearLimit, isTypingIndicatorVisible,
    slashSuggestions: slash.suggestions, showSlashDropdown: slash.showDropdown,
    slashSelectedIndex: slash.selectedIndex, setSlashIndex: slash.setSelectedIndex, fetchPresets: slash.fetchPresets,
    applySlashPreset, handleKeydown, handleInput, focusInput,
  }
}
