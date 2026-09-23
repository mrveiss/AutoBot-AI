// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #15224 — a failed per-service action must reach the operator.
 *
 * `POST /orchestration/services/:name/{start,stop,restart}` answers HTTP 200
 * with `success: false` when the action fails — `api/orchestration.py` returns
 * `success=success` rather than an error status. The deleted ServicesView.vue
 * set `errorMessage` on exactly that branch. When the per-node tab took over,
 * the three per-service actions set `error` only from `catch`, which a 200
 * never enters, so the operator clicked the button, the action failed, and
 * nothing appeared anywhere in the UI.
 *
 * `restartAllNodeServices` was given this branch during the #15224 review and
 * is already pinned in `useOrchestrationManagement.statusUpdate.test.ts`
 * ("sets orchestration.error on an HTTP 200 partial failure"). Its three
 * siblings were missed. This file covers those, so the set is complete rather
 * than one-in-four.
 *
 * Asserted on `error` rather than on a logger call: the red banner
 * (`OrchestrationView.vue`, `v-if="orchestration.error"`) is what an operator
 * actually sees, and a test satisfied by a log line would pass on the broken
 * version. The composable returns `reactive({...})`, so refs arrive unwrapped.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    nodes: [],
    setServiceStatus: vi.fn(),
    updateServiceStatus: vi.fn(),
  }),
}))

vi.mock('@/composables/useSlmWebSocket', () => ({
  useSlmWebSocket: () => ({
    connect: vi.fn(),
    subscribeAll: vi.fn(),
    onServiceStatus: vi.fn(),
    connected: { value: false },
  }),
}))

import { useOrchestrationManagement } from './useOrchestrationManagement'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

/** The three actions the restart-all fix skipped over. */
const ACTIONS: ReadonlyArray<{
  label: string
  invoke: (o: ReturnType<typeof useOrchestrationManagement>) => Promise<unknown>
}> = [
  { label: 'startService', invoke: (o) => o.startService('autobot-backend', { node_id: 'node-a' }) },
  { label: 'stopService', invoke: (o) => o.stopService('autobot-backend', { node_id: 'node-a' }) },
  { label: 'restartService', invoke: (o) => o.restartService('autobot-backend', { node_id: 'node-a' }) },
]

describe('a 200 carrying success:false is surfaced, not swallowed (#15224)', () => {
  it.each(ACTIONS)('$label sets error from the failure message', async ({ invoke }) => {
    fetchMock.mockResolvedValue(
      jsonResponse({ success: false, message: 'systemd refused: unit is masked' })
    )

    const o = useOrchestrationManagement()
    const result = await invoke(o)

    // The response is still returned — the caller needs it — but the failure
    // must ALSO be visible outside devtools.
    expect((result as { success: boolean } | null)?.success).toBe(false)
    expect(o.error).toBe('systemd refused: unit is masked')
  })

  it.each(ACTIONS)('$label still reports when the failure carries no message', async ({ label, invoke }) => {
    fetchMock.mockResolvedValue(jsonResponse({ success: false }))

    const o = useOrchestrationManagement()
    await invoke(o)

    expect(o.error, `${label} left the operator with no indication of failure`).toBeTruthy()
  })

  it.each(ACTIONS)('$label leaves error clear when the action succeeds', async ({ invoke }) => {
    fetchMock.mockResolvedValue(jsonResponse({ success: true, message: 'started' }))

    const o = useOrchestrationManagement()
    await invoke(o)

    expect(o.error).toBeNull()
  })

  it.each(ACTIONS)('$label still reports a transport failure', async ({ invoke }) => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'node unreachable' }, 502))

    const o = useOrchestrationManagement()
    const result = await invoke(o)

    expect(result).toBeNull()
    expect(o.error).toBe('node unreachable')
  })
})
