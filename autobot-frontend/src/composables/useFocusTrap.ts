/**
 * AutoBot - AI-Powered Automation Platform
 * Copyright (c) 2025 mrveiss
 * Author: mrveiss
 *
 * useFocusTrap Composable (#5130)
 *
 * Tab / Shift+Tab focus trap that wraps focus inside a container. Extracted
 * from the byte-for-byte identical handlers in BaseModal.vue and
 * HostSelectionDialog.vue (introduced by #5121 / PR #5016).
 *
 * Only intercepts when focus would leave the container — middle-of-form
 * Tabs fall through to browser default, so devtools / outside clicks stay
 * usable during debugging.
 *
 * Consumer pattern:
 *
 *   const dialogRef = ref<HTMLElement | null>(null)
 *   const { onKeydown } = useFocusTrap(dialogRef)
 *
 *   <template><div ref="dialogRef" @keydown="onKeydown">...</div></template>
 */

import type { Ref } from 'vue'

/**
 * CSS selector matching natively-focusable elements plus anything with an
 * explicit non-negative tabindex. Kept as a module-level constant so all
 * consumers agree on what "focusable" means — change in one place if
 * `details` / `summary` / contenteditable ever need including.
 */
export const FOCUSABLE_SELECTOR =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), ' +
  'textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

export interface UseFocusTrapReturn {
  /**
   * `keydown` handler to bind on the container. No-op for non-Tab keys and
   * when the container ref is unset — safe to attach unconditionally.
   */
  onKeydown: (event: KeyboardEvent) => void
}

/**
 * Focus trap composable.
 *
 * @param containerRef  Ref to the HTMLElement whose focusable descendants
 *                      should be wrapped. When null, the handler no-ops —
 *                      callers don't need a guard for the "before mounted"
 *                      window.
 */
export function useFocusTrap(
  containerRef: Ref<HTMLElement | null>
): UseFocusTrapReturn {
  function onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab' || !containerRef.value) return

    const focusables = containerRef.value.querySelectorAll<HTMLElement>(
      FOCUSABLE_SELECTOR
    )
    if (focusables.length === 0) return

    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const active = document.activeElement

    if (event.shiftKey && active === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && active === last) {
      event.preventDefault()
      first.focus()
    }
    // Otherwise allow default Tab behavior.
  }

  return { onKeydown }
}
