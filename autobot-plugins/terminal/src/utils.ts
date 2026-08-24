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
 * Keep the two in sync -- same logic, same tests, same reasoning.
 *
 * createLogger() above is a no-op today, so this has no live exposure through
 * it yet -- but SshTerminal.vue's WebSocket URL now carries a JWT in
 * `?token=...` (#14991), and useWebSocket.ts logs the full URL on connect and
 * on an invalid-URL error. Redacting here means the logger cannot start
 * leaking the token the day createLogger() stops being a no-op.
 *
 * Redacts the VALUE only -- the parameter name stays visible (`?token=REDACTED`).
 * Never throws: called from exactly the branch where the input may not be a
 * valid URL (e.g. an empty string), so a parse failure falls back to a regex
 * substitution rather than raising.
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
    return rawUrl.replace(SENSITIVE_QUERY_PATTERN, '$1REDACTED')
  }
}
