// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Accessibility composables for WCAG 2.1 AA compliance.
 *
 * Provides:
 * - useFocusTrap: re-exported from the shared kit (restoreFocus / initialFocus / listenOnDocument options)
 * - useKeyboardNav: arrow key navigation for lists/grids
 * - useAnnounce: screen reader announcements via aria-live
 *
 * Issue #754: Accessibility audit and improvements.
 */

import { ref, type Ref } from 'vue'

// Theme switching (light / dark / contrast / mono) lives in ./useSlmTheme (#18239); the former
// high-contrast and dark-mode toggles here are folded into it.


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

// useAnnounce (#18240) and useFocusTrap (#19688) live in the shared kit; re-exported so existing
// importers of this module keep working with ONE implementation.
// NOTE: the kit useFocusTrap is manual (activate/deactivate); the former local copy auto-activated
// through watch(containerRef), the kit one does not, so call activate() when the container shows.
export { useAnnounce, useFocusTrap } from '@autobot/ui'
