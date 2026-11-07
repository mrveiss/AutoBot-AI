// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
/**
 * #18391 AC3 at the data layer: an unreadable ledger store (typed 503
 * `LedgerUnavailable`) is `unavailable`, never an empty `ready` -- the screen
 * says "couldn't read the ledger", not "no claims". An empty list is `ready`
 * with no rows; anything else is `error`.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { rawRequest } = vi.hoisted(() => ({ rawRequest: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { rawRequest } }))
vi.mock('@/config/ssot-config', () => ({ getApiBase: () => '/api' }))

import { askHolderToRelease, groupByScope, useAgentLedger, type ClaimRow, type WaiterRow } from '../useAgentLedger'

const json = (status: number, body: unknown) => ({ status, ok: status < 400, json: async () => body })

const claim = (scope: string, agent: string): ClaimRow => ({
  scope, kind: scope.split(':')[0], agent_id: agent, task_id: `t-${agent}`, mode: 'exclusive', intent: 'build',
  acquired_at: '2026-10-16T10:00:00Z', expires_at: '2026-10-16T11:00:00Z', renewals: 0, company_id: 'c1',
})
const waiter = (scope: string, agent: string, position: number): WaiterRow => ({
  scope, position, agent_id: agent, task_id: `t-${agent}`, mode: 'exclusive', intent: 'wait', priority: 0,
  joined_at: '2026-10-16T10:05:00Z', expires_at: '2026-10-16T11:05:00Z', company_id: 'c1',
})

/** Route each ledger path to a canned response; anything unlisted answers an empty list. */
function serve(routes: Record<string, ReturnType<typeof json>>) {
  const empty: Record<string, string> = {
    presence: 'agents', claims: 'claims', waitlists: 'waiters', conflicts: 'conflicts',
    activity: 'activity', 'peer-messages': 'recipients', 'idle-subscribers': 'subscribers',
  }
  rawRequest.mockImplementation(async (url: string) => {
    const name = url.split('/coordination/ledger/')[1]
    return routes[name] ?? json(200, { [empty[name]]: [], count: 0 })
  })
}

describe('useAgentLedger (#18391)', () => {
  // Braces matter: a function returned from beforeEach is run as its teardown,
  // and mockReset() returns the mock -- vitest would call rawRequest() once more.
  beforeEach(() => {
    rawRequest.mockReset()
  })

  it('reads the company ledger paths through ApiClient (org scoping is the backend\'s)', async () => {
    serve({})
    await useAgentLedger().refresh()
    const paths = rawRequest.mock.calls.map((c) => c[0]).sort()
    expect(paths).toEqual([
      '/api/coordination/ledger/activity', '/api/coordination/ledger/claims', '/api/coordination/ledger/conflicts',
      '/api/coordination/ledger/idle-subscribers', '/api/coordination/ledger/peer-messages',
      '/api/coordination/ledger/presence', '/api/coordination/ledger/waitlists',
    ])
  })

  it('an empty ledger is ready with no rows', async () => {
    serve({})
    const ledger = useAgentLedger()
    await ledger.refresh()
    expect(ledger.claims.value).toEqual({ state: 'ready', rows: [] })
  })

  it('a typed 503 is unavailable, naming the store -- not an empty list', async () => {
    serve({ claims: json(503, { error: 'ledger_unavailable', source: 'claims', detail: 'redis down' }) })
    const ledger = useAgentLedger()
    await ledger.refresh()
    expect(ledger.claims.value).toEqual({ state: 'unavailable', rows: [], source: 'claims' })
    expect(ledger.waitlists.value.state).toBe('ready')
  })

  it('an untyped failure is error, distinct from unavailable', async () => {
    serve({ claims: json(500, { detail: 'boom' }), waitlists: json(503, { detail: 'proxy' }) })
    const ledger = useAgentLedger()
    await ledger.refresh()
    expect(ledger.claims.value.state).toBe('error')
    expect(ledger.waitlists.value.state).toBe('error')
  })

  it('contention is only as readable as the worse of claims and waitlists', async () => {
    serve({ waitlists: json(503, { error: 'ledger_unavailable', source: 'waitlists', detail: 'x' }) })
    const ledger = useAgentLedger()
    await ledger.refresh()
    expect(ledger.contention.value).toEqual({ state: 'unavailable', rows: [], source: 'waitlists' })
  })
})

describe('groupByScope', () => {
  it('puts holders and queue-ordered waiters under their scope, most contended first', () => {
    const rows = groupByScope(
      [claim('provider:openai', 'a1'), claim('cpu:build', 'a2')],
      [waiter('provider:openai', 'a4', 2), waiter('provider:openai', 'a3', 1), waiter('queue:ingest', 'a5', 1)],
    )
    expect(rows.map((r) => r.scope)).toEqual(['provider:openai', 'queue:ingest', 'cpu:build'])
    expect(rows[0].waiters.map((w) => w.agent_id)).toEqual(['a3', 'a4'])
    expect(rows[1]).toMatchObject({ scope: 'queue:ingest', kind: 'queue', holders: [] })
  })
})

describe('askHolderToRelease (#18391 AC4, route #18599)', () => {
  beforeEach(() => {
    rawRequest.mockReset()
  })

  it.each([
    [200, { token: 'tok-1' }, { state: 'sent', token: 'tok-1' }],
    [429, {}, { state: 'too-soon' }],
    [404, {}, { state: 'not-found' }],
    [503, { error: 'ledger_unavailable', source: 'claims', detail: 'x' }, { state: 'unavailable' }],
    [503, { detail: 'proxy' }, { state: 'error' }],
    [200, {}, { state: 'error' }],
  ])('%s %j -> %j', async (status, body, outcome) => {
    rawRequest.mockResolvedValueOnce(json(status, body))
    expect(await askHolderToRelease('provider:openai', 't1', 'need it')).toEqual(outcome)
    expect(rawRequest).toHaveBeenCalledWith('/api/coordination/ledger/claims/yield-request', {
      method: 'POST', body: { scope: 'provider:openai', holder_task_id: 't1', reason: 'need it' },
    })
  })

  it('a network failure is error, not sent', async () => {
    rawRequest.mockRejectedValueOnce(new Error('offline'))
    expect(await askHolderToRelease('provider:openai', 't1')).toEqual({ state: 'error' })
  })
})
