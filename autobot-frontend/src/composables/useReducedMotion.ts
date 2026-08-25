// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * `prefers-reduced-motion`, for motion that CSS cannot reach.
 *
 * #14770: our stylesheet already honours the preference globally — a universal
 * kill switch zeroes every `animation-duration` and `transition-duration`. But
 * a media query cannot reach motion a script starts, and several of ours do:
 * router smooth-scroll on every navigation, cytoscape graph layouts animating
 * their way to equilibrium on load, and a viewport tween. Those fired
 * regardless of the setting, for exactly the users who asked for less of them.
 *
 * Two entry points, because the call sites are not all components:
 *   - `isReducedMotion()` reads the preference live. Safe from a router
 *     `scrollBehavior`, a plain module, or anywhere outside a component's
 *     lifecycle.
 *   - `useReducedMotion()` returns a ref that tracks changes, for anything
 *     that must re-render when the user flips the setting mid-session.
 *
 * Deliberately no module-level cache: the live read cannot go stale, and a
 * shared ref would leak one test's stubbed preference into the next.
 */

import { ref, onScopeDispose, type Ref } from 'vue'

const REDUCED_MOTION_QUERY = '(prefers-reduced-motion: reduce)'

/** True when the user has asked the platform for reduced motion. */
export function isReducedMotion(): boolean {
  // `matchMedia` is absent in SSR and in some test environments; absence means
  // "no stated preference", never an exception on a motion decision.
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  try {
    return window.matchMedia(REDUCED_MOTION_QUERY).matches
  } catch {
    return false
  }
}

/**
 * The scroll behaviour to use for a scroll the app initiates.
 *
 * Exists so call sites read as intent rather than as a repeated ternary, and
 * so there is one place to change if the fallback ever needs to be something
 * other than `'auto'`.
 */
export function scrollBehavior(): ScrollBehavior {
  return isReducedMotion() ? 'auto' : 'smooth'
}

/** Reactive form, for components that must re-render when the setting flips. */
export function useReducedMotion(): { prefersReducedMotion: Ref<boolean> } {
  const prefersReducedMotion = ref(isReducedMotion())

  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    try {
      const query = window.matchMedia(REDUCED_MOTION_QUERY)
      const onChange = (event: MediaQueryListEvent) => {
        prefersReducedMotion.value = event.matches
      }
      // `addListener` is the pre-2019 spelling; some environments still only
      // expose that one, and a missing listener must not break the caller.
      if (typeof query.addEventListener === 'function') {
        query.addEventListener('change', onChange)
        onScopeDispose(() => query.removeEventListener('change', onChange))
      } else if (typeof query.addListener === 'function') {
        query.addListener(onChange)
        onScopeDispose(() => query.removeListener?.(onChange))
      }
    } catch {
      /* leave the initial read in place */
    }
  }

  return { prefersReducedMotion }
}
