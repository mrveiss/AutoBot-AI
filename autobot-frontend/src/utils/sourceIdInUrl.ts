// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * The one definition of "this URL names a code source" (#20513).
 *
 * The codebase-analytics routes require a `source_id` query parameter and answer 422
 * without it, and `withSourceId` adds nothing when no source is selected. Callers ask
 * here whether a URL carries one instead of each keeping a private regex.
 */

/** A non-empty `source_id` query parameter anywhere in a URL; group 1 is its raw value. */
const SOURCE_ID_IN_URL = /[?&]source_id=([^&#]+)/

/** The `source_id` a URL carries, decoded, or null when it carries none. */
export function sourceIdInUrl(url: string): string | null {
  const match = SOURCE_ID_IN_URL.exec(url)
  return match ? decodeURIComponent(match[1]) : null
}

/** True when the URL carries a non-empty `source_id`. */
export function hasSourceIdInUrl(url: string): boolean {
  return sourceIdInUrl(url) !== null
}
