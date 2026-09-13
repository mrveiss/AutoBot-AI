// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform

type LogFn = (...args: unknown[]) => void
const noop: LogFn = () => {}

/** Minimal scoped logger for plugin-internal use. No-op by default to comply with no-console rule. */
export function createLogger(_scope: string) {
  return {
    debug: noop,
    info: noop,
    warn: noop,
    error: noop,
  }
}

/**
 * Redact credential-shaped query parameter values before a URL is logged (#14989).
 *
 * Duplicated from autobot-frontend/src/utils/redactUrlForLogging.ts rather than
 * shared: @autobot/terminal is a standalone package (peerDependencies only --
 * vue/pinia/xterm) consumed by BOTH autobot-frontend and autobot-slm-frontend,
 * with no shared frontend utility package between them to hold one copy in.
 * Keep the two in sync -- same logic, same tests, same reasoning (#15002
 * tracks the duplication itself).
 *
 * createLogger() above is a no-op today, so this has no live exposure through
 * it yet -- but SshTerminal.vue's WebSocket URL now carries a JWT in
 * `?token=...` (#14991), and useWebSocket.ts logs the full URL on connect and
 * on an invalid-URL error. Redacting here means the logger cannot start
 * leaking the token the day createLogger() stops being a no-op.
 *
 * Redacts the VALUE only -- the parameter name stays visible (`?token=REDACTED`)
 * so the log line is still useful for diagnosing connection issues.
 *
 * Never throws, for real: every call site is TS-typed `string`, but the
 * regex fallback below runs unconditionally rather than only on a `new
 * URL()` parse failure, so a non-string slipping through at runtime is
 * coerced instead of crashing a log line.
 *
 * Covers the query string AND the fragment. `URLSearchParams` only ever
 * looks at the query string -- `new URL('wss://h/ws?x=1#token=SECRET')`
 * leaves `#token=SECRET` completely untouched -- so the regex substitution
 * below always runs over the final string as a second pass.
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
    // Not a parseable absolute URL -- the regex pass below is the only
    // redaction this input gets.
  }

  return candidate.replace(SENSITIVE_QUERY_PATTERN, '$1REDACTED')
}

/**
 * Redact a caught error's message before it is logged (#14989 follow-up).
 *
 * `new WebSocket(url)` throws a browser-native SyntaxError whose `.message`
 * embeds the full attempted URL verbatim when the scheme is wrong -- a catch
 * block that logs the raw error leaks the same token this file exists to
 * keep out of the console.
 *
 * Preserves the error's type, name and stack -- only the message text is
 * rewritten. Non-Error values pass through unchanged: there is no message
 * field to redact.
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
