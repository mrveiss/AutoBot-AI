// AutoBot - AI-Powered Automation Platform
// Copyright (c) 2025 mrveiss
// Author: mrveiss
/**
 * navItems coverage test (#6499)
 *
 * Catches the recurring bug where a new top-level `requiresAuth: true` route
 * is added to `router/index.ts` but the developer forgets to add a matching
 * entry to `App.vue`'s `navItems`, leaving the new view unreachable from the
 * main nav.
 *
 * Pattern recurred twice in past sessions:
 *   - Remote Desktop (#4977 / SlmNoVnc) — added to router, forgotten in nav
 *   - Agent Activity (#5071 / #6451) — same mistake
 *
 * Rule enforced:
 *   For every top-level route with `meta.requiresAuth === true`, there must
 *   be a matching `to:` entry in `navItems` UNLESS the route is in the
 *   explicit `INTENTIONALLY_HIDDEN` allowlist below.
 *
 * Sub-routes (children) are intentionally excluded — only the parent appears
 * in main nav. Redirects and dynamic-param routes (`:sessionId`, `:pathMatch`)
 * are also excluded.
 */

import { describe, it, expect } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'
import { routes } from '@/router'
import { navItems, profileMenuItems, filterByFeatureFlag } from '@/config/navItems'

/**
 * Routes that are intentionally NOT in main nav.
 *
 * Each entry MUST include a reason. If you add a new top-level `requiresAuth`
 * route that should not appear in nav, add it here with justification.
 *
 * Prefer `hideInNav: true` on the route's `meta` instead of allowlisting —
 * use this allowlist only for routes that have a different exposure path
 * (footer link, accessed from another view, etc.) without an explicit flag.
 */
const INTENTIONALLY_HIDDEN: Record<string, string> = {
  '/about': 'Reachable via footer "About" link, not main nav',
  '/agents': 'Parent shell — redirects to /agents/registry; nav uses the deep-link entry (#6634)',
  '/agents/activity': 'Reached as a tab inside /agents shell (#6634); standalone URL kept for bookmarks',
  '/agents/heartbeat': 'Reached as a tab inside /agents shell (#6634); standalone URL kept for bookmarks',
  '/admin/users': 'Admin-only — surfaced via separate admin entrypoint',
  '/slm/tools/novnc': "Accessed via Chat tab's noVNC sub-tab (#6414/#6415); standalone URL kept for bookmarks",
}

/** True if route is hidden from nav by an explicit meta flag. */
function isHiddenByMeta(route: RouteRecordRaw): boolean {
  return route.meta?.hideInNav === true
}

/** True if route requires auth (top-level only). */
function requiresAuth(route: RouteRecordRaw): boolean {
  return route.meta?.requiresAuth === true
}

/** True if route is a redirect (no real component) or dynamic catch-all. */
function isRedirectOrCatchAll(route: RouteRecordRaw): boolean {
  if (route.redirect !== undefined) return true
  if (typeof route.path !== 'string') return false
  // Dynamic param routes like ':sessionId' or ':pathMatch(.*)*' are not navigation targets
  return route.path.includes(':') || route.path.includes('*')
}

/** Collect top-level routes (children are sub-routes, not main nav targets). */
function topLevelRoutes(): RouteRecordRaw[] {
  return routes.filter((r) => !isRedirectOrCatchAll(r))
}

/** Collect all absolute route paths recursively (including children). */
function allRoutePaths(
  routeList: RouteRecordRaw[] = routes,
  parentPath = '',
): Set<string> {
  const paths = new Set<string>()
  for (const route of routeList) {
    if (typeof route.path !== 'string') continue
    const fullPath = route.path.startsWith('/')
      ? route.path
      : (parentPath ? `${parentPath}/${route.path}` : `/${route.path}`).replace(/\/+/g, '/')
    if (!route.path.includes(':') && !route.path.includes('*') && route.redirect === undefined) {
      paths.add(fullPath)
    }
    const children = (route as RouteRecordRaw & { children?: RouteRecordRaw[] }).children
    if (children) {
      for (const p of allRoutePaths(children, fullPath)) paths.add(p)
    }
  }
  return paths
}

describe('navItems coverage (#6499)', () => {
  it('every top-level requiresAuth route has a navItems entry or is allowlisted', () => {
    const navPaths = new Set(navItems.map((n) => n.to))
    const missing: string[] = []

    for (const route of topLevelRoutes()) {
      if (!requiresAuth(route)) continue
      if (isHiddenByMeta(route)) continue
      if (route.path in INTENTIONALLY_HIDDEN) continue
      if (navPaths.has(route.path)) continue
      missing.push(route.path)
    }

    if (missing.length > 0) {
      throw new Error(
        `The following top-level requiresAuth routes have no navItems entry and are not in INTENTIONALLY_HIDDEN:\n` +
          missing.map((p) => `  - ${p}`).join('\n') +
          `\n\nFix: Either add an entry to src/config/navItems.ts, or set ` +
          `meta.hideInNav: true on the route, or add the route to INTENTIONALLY_HIDDEN ` +
          `in this test with a justification (sub-tab, footer link, admin entrypoint, etc.).`,
      )
    }

    expect(missing).toEqual([])
  })

  it('every navItems entry corresponds to a real route', () => {
    const allPaths = allRoutePaths()
    const orphans = navItems.filter((n) => !allPaths.has(n.to)).map((n) => n.to)

    expect(orphans).toEqual([])
  })

  it('every allowlisted path corresponds to a real route', () => {
    const allPaths = allRoutePaths()
    const stale = Object.keys(INTENTIONALLY_HIDDEN).filter((p) => !allPaths.has(p))

    expect(stale).toEqual([])
  })

  it('canvas is hidden in profileMenuItems when VITE_FEATURE_CANVAS is unset', () => {
    const result = filterByFeatureFlag(profileMenuItems, {})
    expect(result.map((i) => i.to)).not.toContain('/canvas')
  })

  it('canvas is visible in profileMenuItems when VITE_FEATURE_CANVAS=true', () => {
    const result = filterByFeatureFlag(profileMenuItems, { VITE_FEATURE_CANVAS: 'true' })
    expect(result.map((i) => i.to)).toContain('/canvas')
  })

  it('canvas profileMenuItem has featureFlag set to "canvas"', () => {
    const canvasItem = profileMenuItems.find((i) => i.to === '/canvas')
    expect(canvasItem?.featureFlag).toBe('canvas')
  })

  it('allowlist size and route counts (regression sentinel)', () => {
    const allowlistSize = Object.keys(INTENTIONALLY_HIDDEN).length
    const checkedCount = topLevelRoutes().filter(
      (r) => requiresAuth(r) && !isHiddenByMeta(r),
    ).length

    // Sanity: must be checking a meaningful number of routes
    expect(checkedCount).toBeGreaterThan(5)
    // Allowlist should stay small — if it grows, prefer hideInNav meta flag
    expect(allowlistSize).toBeLessThan(15)
  })
})
