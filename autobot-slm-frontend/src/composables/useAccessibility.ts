// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss

/**
 * Accessibility composables for WCAG 2.1 AA compliance.
 *
 * Provides:
 * - useFocusTrap: traps focus within modals/dialogs
 * - useKeyboardNav: arrow key navigation for lists/grids
 * - useHighContrast: high contrast mode toggle with localStorage
 * - useAnnounce: screen reader announcements via aria-live
 *
 * Issue #754: Accessibility audit and improvements.
 */

import { ref, onMounted, onUnmounted, watch, type Ref } from 'vue'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('Accessibility')

// ─── High Contrast Mode ───────────────────────────────────────

const CONTRAST_STORAGE_KEY = 'autobot-high-contrast'

/** Shared reactive state for high contrast mode across all consumers. */
const highContrastEnabled = ref(false)

/**
 * Apply or remove the high-contrast data attribute on the root element.
 *
 * Helper for useHighContrast (Issue #754).
 */
function applyHighContrast(enabled: boolean): void {
  if (enabled) {
    document.documentElement.setAttribute('data-theme', 'high-contrast')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

/**
 * High contrast mode composable with localStorage persistence.
 *
 * Issue #754: Accessibility audit and improvements.
 */
export function useHighContrast() {
  function toggle(): void {
    highContrastEnabled.value = !highContrastEnabled.value
    localStorage.setItem(CONTRAST_STORAGE_KEY, String(highContrastEnabled.value))
    applyHighContrast(highContrastEnabled.value)
    logger.info('High contrast mode:', highContrastEnabled.value ? 'enabled' : 'disabled')
  }

  function init(): void {
    const stored = localStorage.getItem(CONTRAST_STORAGE_KEY)
    if (stored === 'true') {
      highContrastEnabled.value = true
      applyHighContrast(true)
    }
  }

  return {
    enabled: highContrastEnabled,
    toggle,
    init,
  }
}


// ─── Focus Trap ───────────────────────────────────────────────

/** Selector for all focusable elements within a container. */
const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(', ')

/**
 * Trap focus within a container element (for modals/dialogs).
 *
 * Issue #754: Accessibility audit and improvements.
 */
export function useFocusTrap(containerRef: Ref<HTMLElement | null>) {
  let previousFocus: HTMLElement | null = null

  function getFocusableElements(): HTMLElement[] {
    if (!containerRef.value) return []
    return Array.from(containerRef.value.querySelectorAll(FOCUSABLE_SELECTOR))
  }

  function handleKeyDown(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return

    const focusable = getFocusableElements()
    if (focusable.length === 0) return

    const first = focusable[0]
    const last = focusable[focusable.length - 1]

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault()
      first.focus()
    }
  }

  function activate(): void {
    previousFocus = document.activeElement as HTMLElement
    document.addEventListener('keydown', handleKeyDown)

    // Focus first focusable element in the container
    const focusable = getFocusableElements()
    if (focusable.length > 0) {
      focusable[0].focus()
    }
  }

  function deactivate(): void {
    document.removeEventListener('keydown', handleKeyDown)
    if (previousFocus) {
      previousFocus.focus()
      previousFocus = null
    }
  }

  // Auto-activate/deactivate based on container visibility
  watch(containerRef, (el) => {
    if (el) {
      activate()
    } else {
      deactivate()
    }
  })

  onUnmounted(() => {
    deactivate()
  })

  return { activate, deactivate }
}


// ─── Keyboard Navigation ──────────────────────────────────────

interface KeyboardNavOptions {
  /** Orientation: 'vertical' for up/down, 'horizontal' for left/right, 'grid' for both. */
  orientation?: 'vertical' | 'horizontal' | 'grid'
  /** Number of columns for grid orientation. */
  columns?: number
  /** Whether navigation wraps at boundaries. */
  wrap?: boolean
  /** Callback when an item is activated (Enter/Space). */
  onActivate?: (index: number) => void
}

/**
 * Arrow key navigation for lists, grids, and tab panels.
 *
 * Issue #754: Accessibility audit and improvements.
 */
export function useKeyboardNav(
  items: Ref<HTMLElement[]>,
  options: KeyboardNavOptions = {}
) {
  const {
    orientation = 'vertical',
    columns = 1,
    wrap = true,
    onActivate,
  } = options

  const activeIndex = ref(0)

  function moveFocus(newIndex: number): void {
    const count = items.value.length
    if (count === 0) return

    let idx = newIndex
    if (wrap) {
      idx = ((idx % count) + count) % count
    } else {
      idx = Math.max(0, Math.min(count - 1, idx))
    }

    activeIndex.value = idx
    items.value[idx]?.focus()
  }

  function handleKeyDown(event: KeyboardEvent): void {
    const count = items.value.length
    if (count === 0) return

    let handled = false

    switch (event.key) {
      case 'ArrowDown':
        if (orientation === 'vertical' || orientation === 'grid') {
          moveFocus(activeIndex.value + (orientation === 'grid' ? columns : 1))
          handled = true
        }
        break
      case 'ArrowUp':
        if (orientation === 'vertical' || orientation === 'grid') {
          moveFocus(activeIndex.value - (orientation === 'grid' ? columns : 1))
          handled = true
        }
        break
      case 'ArrowRight':
        if (orientation === 'horizontal' || orientation === 'grid') {
          moveFocus(activeIndex.value + 1)
          handled = true
        }
        break
      case 'ArrowLeft':
        if (orientation === 'horizontal' || orientation === 'grid') {
          moveFocus(activeIndex.value - 1)
          handled = true
        }
        break
      case 'Home':
        moveFocus(0)
        handled = true
        break
      case 'End':
        moveFocus(count - 1)
        handled = true
        break
      case 'Enter':
      case ' ':
        if (onActivate) {
          onActivate(activeIndex.value)
          handled = true
        }
        break
    }

    if (handled) {
      event.preventDefault()
    }
  }

  return {
    activeIndex,
    handleKeyDown,
    moveFocus,
  }
}


// ─── Screen Reader Announcements ──────────────────────────────

/**
 * Announce messages to screen readers via an aria-live region.
 *
 * Issue #754: Accessibility audit and improvements.
 */
export function useAnnounce() {
  let liveRegion: HTMLElement | null = null

  function ensureLiveRegion(): HTMLElement {
    if (liveRegion) return liveRegion

    const existing = document.getElementById('a11y-live-region')
    if (existing) {
      liveRegion = existing
      return liveRegion
    }

    liveRegion = document.createElement('div')
    liveRegion.id = 'a11y-live-region'
    liveRegion.setAttribute('aria-live', 'polite')
    liveRegion.setAttribute('aria-atomic', 'true')
    liveRegion.setAttribute('role', 'status')
    liveRegion.className = 'sr-only'
    document.body.appendChild(liveRegion)
    return liveRegion
  }

  /**
   * Announce a message to screen readers.
   *
   * Helper for useAnnounce (Issue #754).
   */
  function announce(message: string, priority: 'polite' | 'assertive' = 'polite'): void {
    const region = ensureLiveRegion()
    region.setAttribute('aria-live', priority)
    // Clear then set to ensure re-announcement
    region.textContent = ''
    requestAnimationFrame(() => {
      region.textContent = message
    })
  }

  onMounted(() => {
    ensureLiveRegion()
  })

  return { announce }
}
