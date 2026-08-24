// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * Redact credential-shaped query parameter values before a URL is logged (#14989).
 *
 * WebSocket URLs built by buildAuthenticatedWsUrl (#6700) and its callers carry a
 * JWT in `?token=...` -- the only credential a browser can present on a WS
 * handshake. Composables that connect those URLs (useWebSocket.ts,
 * TerminalService.ts) log the full URL on connect/error for debugging, which
 * used to be harmless because the URL carried no secret. It no longer is.
 *
 * Redacts the VALUE only -- the parameter name stays visible (`?token=REDACTED`)
 * so the log line is still useful for diagnosing connection issues.
 *
 * Never throws: the composables call this from exactly the branch where the
 * input may not be a valid URL (e.g. an empty string), so a parse failure
 * falls back to a regex substitution on the raw string rather than raising.
 */

const SENSITIVE_QUERY_PARAMS = new Set([
  'token',
  'access_token',
  'id_token',
  'refresh_token',
  'api_key',
  'apikey',
  'secret',
  'password',
  'auth',
  'authorization',
])

const SENSITIVE_QUERY_PATTERN = new RegExp(
  `([?&](?:${[...SENSITIVE_QUERY_PARAMS].join('|')})=)[^&]*`,
  'gi',
)

export function redactUrlForLogging(rawUrl: string): string {
  try {
    const parsed = new URL(rawUrl)
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (SENSITIVE_QUERY_PARAMS.has(key.toLowerCase())) {
        parsed.searchParams.set(key, 'REDACTED')
      }
    }
    return parsed.toString()
  } catch {
    // Not a parseable absolute URL (this is exactly the "Invalid URL" case
    // callers hit) -- fall back to a string substitution that cannot throw.
    return rawUrl.replace(SENSITIVE_QUERY_PATTERN, '$1REDACTED')
  }
}
