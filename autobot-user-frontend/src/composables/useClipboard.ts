/**
 * Clipboard Composable
 *
 * Centralized clipboard operations to eliminate duplicate clipboard logic across components.
 * Supports modern Clipboard API with automatic fallback for older browsers.
 *
 * Features:
 * - Copy text to clipboard with browser compatibility
 * - Automatic fallback for older browsers (execCommand)
 * - Success/error state tracking
 * - Auto-reset "copied" state after timeout
 * - TypeScript type safety
 * - Browser support detection
 *
 * Usage:
 * ```typescript
 * import { useClipboard } from '@/composables/useClipboard'
 *
 * const {
 *   copy,
 *   copied,
 *   error,
 *   isSupported
 * } = useClipboard({
 *   copiedDuration: 2000 // Reset "copied" state after 2 seconds
 * })
 *
 * // In methods
 * const handleCopy = async () => {
 *   await copy('Text to copy')
 *   if (copied.value) {
 *     console.log('Copied successfully!')
 *   }
 * }
 *
 * // In template
 * <button @click="copy(someText)">
 *   <i :class="copied ? 'fas fa-check' : 'fas fa-copy'"></i>
 *   {{ copied ? 'Copied!' : 'Copy' }}
 * </button>
 * ```
 */

import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { createLogger } from '@/utils/debugUtils'

// Create scoped logger for useClipboard
const logger = createLogger('useClipboard')

// ========================================
// Types & Interfaces
// ========================================

export interface ClipboardOptions {
  /**
   * Duration (ms) to show "copied" state before auto-reset (default: 2000)
   * Set to 0 to disable auto-reset
   */
  copiedDuration?: number

  /**
   * Callback on successful copy
   * @param text - Copied text
   */
  onSuccess?: (text: string) => void | Promise<void>

  /**
   * Callback on copy error
   * @param error - Error object or message
   */
  onError?: (error: Error | string) => void | Promise<void>

  /**
   * Legacy mode: use execCommand instead of Clipboard API (default: false)
   * Useful for testing fallback behavior
   */
  legacyMode?: boolean
}

export interface UseClipboardReturn {
  /**
   * Copy text to clipboard
   * @param text - Text to copy
   * @returns Promise that resolves to true if successful, false otherwise
   */
  copy: (text: string) => Promise<boolean>

  /**
   * Whether text was recently copied (resets after copiedDuration)
   */
  copied: Readonly<Ref<boolean>>

  /**
   * Error from last copy attempt (null if successful)
   */
  error: Readonly<Ref<Error | string | null>>

  /**
   * Whether Clipboard API is supported
   */
  isSupported: ComputedRef<boolean>

  /**
   * Text that was last copied
   */
  copiedText: Readonly<Ref<string>>

  /**
   * Manually reset copied state
   */
  resetCopied: () => void
}

// ========================================
// Main Composable
// ========================================

/**
 * Create clipboard utilities
 *
 * @param options - Clipboard configuration
 * @returns Clipboard state and methods
 *
 * @example Basic usage
 * ```typescript
 * const { copy, copied } = useClipboard()
 * await copy('Hello world')
 * ```
 *
 * @example With callbacks
 * ```typescript
 * const { copy } = useClipboard({
 *   onSuccess: (text) => console.log(`Copied: ${text}`),
 *   onError: (err) => console.error('Copy failed:', err)
 * })
 * ```
 */
export function useClipboard(options: ClipboardOptions = {}): UseClipboardReturn {
  const {
    copiedDuration = 2000,
    onSuccess,
    onError,
    legacyMode = false
  } = options

  // State
  const copied = ref<boolean>(false)
  const error = ref<Error | string | null>(null)
  const copiedText = ref<string>('')

  // Timer for auto-reset
  let resetTimer: ReturnType<typeof setTimeout> | null = null

  // Computed: Is Clipboard API supported
  const isSupported = computed(() => {
    if (legacyMode) return false
    return (
      typeof navigator !== 'undefined' &&
      navigator.clipboard != null &&
      typeof navigator.clipboard.writeText === 'function'
    )
  })

  /**
   * Reset copied state
   */
  const resetCopied = (): void => {
    copied.value = false
    copiedText.value = ''

    if (resetTimer) {
      clearTimeout(resetTimer)
      resetTimer = null
    }
  }

  /**
   * Set copied state with auto-reset
   */
  const setCopied = (text: string): void => {
    copied.value = true
    copiedText.value = text

    // Auto-reset after duration
    if (copiedDuration > 0) {
      if (resetTimer) clearTimeout(resetTimer)

      resetTimer = setTimeout(() => {
        resetCopied()
      }, copiedDuration)
    }
  }

  /**
   * Fallback copy using execCommand (for older browsers)
   */
  const copyFallback = (text: string): boolean => {
    // Create temporary textarea
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    textarea.style.left = '-9999px'

    let appended = false

    try {
      document.body.appendChild(textarea)
      appended = true

      // Select and copy
      textarea.select()
      textarea.setSelectionRange(0, text.length)

      const success = document.execCommand('copy')
      return success
    } catch (err) {
      logger.error('Fallback copy failed:', err)
      return false
    } finally {
      // Always clean up textarea, even if copy fails
      if (appended) {
        try {
          document.body.removeChild(textarea)
        } catch (_cleanupErr) {
          // Ignore cleanup errors
        }
      }
    }
  }

  /**
   * Copy text to clipboard
   */
  const copy = async (text: string): Promise<boolean> => {
    // Validate input
    if (!text || typeof text !== 'string' || text.trim() === '') {
      const errorMsg = 'Invalid text: must be a non-empty string'
      error.value = errorMsg
      if (onError) {
        await onError(errorMsg)
      }
      return false
    }

    // Reset state
    error.value = null
    copied.value = false

    try {
      // Try modern Clipboard API first
      if (isSupported.value) {
        await navigator.clipboard.writeText(text)
      } else {
        // Fallback for older browsers
        const success = copyFallback(text)

        if (!success) {
          throw new Error('Clipboard copy failed')
        }
      }

      // Success
      setCopied(text)

      if (onSuccess) {
        await onSuccess(text)
      }

      return true

    } catch (err: any) {
      // Error handling
      const errorObj = err instanceof Error ? err : new Error(String(err))
      error.value = errorObj

      logger.error('Copy failed:', errorObj)

      if (onError) {
        await onError(errorObj)
      }

      return false
    }
  }

  return {
    copy,
    copied: computed(() => copied.value),
    error: computed(() => error.value),
    isSupported,
    copiedText: computed(() => copiedText.value),
    resetCopied
  }
}

// ========================================
// Helper: Copy with Confirmation
// ========================================

/**
 * Helper for copying with automatic success message
 *
 * @param text - Text to copy
 * @param successMessage - Message to show on success (default: 'Copied!')
 * @returns Clipboard composable with built-in success message
 *
 * @example
 * ```typescript
 * const { copy, copied } = useClipboardWithMessage()
 *
 * <button @click="copy('Hello')">
 *   {{ copied ? 'Copied!' : 'Copy' }}
 * </button>
 * ```
 */
export function useClipboardWithMessage(
  successMessage: string = 'Copied!',
  errorMessage: string = 'Failed to copy'
) {
  const message = ref<string>('')
  const messageType = ref<'success' | 'error' | ''>('')

  const clipboard = useClipboard({
    onSuccess: () => {
      message.value = successMessage
      messageType.value = 'success'
    },
    onError: () => {
      message.value = errorMessage
      messageType.value = 'error'
    }
  })

  return {
    ...clipboard,
    message: computed(() => message.value),
    messageType: computed(() => messageType.value)
  }
}

// ========================================
// Helper: Copy DOM Element Text
// ========================================

/**
 * Helper for copying text from a DOM element
 *
 * @param element - DOM element or ref to element
 * @param options - Clipboard options
 * @returns Clipboard composable
 *
 * @example
 * ```typescript
 * const codeElement = ref<HTMLElement>()
 * const { copyElement } = useClipboardElement()
 *
 * <pre ref="codeElement">const code = 'example'</pre>
 * <button @click="copyElement(codeElement)">Copy Code</button>
 * ```
 */
export function useClipboardElement(options: ClipboardOptions = {}) {
  const clipboard = useClipboard(options)

  const copyElement = async (
    element: HTMLElement | Ref<HTMLElement | undefined>
  ): Promise<boolean> => {
    const el = element instanceof HTMLElement ? element : element.value

    if (!el) {
      logger.error('Invalid element')
      return false
    }

    const text = el.textContent || el.innerText || ''
    return clipboard.copy(text)
  }

  return {
    ...clipboard,
    copyElement
  }
}
