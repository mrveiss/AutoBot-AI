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
 * Never throws, for real: every call site is TS-typed `string`, but the
 * regex fallback below runs unconditionally (see below) rather than only on
 * a `new URL()` parse failure, so a non-string slipping through at runtime
 * (`null`/`undefined` via `any`, a non-TS caller) is coerced instead of
 * crashing a log line.
 *
 * Covers the query string AND the fragment. `URLSearchParams` only ever
 * looks at the query string -- `new URL('wss://h/ws?x=1#token=SECRET')`
 * leaves `#token=SECRET` completely untouched -- so the regex substitution
 * below always runs over the final string as a second pass, not only as the
 * fallback for a `new URL()` failure.
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

// `[?&#]` -- `?`/`&` bound a query param, `#` starts (or, repeated, could
// appear inside) a fragment; treating all three as valid prefixes is what
// makes the pass below cover `#token=...` as well as `?token=...`.
const SENSITIVE_QUERY_PATTERN = new RegExp(
  `([?&#](?:${Array.from(SENSITIVE_QUERY_PARAMS).join('|')})=)[^&]*`,
  'gi',
)

export function redactUrlForLogging(rawUrl: string): string {
  if (typeof rawUrl !== 'string') {
    // Not reachable through the compiled app (every call site is typed
    // `string`), but the doc comment above claims "never throws" -- make
    // that literally true rather than only true for well-typed callers.
    return String(rawUrl)
  }

  let candidate = rawUrl
  try {
    const parsed = new URL(rawUrl)
    for (const key of Array.from(parsed.searchParams.keys())) {
      if (SENSITIVE_QUERY_PARAMS.has(key.toLowerCase())) {
        parsed.searchParams.set(key, 'REDACTED')
      }
    }
    candidate = parsed.toString()
  } catch {
    // Not a parseable absolute URL (this is exactly the "Invalid URL" case
    // callers hit) -- the regex pass below is the only redaction this
    // input gets.
  }

  return candidate.replace(SENSITIVE_QUERY_PATTERN, '$1REDACTED')
}

/**
 * Redact a caught error's message before it is logged (#14989 follow-up).
 *
 * `new WebSocket(url)` throws a browser-native SyntaxError whose `.message`
 * embeds the full attempted URL verbatim when the scheme is wrong (Chrome:
 * "Failed to construct 'WebSocket': The URL's scheme must be either 'ws' or
 * 'wss'. '<url>' is not allowed.") -- so a catch block that logs the raw
 * error leaks the same token this file exists to keep out of the console,
 * through a path buildAuthenticatedWsUrl's callers never validate a scheme
 * for before constructing the socket.
 *
 * Preserves the error's type, name and stack -- only the message text is
 * rewritten -- so this does not "swallow the error or discard the stack"
 * for debugging. Non-Error values pass through unchanged: there is no
 * message field to redact.
 */
export function redactErrorForLogging(err: unknown): unknown {
  if (!(err instanceof Error)) {
    return err
  }
  const redacted = new Error(redactUrlForLogging(err.message))
  redacted.name = err.name
  redacted.stack = err.stack
  return redacted
}
