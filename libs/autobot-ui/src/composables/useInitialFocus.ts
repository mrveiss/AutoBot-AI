// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * useInitialFocus Composable (#5411)
 *
 * Third primitive in the dialog-a11y trio (with useFocusTrap #5130 and
 * useFocusRestore #5356). Returns a `focusFirst()` helper the caller
 * invokes from their open / mount / watch handler.
 *
 * Caller-controlled (not auto-fire on a trigger ref) because initial-focus
 * timing varies — transition complete, mount, or after async data load —
 * and the right moment is consumer-specific.
 *
 * Fallback order: a `data-autofocus` target → first focusable descendant → the container itself
 * (requires `tabindex="-1"`) → no-op.
 */

import { nextTick, type Ref } from 'vue'
import { FOCUSABLE_SELECTOR, isTabbable } from './useFocusTrap'

export interface UseInitialFocusReturn {
  /**
   * Move focus into the container. Awaits `nextTick()` so callers can fire
   * this in a watch immediately after `show.value = true` without worrying
   * about the v-if'd children not being mounted yet.
   */
  focusFirst: () => Promise<void>
}

/**
 * @param containerRef  Ref to the dialog/panel element. Falls back to
 *                      focusing the container itself if no focusable
 *                      descendant is found, which requires the container
 *                      to have `tabindex="-1"` to actually accept focus.
 */
/**
 * An element marked `data-autofocus` (or the first focusable inside it, for a field component
 * that puts data-* attributes on a wrapper) takes initial focus ahead of the first focusable.
 */
function preferredTarget(container: HTMLElement): HTMLElement | null {
  for (const marked of container.querySelectorAll<HTMLElement>('[data-autofocus]')) {
    // A marked wrapper offers its own focusable descendants in order; one that is not rendered
    // (display:none) cannot take focus, so the first that can wins and the fallback stays alive.
    const candidates = marked.matches(FOCUSABLE_SELECTOR)
      ? [marked]
      : Array.from(marked.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
    const target = candidates.find(isTabbable)
    if (target) return target
  }
  return null
}

export function useInitialFocus(
  containerRef: Ref<HTMLElement | null>
): UseInitialFocusReturn {
  async function focusFirst(): Promise<void> {
    await nextTick()
    if (!containerRef.value) return
    const first = preferredTarget(containerRef.value)
      ?? containerRef.value.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
    if (first) {
      first.focus()
    } else {
      containerRef.value.focus()
    }
  }

  return { focusFirst }
}
