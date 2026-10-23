// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * Admin-gated "clear stuck tasks" helpers for pattern analysis (#18718).
 *
 * The clear-stuck route requires admin; the analysis flow calls it
 * automatically as recovery, so a non-admin 403 must not break the flow.
 */
import { fetchWithAuth } from '@/utils/fetchWithAuth'
import { createLogger } from '@/utils/debugUtils'

const logger = createLogger('usePatternClearStuck')

/** What a refused (non-admin) clear reports, distinct from "another analysis is running". */
export const CLEAR_STUCK_FORBIDDEN_MESSAGE = 'Clearing stuck tasks requires admin'

/** True for the `HTTP 403: ...` error ApiClient throws on a refused request. */
export function isClearStuckForbidden(e: unknown): boolean {
  const forbidden = e instanceof Error && e.message.startsWith('HTTP 403')
  if (forbidden) logger.debug('clear-stuck refused (403, not admin); continuing without it')
  return forbidden
}

/** POST force clear-stuck; returns null (and logs at debug) when a non-admin gets 403. */
export async function forceClearStuck(url: string, signal?: AbortSignal): Promise<Response | null> {
  // fetchWithAuth retained: AbortController signal + response.status inspection — exempt (#6256)
  const resp = await fetchWithAuth(url, { method: 'POST', signal })
  if (resp.status !== 403) return resp
  logger.debug('clear-stuck refused (403, not admin); continuing without it')
  return null
}
