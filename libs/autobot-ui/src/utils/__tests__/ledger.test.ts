// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Agent-ledger answer reading (#18391): both consoles read the same response
// shapes through these, so "couldn't read the ledger" and every yield-request
// outcome must mean one thing.

import { describe, it, expect } from 'vitest'
import { ledgerAskOutcomeFrom, ledgerSectionFrom, readLedgerSection, sendLedgerAsk } from '../ledger'

function response(status: number, body: unknown): Response {
  return new Response(body === undefined ? 'not json' : JSON.stringify(body), { status })
}

const UNAVAILABLE = { error: 'ledger_unavailable', source: 'claims', detail: 'redis down' }

describe('ledgerSectionFrom', () => {
  it('reads the named list field as a ready section, empty included', async () => {
    expect(await ledgerSectionFrom(response(200, { claims: [{ scope: 'a' }], count: 1 }), 'claims')).toEqual({
      state: 'ready',
      rows: [{ scope: 'a' }],
    })
    expect(await ledgerSectionFrom(response(200, { claims: [], count: 0 }), 'claims')).toEqual({ state: 'ready', rows: [] })
  })

  it('reads a typed 503 as unavailable, naming the store', async () => {
    expect(await ledgerSectionFrom(response(503, UNAVAILABLE), 'claims')).toEqual({
      state: 'unavailable',
      rows: [],
      source: 'claims',
    })
  })

  it('reads an untyped 503, another status, a missing field or a non-JSON body as error', async () => {
    for (const r of [response(503, { detail: 'x' }), response(500, {}), response(200, { other: [] }), response(200, undefined)]) {
      expect((await ledgerSectionFrom(r, 'claims')).state).toBe('error')
    }
  })

  it('maps a thrown request to error', async () => {
    expect(await readLedgerSection(() => Promise.reject(new Error('offline')), 'claims')).toEqual({ state: 'error', rows: [] })
  })
})

describe('ledgerAskOutcomeFrom', () => {
  it.each([
    [response(200, { token: 't-1' }), { state: 'sent', token: 't-1' }],
    [response(429, { detail: 'too soon' }), { state: 'too-soon' }],
    [response(404, { detail: 'no claim' }), { state: 'not-found' }],
    [response(503, UNAVAILABLE), { state: 'unavailable' }],
    [response(503, { detail: 'untyped' }), { state: 'error' }],
    [response(200, {}), { state: 'error' }],
    [response(500, undefined), { state: 'error' }],
  ])('maps %#', async (r, outcome) => {
    expect(await ledgerAskOutcomeFrom(r)).toEqual(outcome)
  })

  it('maps a thrown request to error, never sent', async () => {
    expect(await sendLedgerAsk(() => Promise.reject(new Error('offline')))).toEqual({ state: 'error' })
  })
})
