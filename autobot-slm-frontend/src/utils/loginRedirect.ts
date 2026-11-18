// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Base-aware SLM login location (#18892).
 *
 * The SLM SPA is served under `import.meta.env.BASE_URL` ('/slm/' when
 * co-located, '/' standalone) and its router uses `createWebHistory(BASE_URL)`.
 * A full page load to a bare '/login' bypasses that base and lands on the USER
 * frontend's login page, so every location the client builds by hand goes
 * through here. Importing the router instead would create a cycle
 * (router -> auth store -> ApiClient -> router).
 */

const LOGIN_ROUTE_PATH = 'login'

/** The app base with exactly one trailing slash ('/slm/' or '/'). */
export function appBase(): string {
  const base = import.meta.env.BASE_URL || '/'
  return base.endsWith('/') ? base : `${base}/`
}

/** Path of the SLM login page including the base ('/slm/login'). */
export function loginPath(): string {
  return `${appBase()}${LOGIN_ROUTE_PATH}`
}

/** True when `pathname` is the SLM login page. */
export function isLoginPathname(pathname: string): boolean {
  return pathname === loginPath() || pathname === `${loginPath()}/`
}

/** Current location as an app-relative route path (base stripped), for `?redirect=`. */
export function currentAppPath(loc: Pick<Location, 'pathname' | 'search' | 'hash'>): string {
  const base = appBase()
  const rest = loc.pathname.startsWith(base)
    ? `/${loc.pathname.slice(base.length)}`
    : loc.pathname
  return `${rest}${loc.search ?? ''}${loc.hash ?? ''}`
}

/** Full login URL carrying the current route as the `redirect` query. */
export function buildLoginUrl(loc: Pick<Location, 'pathname' | 'search' | 'hash'>): string {
  return `${loginPath()}?redirect=${encodeURIComponent(currentAppPath(loc))}`
}

/** True for a C0 control character (tab, CR, LF, ...) or DEL anywhere in `value`. */
function hasControlCharacter(value: string): boolean {
  return Array.from(value).some((ch) => {
    const code = ch.charCodeAt(0)
    return code < 0x20 || code === 0x7f
  })
}

/** True when an app-relative route path is the login route itself (a redirect loop). */
function isLoginRoute(path: string): boolean {
  const pathname = path.split(/[?#]/, 1)[0].replace(/\/+$/, '')
  return pathname.toLowerCase() === `/${LOGIN_ROUTE_PATH}` // vue-router matches case-insensitively
}

/**
 * Validate a `redirect` query value: only same-app absolute route paths are
 * followed (no scheme, no '//' protocol-relative host, no backslash, no control
 * character, and never the login route itself, which would loop).
 */
export function safeRedirectTarget(raw: unknown): string {
  if (typeof raw !== 'string') return '/'
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.includes('\\')) return '/'
  if (hasControlCharacter(raw) || isLoginRoute(raw)) return '/'
  return raw
}
