// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #15640 — `useNodeServices.getLogs()` must REJECT on a failed fetch, never
 * resolve to `''`.
 *
 * The defect #15620 fixed was not a crash. `getLogs()` caught the failure and
 * returned an empty string, and its only caller renders a falsy result as
 * "No logs available" (`FleetToolsTab.vue`) — so a journal fetch cut short by
 * its own ceiling told the operator, in words, that the node had nothing to
 * say. Reverting the `throw err` to `return ''` restores that exactly, and
 * every other assertion in this repository still passes.
 *
 * The composable had no test file at all, which is why the rethrow was
 * asserted only by reading the diff. These pin the contract at the seam; the
 * user-visible half is pinned at the sink in
 * `components/fleet/FleetToolsTab.logsError.test.ts`.
 */

import { describe, it, expect, vi } from 'vitest'

const h = vi.hoisted(() => ({
  getServiceLogs: vi.fn(),
  getNodeServices: vi.fn(),
}))

vi.mock('@/composables/useSlmApi', () => ({
  // A plain arrow, not a `vi.fn`: this suite runs with `mockReset: true`, which
  // strips an implementation registered on a mock before the tests execute.
  useSlmApi: () => ({
    getServiceLogs: h.getServiceLogs,
    getNodeServices: h.getNodeServices,
  }),
}))

import { useNodeServices } from '@/composables/useNodeServices'

const NODE = 'node-alpha'
const SERVICE = 'slm-backend'
const GATEWAY_TIMEOUT_MESSAGE =
  "Journal fetch for 'slm-backend' did not complete within 30s. Any logs it had read are incomplete, not absent."

describe('useNodeServices.getLogs', () => {
  it('rethrows a failed fetch instead of resolving to an empty string', async () => {
    const failure = new Error(GATEWAY_TIMEOUT_MESSAGE)
    h.getServiceLogs.mockRejectedValue(failure)

    const { getLogs } = useNodeServices(NODE)

    // `rejects.toBe` rather than `toThrow`: the caller needs the original error
    // — the 504 detail it carries is the only thing that tells the operator
    // what to change — not a substitute the composable manufactured.
    await expect(getLogs(SERVICE)).rejects.toBe(failure)
  })

  it('never settles a failed fetch with the value an empty journal produces', async () => {
    h.getServiceLogs.mockRejectedValue(new Error(GATEWAY_TIMEOUT_MESSAGE))

    const { getLogs } = useNodeServices(NODE)
    const settled = await Promise.allSettled([getLogs(SERVICE)])

    expect(settled[0].status).toBe('rejected')
    // Stated as its own assertion because `return ''` is the exact regression:
    // it settles fulfilled with a falsy value, which every caller renders as
    // "this node logged nothing".
    expect(settled[0]).not.toMatchObject({ status: 'fulfilled', value: '' })
  })

  it('still records the failure on `error` for callers that show it inline', async () => {
    h.getServiceLogs.mockRejectedValue(new Error(GATEWAY_TIMEOUT_MESSAGE))

    const { getLogs, error } = useNodeServices(NODE)
    await expect(getLogs(SERVICE)).rejects.toThrow()

    expect(error.value).toBe(GATEWAY_TIMEOUT_MESSAGE)
  })

  it('resolves with empty content when the journal genuinely has none', async () => {
    h.getServiceLogs.mockResolvedValue({
      service_name: SERVICE,
      node_id: NODE,
      logs: '',
      lines_returned: 1,
    })

    const { getLogs, error } = useNodeServices(NODE)

    // The other side of the same distinction: an empty journal is a success,
    // and asserting only the rejection above would let a regression answer
    // every fetch with a rejection and still pass.
    await expect(getLogs(SERVICE)).resolves.toBe('')
    expect(error.value).toBeNull()
  })

  it('passes the requested line count through to the API', async () => {
    h.getServiceLogs.mockResolvedValue({
      service_name: SERVICE,
      node_id: NODE,
      logs: 'one line\n',
      lines_returned: 1,
    })

    const { getLogs } = useNodeServices(NODE)
    await getLogs(SERVICE, 25)

    expect(h.getServiceLogs).toHaveBeenCalledWith(NODE, SERVICE, { lines: 25 })
  })
})
