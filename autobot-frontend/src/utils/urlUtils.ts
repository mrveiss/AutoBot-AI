// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * Normalize a raw URL/search string into a fully-qualified URL.
 *
 * Rules (#5139):
 *   - Already has a scheme (`://`) → returned as-is
 *   - Starts with `localhost` → prefixed with `http://`
 *   - Contains a dot → prefixed with `https://`
 *   - Bare word → routed through DuckDuckGo search
 */
export function normalizeUrl(raw: string): string {
  const input = raw.trim()
  if (input.includes('://')) return input
  if (input.startsWith('localhost')) return `http://${input}`
  if (input.includes('.')) return `https://${input}`
  return `https://duckduckgo.com/?q=${encodeURIComponent(input)}`
}
