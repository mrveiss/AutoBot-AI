// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * The URL the Browser tool will submit, or `null` when there is none (#22142).
 *
 * `BrowserTool` defaulted its address bar to `'/'`, which the backend URL guard refuses (it admits only
 * `http` and `https`), so Start answered 403 on every click. A submitted address must parse as an
 * absolute http(s) URL with a host; anything else is caught here, where the operator can be told in
 * their own language, instead of after a round trip. The guard stays the authority: this narrows what
 * is sent and widens nothing.
 */
const BROWSE_SCHEMES: ReadonlySet<string> = new Set(['http:', 'https:'])

export function parseBrowseUrl(raw: string): string | null {
  const text = raw.trim()
  if (text === '') return null
  try {
    const parsed = new URL(text)
    return BROWSE_SCHEMES.has(parsed.protocol) && parsed.hostname !== '' ? parsed.toString() : null
  } catch {
    return null
  }
}
