/**
 * Keyboard Event Composable
 *
 * Centralized keyboard event handling to eliminate duplicate keyboard logic across components.
 * Provides utilities for common keyboard interactions with automatic cleanup.
 *
 * Features:
 * - Key press detection with modifier support
 * - Accessibility helpers (clickable elements via keyboard)
 * - Escape/Enter key shortcuts
 * - Keyboard shortcut combinations
 * - Automatic event listener cleanup
 * - TypeScript type safety
 * - Conditional execution support
 *
 * Usage:
 * ```typescript
 * import { useKeyPress, useEscapeKey, useKeyboardShortcut } from '@/composables/useKeyboard'
 *
 * // Close modal on Escape
 * useEscapeKey(() => closeModal(), () => isModalOpen.value)
 *
 * // Submit form on Enter
 * useEnterKey(() => submitForm())
 *
 * // Keyboard shortcuts
 * useKeyboardShortcut('ctrl+s', () => saveDocument())
 * useKeyboardShortcut('meta+k', () => openCommandPalette())
 * ```
 */

import { onMounted, onUnmounted, type Ref } from 'vue'
import { resolveTarget } from './utils/target-resolver'

// ========================================
// Types & Interfaces
// ========================================

export type KeyboardEventKey =
  | 'Enter'
  | 'Escape'
  | 'Space'
  | 'Tab'
  | 'Backspace'
  | 'Delete'
  | 'ArrowUp'
  | 'ArrowDown'
  | 'ArrowLeft'
  | 'ArrowRight'
  | 'Home'
  | 'End'
  | 'PageUp'
  | 'PageDown'
  | string

export type KeyModifier = 'ctrl' | 'alt' | 'shift' | 'meta'

export interface KeyPressOptions {
  /**
   * Event type to listen for (default: 'keydown')
   */
  event?: 'keydown' | 'keyup' | 'keypress'

  /**
   * Target element to attach listener (default: document)
   */
  target?: HTMLElement | Document | Window | Ref<HTMLElement | undefined | null>

  /**
   * Prevent default browser behavior (default: false)
   */
  preventDefault?: boolean

  /**
   * Stop event propagation (default: false)
   */
  stopPropagation?: boolean

  /**
   * Condition that must be true for callback to execute
   * Use for conditional handlers (e.g., only when modal is open)
   */
  condition?: () => boolean
}

export interface KeyboardShortcutOptions extends KeyPressOptions {
  /**
   * Allow shortcut when input elements are focused (default: false)
   * Set to true if shortcut should work in forms/textareas
   */
  allowInInput?: boolean
}

// ========================================
// Core Key Press Handler
// ========================================

/**
 * Listen for specific key press with automatic cleanup
 *
 * @param key - Key to listen for (e.g., 'Enter', 'Escape')
 * @param callback - Function to call when key is pressed
 * @param options - Configuration options
 *
 * @example
 * ```typescript
 * useKeyPress('Escape', () => closeModal(), {
 *   condition: () => isModalOpen.value,
 *   preventDefault: true
 * })
 * ```
 */
export function useKeyPress(
  key: KeyboardEventKey,
  callback: (event: KeyboardEvent) => void,
  options: KeyPressOptions = {}
): void {
  const {
    event = 'keydown',
    target = document,
    preventDefault = false,
    stopPropagation = false,
    condition
  } = options

  const handleKeyPress = (e: Event): void => {
    const keyboardEvent = e as KeyboardEvent

    // Check if key matches
    if (keyboardEvent.key !== key) {
      return
    }

    // Check condition if provided
    if (condition && !condition()) {
      return
    }

    // Prevent default if requested
    if (preventDefault) {
      keyboardEvent.preventDefault()
    }

    // Stop propagation if requested
    if (stopPropagation) {
      keyboardEvent.stopPropagation()
    }

    // Execute callback
    callback(keyboardEvent)
  }

  // Cache target to ensure cleanup works even if ref changes
  let cachedTarget: HTMLElement | Document | Window | null = null

  onMounted(() => {
    cachedTarget = resolveTarget(target)
    cachedTarget.addEventListener(event, handleKeyPress)
  })

  onUnmounted(() => {
    if (cachedTarget) {
      cachedTarget.removeEventListener(event, handleKeyPress)
    }
  })
}

// ========================================
// Escape Key Helper
// ========================================

/**
 * Listen for Escape key press (common for closing modals/dialogs)
 *
 * @param callback - Function to call when Escape is pressed
 * @param condition - Optional condition that must be true
 * @param options - Additional options
 *
 * @example Close modal on Escape
 * ```typescript
 * useEscapeKey(() => closeModal(), () => isModalOpen.value)
 * ```
 *
 * @example Close with preventDefault
 * ```typescript
 * useEscapeKey(() => closeDialog(), undefined, { preventDefault: true })
 * ```
 */
export function useEscapeKey(
  callback: (event: KeyboardEvent) => void,
  condition?: () => boolean,
  options: Omit<KeyPressOptions, 'condition'> = {}
): void {
  useKeyPress('Escape', callback, {
    ...options,
    condition
  })
}

// ========================================
// Enter Key Helper
// ========================================

/**
 * Listen for Enter key press (common for form submission)
 *
 * @param callback - Function to call when Enter is pressed
 * @param condition - Optional condition that must be true
 * @param options - Additional options
 *
 * @example Submit form on Enter
 * ```typescript
 * useEnterKey(() => submitForm())
 * ```
 *
 * @example Submit with condition
 * ```typescript
 * useEnterKey(
 *   () => sendMessage(),
 *   () => messageText.value.trim() !== ''
 * )
 * ```
 */
export function useEnterKey(
  callback: (event: KeyboardEvent) => void,
  condition?: () => boolean,
  options: Omit<KeyPressOptions, 'condition'> = {}
): void {
  useKeyPress('Enter', callback, {
    ...options,
    condition
  })
}

// ========================================
// Keyboard Shortcut Handler
// ========================================

/**
 * Parse keyboard shortcut string (e.g., 'ctrl+s', 'meta+shift+k')
 */
function parseShortcut(shortcut: string): {
  key: string
  ctrl: boolean
  alt: boolean
  shift: boolean
  meta: boolean
} {
  const parts = shortcut.toLowerCase().split('+')
  const modifiers = {
    ctrl: parts.includes('ctrl'),
    alt: parts.includes('alt'),
    shift: parts.includes('shift'),
    meta: parts.includes('meta') || parts.includes('cmd')
  }

  // Last part is the key
  const key = parts[parts.length - 1]

  return {
    key,
    ...modifiers
  }
}

/**
 * Check if keyboard event matches shortcut
 * (Note: Currently unused but preserved for potential direct shortcut matching use cases)
 */
function _matchesShortcut(event: KeyboardEvent, shortcut: string): boolean {
  const parsed = parseShortcut(shortcut)

  return (
    event.key.toLowerCase() === parsed.key &&
    event.ctrlKey === parsed.ctrl &&
    event.altKey === parsed.alt &&
    event.shiftKey === parsed.shift &&
    event.metaKey === parsed.meta
  )
}

/**
 * Check if keyboard event matches pre-parsed shortcut
 * (More efficient than matchesShortcut for repeated checks)
 */
function matchesParsedShortcut(
  event: KeyboardEvent,
  parsed: { key: string; ctrl: boolean; alt: boolean; shift: boolean; meta: boolean }
): boolean {
  return (
    event.key.toLowerCase() === parsed.key &&
    event.ctrlKey === parsed.ctrl &&
    event.altKey === parsed.alt &&
    event.shiftKey === parsed.shift &&
    event.metaKey === parsed.meta
  )
}

/**
 * Check if event originated from input element
 */
function isInputEvent(event: KeyboardEvent): boolean {
  const target = event.target as HTMLElement | null

  // Null/undefined check
  if (!target) {
    return false
  }

  // Check if target has tagName property and it's a string
  if (typeof target.tagName !== 'string') {
    return false
  }

  const tagName = target.tagName.toLowerCase()
  return (
    tagName === 'input' ||
    tagName === 'textarea' ||
    tagName === 'select' ||
    (typeof target.isContentEditable === 'boolean' && target.isContentEditable)
  )
}

/**
 * Listen for keyboard shortcut combination
 *
 * @param shortcut - Shortcut string (e.g., 'ctrl+s', 'meta+k', 'ctrl+shift+p')
 * @param callback - Function to call when shortcut is pressed
 * @param options - Configuration options
 *
 * @example Save document
 * ```typescript
 * useKeyboardShortcut('ctrl+s', () => saveDocument(), {
 *   preventDefault: true
 * })
 * ```
 *
 * @example Command palette (Mac: Cmd+K, Windows/Linux: Ctrl+K)
 * ```typescript
 * useKeyboardShortcut('meta+k', () => openPalette())
 * useKeyboardShortcut('ctrl+k', () => openPalette())
 * ```
 *
 * @example Multiple modifiers
 * ```typescript
 * useKeyboardShortcut('ctrl+shift+p', () => openCommandPalette())
 * ```
 */
export function useKeyboardShortcut(
  shortcut: string,
  callback: (event: KeyboardEvent) => void,
  options: KeyboardShortcutOptions = {}
): void {
  const {
    event = 'keydown',
    target = document,
    preventDefault = true, // Default to true for shortcuts
    stopPropagation = false,
    condition,
    allowInInput = false
  } = options

  // Parse shortcut once at registration time (not on every keydown event)
  const parsedShortcut = parseShortcut(shortcut)

  const handleShortcut = (e: Event): void => {
    const keyboardEvent = e as KeyboardEvent

    // Check if shortcut matches (using pre-parsed shortcut)
    if (!matchesParsedShortcut(keyboardEvent, parsedShortcut)) {
      return
    }

    // Check if event is from input and we're not allowing that
    if (!allowInInput && isInputEvent(keyboardEvent)) {
      return
    }

    // Check condition if provided
    if (condition && !condition()) {
      return
    }

    // Prevent default if requested
    if (preventDefault) {
      keyboardEvent.preventDefault()
    }

    // Stop propagation if requested
    if (stopPropagation) {
      keyboardEvent.stopPropagation()
    }

    // Execute callback
    callback(keyboardEvent)
  }

  // Cache target to ensure cleanup works even if ref changes
  let cachedTarget: HTMLElement | Document | Window | null = null

  onMounted(() => {
    cachedTarget = resolveTarget(target)
    cachedTarget.addEventListener(event, handleShortcut)
  })

  onUnmounted(() => {
    if (cachedTarget) {
      cachedTarget.removeEventListener(event, handleShortcut)
    }
  })
}

// ========================================
// Accessibility: Clickable Element Helper
// ========================================

/**
 * Make element keyboard-accessible by simulating click on Enter/Space
 *
 * Returns event handlers to attach to your element
 *
 * @param callback - Function to call when Enter or Space is pressed
 * @param options - Configuration options
 * @returns Object with event handlers
 *
 * @example Make div clickable
 * ```vue
 * <script setup>
 * const { onKeyUp } = useClickableElement(() => handleClick())
 * </script>
 *
 * <template>
 *   <div
 *     tabindex="0"
 *     role="button"
 *     @click="handleClick"
 *     @keyup="onKeyUp"
 *   >
 *     Clickable Element
 *   </div>
 * </template>
 * ```
 *
 * @example With custom keys
 * ```typescript
 * const { onKeyUp } = useClickableElement(
 *   () => handleClick(),
 *   { keys: ['Enter'] } // Only Enter, not Space
 * )
 * ```
 */
export function useClickableElement(
  callback: (event: KeyboardEvent) => void,
  options: {
    keys?: KeyboardEventKey[]
    preventDefault?: boolean
  } = {}
): {
  onKeyUp: (event: KeyboardEvent) => void
  onKeyDown: (event: KeyboardEvent) => void
} {
  const { keys = ['Enter', ' '], preventDefault = true } = options

  const handleKey = (event: KeyboardEvent): void => {
    // Check if pressed key is in our list
    if (!keys.includes(event.key)) {
      return
    }

    if (preventDefault) {
      event.preventDefault()
    }

    callback(event)
  }

  return {
    onKeyUp: handleKey,
    onKeyDown: (event: KeyboardEvent) => {
      // Prevent default on keydown for Space to avoid page scroll
      if (event.key === ' ' && preventDefault) {
        event.preventDefault()
      }
    }
  }
}

// ========================================
// Arrow Key Navigation Helper
// ========================================

/**
 * Handle arrow key navigation with callbacks
 *
 * @param handlers - Callbacks for each arrow direction
 * @param options - Configuration options
 *
 * @example Navigate list
 * ```typescript
 * useArrowKeys({
 *   up: () => selectPrevious(),
 *   down: () => selectNext(),
 *   left: () => goBack(),
 *   right: () => goForward()
 * }, { preventDefault: true })
 * ```
 */
export function useArrowKeys(
  handlers: {
    up?: (event: KeyboardEvent) => void
    down?: (event: KeyboardEvent) => void
    left?: (event: KeyboardEvent) => void
    right?: (event: KeyboardEvent) => void
  },
  options: Omit<KeyPressOptions, 'condition'> = {}
): void {
  // Issue #156 Fix: addEventListener expects Event, not KeyboardEvent
  // Type as Event and assert to KeyboardEvent inside
  const handleArrowKey = (event: Event): void => {
    const keyEvent = event as KeyboardEvent
    switch (keyEvent.key) {
      case 'ArrowUp':
        if (handlers.up) {
          if (options.preventDefault) keyEvent.preventDefault()
          if (options.stopPropagation) keyEvent.stopPropagation()
          handlers.up(keyEvent)
        }
        break
      case 'ArrowDown':
        if (handlers.down) {
          if (options.preventDefault) keyEvent.preventDefault()
          if (options.stopPropagation) keyEvent.stopPropagation()
          handlers.down(keyEvent)
        }
        break
      case 'ArrowLeft':
        if (handlers.left) {
          if (options.preventDefault) keyEvent.preventDefault()
          if (options.stopPropagation) keyEvent.stopPropagation()
          handlers.left(keyEvent)
        }
        break
      case 'ArrowRight':
        if (handlers.right) {
          if (options.preventDefault) keyEvent.preventDefault()
          if (options.stopPropagation) keyEvent.stopPropagation()
          handlers.right(keyEvent)
        }
        break
    }
  }

  const target = options.target || document

  // Cache target to ensure cleanup works even if ref changes
  let cachedTarget: HTMLElement | Document | Window | null = null

  onMounted(() => {
    cachedTarget = resolveTarget(target)
    cachedTarget.addEventListener('keydown', handleArrowKey)
  })

  onUnmounted(() => {
    if (cachedTarget) {
      cachedTarget.removeEventListener('keydown', handleArrowKey)
    }
  })
}
