// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
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

import { getCurrentScope, onScopeDispose, type Ref } from 'vue'

/**
 * CSS selector matching natively-focusable elements plus anything with an
 * explicit non-negative tabindex. Kept as a module-level constant so all
 * consumers agree on what "focusable" means — change in one place if
 * `details` / `summary` / contenteditable ever need including.
 *
 * Note: this selector is CSS-only. Use `isTabbable()` to additionally
 * filter out elements that browsers actually skip during Tab navigation
 * (aria-hidden subtrees, [inert] containers, display:none / visibility:
 * hidden ancestors).
 */
export const FOCUSABLE_SELECTOR =
  'button:not(:disabled), [href], input:not(:disabled), select:not(:disabled), ' +
  'textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'

/**
 * True if `el` is genuinely tabbable in the current DOM — matches the
 * FOCUSABLE_SELECTOR shape AND respects the runtime visibility / inertness
 * filters that the CSS selector alone can't express.
 *
 * Mirrors the practical "tabbability" detection used by industry libraries
 * (`focus-trap`, `@headlessui/vue`, `@radix-ui/react-focus-scope`):
 *   - Skip descendants of `[aria-hidden="true"]` subtrees
 *   - Skip descendants of `[inert]` containers
 *   - Skip elements with a `display:none` ancestor (walk via
 *     `getComputedStyle` rather than `offsetParent` so jsdom-based unit
 *     tests behave the same as real browsers; jsdom's offsetParent is
 *     unreliable because it doesn't compute layout)
 *
 * Filed as #5373.
 */
export function isTabbable(el: HTMLElement): boolean {
  if (el.closest('[aria-hidden="true"]')) return false
  if (el.closest('[inert]')) return false

  // Walk the ancestor chain for display:none. getComputedStyle returns the
  // resolved display value (browsers report defaults like "block"/"inline";
  // jsdom returns "" for unstyled but reports inline `style.display=none`).
  // Either way, a hit on "none" is reliable across both environments.
  let current: HTMLElement | null = el
  while (current) {
    if (getComputedStyle(current).display === 'none') return false
    current = current.parentElement
  }
  return true
}

export interface UseFocusTrapOptions {
  /** `deactivate()` refocuses the element that was focused at `activate()`. Default false. */
  restoreFocus?: boolean
  /** `activate()` focuses the first tabbable element in the container. Default false. */
  initialFocus?: boolean
  /**
   * `activate()` also listens for `keydown` on `document` (removed by
   * `deactivate()`), for callers that cannot bind `onKeydown` on the container.
   * Default false.
   */
  listenOnDocument?: boolean
}

export interface UseFocusTrapReturn {
  /**
   * `keydown` handler to bind on the container. No-op for non-Tab keys and
   * when the container ref is unset — safe to attach unconditionally.
   */
  onKeydown: (event: KeyboardEvent) => void
  /** Records the focused element and focuses the first tabbable, per the options. */
  activate: () => void
  /** Removes the document listener and restores focus, per the options. Idempotent. */
  deactivate: () => void
}

/**
 * Focus trap composable.
 *
 * @param containerRef  Ref to the HTMLElement whose focusable descendants
 *                      should be wrapped. When null, the handler no-ops —
 *                      callers don't need a guard for the "before mounted"
 *                      window.
 * @param options       Opt-in focus restoration, initial focus and a
 *                      document-level listener; all off by default, so a
 *                      caller that only binds `onKeydown` is unchanged.
 */
export function useFocusTrap(
  containerRef: Ref<HTMLElement | null>,
  options: UseFocusTrapOptions = {}
): UseFocusTrapReturn {
  let previousFocus: HTMLElement | null = null
  let active = false

  function tabbables(): HTMLElement[] {
    if (!containerRef.value) return []
    return Array.from(
      containerRef.value.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)
    ).filter(isTabbable)
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab' || !containerRef.value) return

    // CSS-match → tabbability filter. The filter excludes aria-hidden /
    // inert / display:none descendants that the browser would skip
    // during Tab navigation but querySelectorAll returns by structure.
    const focusables = tabbables()
    if (focusables.length === 0) return

    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const current = document.activeElement

    if (event.shiftKey && current === first) {
      event.preventDefault()
      last.focus()
    } else if (!event.shiftKey && current === last) {
      event.preventDefault()
      first.focus()
    }
    // Otherwise allow default Tab behavior.
  }

  function activate(): void {
    if (active) return
    active = true
    previousFocus = document.activeElement as HTMLElement | null
    if (options.listenOnDocument) document.addEventListener('keydown', onKeydown)
    if (options.initialFocus) tabbables()[0]?.focus()
  }

  function deactivate(): void {
    if (!active) return
    active = false
    if (options.listenOnDocument) document.removeEventListener('keydown', onKeydown)
    if (options.restoreFocus && previousFocus) previousFocus.focus()
    previousFocus = null
  }

  if (getCurrentScope()) onScopeDispose(deactivate)

  return { onKeydown, activate, deactivate }
}
