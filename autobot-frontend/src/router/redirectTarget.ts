// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#13996: `?redirect=` is set by `llcCompanyParamGuard` and by
// `AutomationCompanyRedirectView` (which sends `/automation/...`, not
// `/llc/...`). One shared validator so every producer's destination survives
// and no producer can turn the query param into an open redirect.

/**
 * Route prefixes a `?redirect=` destination may point at. A destination is
 * accepted when it is the prefix itself or a path below it — never a bare
 * string match, so `/automation-evil` is rejected while `/automation/canvas`
 * is not.
 */
const ALLOWED_PREFIXES = ['/llc', '/automation'] as const

/**
 * Validate a `?redirect=` value as an in-app destination.
 *
 * @param raw the raw query value (`route.query.redirect`)
 * @returns the destination when it is safe to navigate to, else `null`
 */
export function safeRedirectTarget(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  // Absolute URLs (`https://host/…`) and anything with a scheme fail here.
  if (!raw.startsWith('/')) return null
  // `//host` and `/\host` are scheme-relative — a leading slash is not enough.
  if (raw.startsWith('//') || raw.startsWith('/\\')) return null
  // Browsers strip control characters from URLs, which can re-form `/<TAB>/host`
  // into a scheme-relative one. (Char codes, not a regex: a control-character
  // class is itself a lint error.)
  if (hasControlCharacter(raw)) return null

  const path = raw.split(/[?#]/)[0]

  // Traversal defeats the prefix check: `/automation/../../evil` passes it, and
  // although a path-absolute string can never change the origin (so this is not
  // an open redirect), `history.pushState` hands the raw string to the browser,
  // which DOES collapse the dot segments. The address bar then shows `/evil`
  // while the router state still holds the prefixed path — so an attacker-set
  // `?redirect=` could steer an authenticated user to any in-app route, not the
  // two this list names. Reject dot segments, including the percent-encoded
  // spelling, which normalises identically.
  const segments = path.split('/')
  if (segments.some((seg) => seg === '.' || seg === '..' || seg.toLowerCase() === '%2e%2e' || seg.toLowerCase() === '%2e')) {
    return null
  }

  const allowed = ALLOWED_PREFIXES.some((prefix) => path === prefix || path.startsWith(`${prefix}/`))
  return allowed ? raw : null
}

/** True when `value` contains a C0 control character or DEL. */
function hasControlCharacter(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i)
    if (code < 0x20 || code === 0x7f) return true
  }
  return false
}
