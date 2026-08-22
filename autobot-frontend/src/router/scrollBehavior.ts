// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The router's scroll policy, as a pure function.
 *
 * Extracted from `router/index.ts` for the same reason `redirectTarget.ts`
 * was: the policy is small, decides something worth pinning, and is
 * untestable while it is an inline method on the router options object —
 * reaching it there means importing the entire route table.
 *
 * #14770: it also removes a genuine readability trap. The router option is
 * itself named `scrollBehavior`, so an inline call to the imported
 * `scrollBehavior()` resolved to the module import rather than to the method
 * — correct, because object method shorthand creates no binding for its own
 * name, but not something a reader should have to work out.
 */

import type { RouteLocationNormalized } from 'vue-router'
import { isReducedMotion } from '@/composables/useReducedMotion'

/** What `vue-router` accepts back from a `scrollBehavior` handler. */
export type ScrollTarget =
  | { left: number; top: number }
  | { el: string; behavior: ScrollBehavior }
  | { top: number; behavior: ScrollBehavior }

/**
 * Where to scroll on a navigation, and whether to glide there.
 *
 * A restored position from the browser's own history is returned untouched:
 * it is the browser reinstating what the user already had, not motion the app
 * is initiating, and it carries no behaviour of its own to soften.
 *
 * Everything else is app-initiated motion, which the stylesheet's global
 * reduced-motion rule cannot reach — `scroll-behavior: auto !important` does
 * not override a behaviour passed programmatically — so the preference is
 * consulted here instead.
 */
export function routeScrollBehavior(
  to: Pick<RouteLocationNormalized, 'hash'>,
  savedPosition: { left: number; top: number } | null,
): ScrollTarget {
  if (savedPosition) return savedPosition

  const behavior: ScrollBehavior = isReducedMotion() ? 'auto' : 'smooth'
  if (to.hash) return { el: to.hash, behavior }
  return { top: 0, behavior }
}
