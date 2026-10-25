// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Benign browser notices (#19458, #10352).
 *
 * Browsers surface some self-correcting layout notices as window `error`
 * events even though they are not application errors (no stack, nothing
 * broke). Chromium has two wordings of the ResizeObserver one. This module is
 * the ONLY place that lists them; every error sink (window listeners, the Vue
 * error handler, ErrorBoundary, RUM) asks `isBenignBrowserNotice` instead of
 * keeping its own copy, so the copies cannot drift apart.
 */

const BENIGN_BROWSER_NOTICES: readonly string[] = [
  'ResizeObserver loop limit exceeded',
  'ResizeObserver loop completed with undelivered notifications',
]

function messageOf(value: unknown): string {
  if (typeof value === 'string') return value
  if (value && typeof value === 'object' && 'message' in value) {
    const message = (value as { message?: unknown }).message
    if (typeof message === 'string') return message
  }
  return ''
}

/** True when a message string, Error, ErrorEvent or rejection reason is a benign browser notice. */
export function isBenignBrowserNotice(...candidates: unknown[]): boolean {
  return candidates.some((candidate) => {
    const message = messageOf(candidate)
    return message !== '' && BENIGN_BROWSER_NOTICES.some((notice) => message.includes(notice))
  })
}
