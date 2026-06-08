// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
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
 * Fallback order: first focusable descendant → the container itself
 * (requires `tabindex="-1"`) → no-op.
 */

import { nextTick, type Ref } from 'vue'
import { FOCUSABLE_SELECTOR } from './useFocusTrap'

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
export function useInitialFocus(
  containerRef: Ref<HTMLElement | null>
): UseInitialFocusReturn {
  async function focusFirst(): Promise<void> {
    await nextTick()
    if (!containerRef.value) return
    const first = containerRef.value.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)
    if (first) {
      first.focus()
    } else {
      containerRef.value.focus()
    }
  }

  return { focusFirst }
}
