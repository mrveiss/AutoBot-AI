// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * @autobot/ui — reading the agent ledger's answers, once for both consoles (#18391).
 *
 * The Company OS ledger (user backend, `/coordination/ledger/*`) and the SLM
 * admin ledger (`/monitoring/agent-ledger/*`) share one set of response shapes
 * (`autobot_shared/coordination/ledger_schemas.py`). Each app keeps its own
 * transport — its API client, base URL and auth — and hands the `Response`
 * here, so "couldn't read the ledger" and "what the yield request came back
 * with" mean the same thing in both.
 *
 * A typed 503 (`{error: 'ledger_unavailable', source}`) is `unavailable`, never
 * an empty list: the screen must say the store could not be read.
 */

import { createLogger } from './logger'

const logger = createLogger('ledger')

/** loading -> ready (data, possibly empty) | unavailable (typed 503) | error (anything else). */
export type LedgerSectionStatus = 'loading' | 'ready' | 'unavailable' | 'error'

export interface LedgerSection<T> {
  state: LedgerSectionStatus
  rows: T[]
  /** For `unavailable`: which store the backend could not read. */
  source?: string
}

/** What asking a holder to release came back with. Asking never releases anything. */
export type LedgerAskOutcome =
  | { state: 'sent'; token: string }
  | { state: 'too-soon' }
  | { state: 'not-found' }
  | { state: 'unavailable' }
  | { state: 'error' }

export function loadingLedgerSection<T>(): LedgerSection<T> {
  return { state: 'loading', rows: [] }
}

async function jsonBody(response: Response): Promise<Record<string, unknown> | null> {
  return (await response.json().catch(() => null)) as Record<string, unknown> | null
}

function isUnavailable(response: Response, body: Record<string, unknown> | null): boolean {
  return response.status === 503 && body?.error === 'ledger_unavailable'
}

/** One ledger list answer -> its section; `field` is the list's key in the body. */
export async function ledgerSectionFrom<T>(response: Response, field: string): Promise<LedgerSection<T>> {
  const body = await jsonBody(response)
  if (isUnavailable(response, body)) {
    return { state: 'unavailable', rows: [], source: String(body?.source ?? '') }
  }
  if (!response.ok || !body || !Array.isArray(body[field])) {
    logger.warn(`ledger section ${field} answered ${response.status}`)
    return { state: 'error', rows: [] }
  }
  return { state: 'ready', rows: body[field] as T[] }
}

/** GET through the app's transport, mapping a thrown request to `error`. */
export async function readLedgerSection<T>(request: () => Promise<Response>, field: string): Promise<LedgerSection<T>> {
  try {
    return await ledgerSectionFrom<T>(await request(), field)
  } catch (err: unknown) {
    logger.warn(`ledger section ${field} failed:`, err)
    return { state: 'error', rows: [] }
  }
}

/** The yield-request answer: 200 {token} | 429 asked too recently | 404 no such claim | typed 503. */
export async function ledgerAskOutcomeFrom(response: Response): Promise<LedgerAskOutcome> {
  const body = await jsonBody(response)
  if (response.ok && typeof body?.token === 'string') return { state: 'sent', token: body.token }
  if (response.status === 429) return { state: 'too-soon' }
  if (response.status === 404) return { state: 'not-found' }
  if (isUnavailable(response, body)) return { state: 'unavailable' }
  logger.warn(`yield request answered ${response.status}`)
  return { state: 'error' }
}

/** POST through the app's transport, mapping a thrown request to `error`. */
export async function sendLedgerAsk(request: () => Promise<Response>): Promise<LedgerAskOutcome> {
  try {
    return await ledgerAskOutcomeFrom(await request())
  } catch (err: unknown) {
    logger.warn('yield request failed:', err)
    return { state: 'error' }
  }
}
