// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Authenticated WebSocket URL helper (#6700)
 *
 * The backend WebSocket endpoints (/api/ws/live, /api/ws/events, etc.) require
 * a JWT in the `?token=...` query parameter. Each WS service used to construct
 * this URL ad-hoc, and at least one (LiveEventService) silently omitted the
 * token entirely — flooding the backend with 403s on every page load (#6692).
 *
 * This helper centralizes the pattern so:
 *   - Token plumbing is identical across all WS services
 *   - Missing-token state is explicit (returns null) instead of silently
 *     producing an unauthenticated URL that the server will reject
 *   - Future endpoints don't have to rediscover the convention
 *
 * Returns null when no token is available — callers must handle this and
 * defer the connection until a token is present (e.g., post-login).
 */

import { useUserStore } from '@/stores/useUserStore'

function getWsAuthToken(): string | null {
  return useUserStore().authState.token || null
}

export function buildAuthenticatedWsUrl(baseUrl: string): string | null {
  const token = getWsAuthToken()
  if (!token) return null
  const separator = baseUrl.includes('?') ? '&' : '?'
  return `${baseUrl}${separator}token=${encodeURIComponent(token)}`
}

/**
 * #16457: token via the Sec-WebSocket-Protocol subprotocol instead of the URL
 * query string, so it never lands in server access logs or browser history.
 * Pass the result as the second argument to `new WebSocket(url, protocols)`.
 * Returns null when no token is available, matching `buildAuthenticatedWsUrl`
 * — callers must handle this the same way (defer the connection).
 */
export function buildAuthenticatedWsSubprotocols(): string[] | null {
  const token = getWsAuthToken()
  return token ? ['bearer', token] : null
}
