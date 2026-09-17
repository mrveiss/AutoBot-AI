// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Every company-scoped route reaches the Company OS sidebar (#16901).
 *
 * `nav-items-coverage.test.ts` enforces this contract for TOP-LEVEL routes: a
 * `requiresAuth` route must have a `navItems` entry unless it declares
 * `hideInNav: true`. It iterates `topLevelRoutes()`, so it stops at the company
 * boundary — and the workflow builder, a child of `/llc/companies/:companyId`,
 * sat outside any sidebar for as long as it has existed. It was reachable only
 * by typing the URL, and nothing in the suite had an opinion about that.
 *
 * `LlcSidebar.vue` builds its menu from a hardcoded list, so a route added to
 * the company shell appears in the app and not in the menu. That is a silent
 * failure: the feature works, the page renders, and only a user who already
 * knows the URL can reach it.
 *
 * The check reads the sidebar's SOURCE rather than mounting it, because the
 * links are template literals over a `companyId` the component gets from the
 * route. What matters here is which segments the list names, not what they
 * interpolate to.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import type { RouteRecordRaw } from 'vue-router'
import { routes } from '@/router'

const COMPANY_PATH = '/llc/companies/:companyId'

/** Company-scoped routes that deliberately have no sidebar entry, and why. */
const INTENTIONALLY_ABSENT: Record<string, string> = {
  '': 'Index route — redirects to the dashboard, which has its own entry',
}

const sidebarSource = (): string =>
  readFileSync(
    // Resolved with `path`, not `new URL(relative, base)`. The two-argument URL
    // form throws `TypeError: Invalid URL` under this project's pinned
    // jsdom 30.0.1 + vitest 5.0.0 (the versions package-lock.json resolves and CI
    // installs), deterministically and in CI as well as locally. Building from
    // `import.meta.url` alone is safe because that value is always absolute; it is
    // only the relative-plus-base pair that breaks.
    resolve(dirname(fileURLToPath(import.meta.url)), '../components/llc/LlcSidebar.vue'),
    'utf-8',
  )

/** The path segments `LlcSidebar` links to, e.g. `dashboard`, `automation/overview`. */
export function sidebarSegments(source: string): string[] {
  return [...source.matchAll(/\/llc\/companies\/\$\{id\}\/([a-z0-9/-]+)/g)].map((m) => m[1])
}

function companyChildren(): RouteRecordRaw[] {
  const company = routes.find((r) => r.path === COMPANY_PATH)
  if (!company) throw new Error(`the company route ${COMPANY_PATH} moved — re-point this guard, do not delete it`)
  return company.children ?? []
}

/** Company routes with no sidebar link and no declared reason to be absent. */
export function unreachableFromSidebar(children: RouteRecordRaw[], segments: string[]): string[] {
  const linked = new Set(segments)
  const missing: string[] = []
  for (const child of children) {
    const path = child.path
    if (path in INTENTIONALLY_ABSENT) continue
    if (child.meta?.hideInNav === true) continue
    // A link may point at a deeper default (`automation/overview` covers `automation`).
    const reached = linked.has(path) || [...linked].some((s) => s.startsWith(`${path}/`))
    if (!reached) missing.push(path)
  }
  return missing
}

describe('Company OS sidebar coverage (#16901)', () => {
  it('every company-scoped route is reachable from the sidebar', () => {
    const missing = unreachableFromSidebar(companyChildren(), sidebarSegments(sidebarSource()))
    expect(
      missing,
      `These company-scoped routes have no LlcSidebar entry and no declared reason. A route the ` +
        `menu never names is reachable only by typing its URL:\n  ${missing.join('\n  ')}\n` +
        `Add a link in LlcSidebar.vue, set meta.hideInNav, or record it in INTENTIONALLY_ABSENT.`,
    ).toEqual([])
  })

  // --- controls: an empty sweep must fail here, not pass above ---

  it('the sweep finds the company routes and the sidebar links', () => {
    const children = companyChildren()
    const segments = sidebarSegments(sidebarSource())
    expect(children.length).toBeGreaterThan(10)
    expect(segments.length).toBeGreaterThan(10)
    expect(segments).toContain('dashboard')
  })

  it('the workflow builder is linked — the route this guard was written for', () => {
    const segments = sidebarSegments(sidebarSource())
    expect(segments.some((s) => s.startsWith('automation'))).toBe(true)
  })

  it('removing a real sidebar entry is reported, naming the route', () => {
    // AC4's mutation, on the real route table: drop `dashboard` from the link
    // set and the guard must name it. Without this, every assertion above
    // passes just as happily against a checker that reports nothing.
    const segments = sidebarSegments(sidebarSource()).filter((s) => s !== 'dashboard')
    const missing = unreachableFromSidebar(companyChildren(), segments)
    expect(missing).toContain('dashboard')
  })

  it('a hideInNav route is not reported', () => {
    const hidden = [{ path: 'deliberately-hidden', meta: { hideInNav: true } }] as RouteRecordRaw[]
    expect(unreachableFromSidebar(hidden, [])).toEqual([])
  })
})
