// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #15224 — /services and /orchestration/per-node were duplicate
 * service-control surfaces. Two capabilities existed only on the (now
 * removed) ServicesView.vue and had to be ported into
 * useOrchestrationManagement.ts before the per-node tab could take over:
 *
 *   * live service status pushed over the shared SLM WebSocket actually
 *     updating the in-memory `fleetServices` list (OrchestrationView.vue
 *     previously called `initializeWebSocket()` but the status-update
 *     handler it passed only logged — the reactive list was never touched,
 *     so "live" status only ever changed on the next poll/manual refresh);
 *   * a single progress-tracked call to the existing
 *     `POST /nodes/:id/services/restart-all` endpoint, replacing
 *     OrchestrationView's client-side serial loop over individual restarts.
 *
 * These tests pin both directly against the composable, independent of the
 * (very large) OrchestrationView.vue template.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

vi.mock('@/stores/fleet', () => ({
  useFleetStore: () => ({
    nodes: [],
    setServiceStatus: vi.fn(),
    updateServiceStatus: vi.fn(),
  }),
}))

const connectMock = vi.fn()
const subscribeAllMock = vi.fn()
let registeredStatusHandler:
  | ((nodeId: string, data: { service_name: string; status: string }) => void)
  | null = null
const onServiceStatusMock = vi.fn(
  (handler: (nodeId: string, data: { service_name: string; status: string }) => void) => {
    registeredStatusHandler = handler
  }
)

vi.mock('@/composables/useSlmWebSocket', () => ({
  useSlmWebSocket: () => ({
    connect: connectMock,
    subscribeAll: subscribeAllMock,
    onServiceStatus: onServiceStatusMock,
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

/** Two nodes carrying one service each, one running and one stopped. */
const FLEET_SERVICES_PAYLOAD = {
  services: [
    {
      service_name: 'autobot-backend',
      category: 'autobot',
      nodes: [
        { node_id: 'node-a', hostname: 'a', status: 'running', ip_address: null, port: null },
        { node_id: 'node-b', hostname: 'b', status: 'stopped', ip_address: null, port: null },
      ],
      running_count: 1,
      stopped_count: 1,
      failed_count: 0,
      total_nodes: 2,
    },
  ],
  total_services: 1,
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  registeredStatusHandler = null
  fetchMock = vi.fn().mockResolvedValue(jsonResponse(FLEET_SERVICES_PAYLOAD))
  vi.stubGlobal('fetch', fetchMock)
})

describe('applyServiceStatusUpdate — live status actually reaches the reactive list (#15224)', () => {
  it('flips the node status and recomputes the running/stopped/failed counts', async () => {
    const o = useOrchestrationManagement()
    await o.fetchFleetServices()

    o.applyServiceStatusUpdate('node-b', { service_name: 'autobot-backend', status: 'running' })

    const svc = o.fleetServices.find((s) => s.service_name === 'autobot-backend')
    expect(svc?.nodes.find((n) => n.node_id === 'node-b')?.status).toBe('running')
    expect(svc?.running_count).toBe(2)
    expect(svc?.stopped_count).toBe(0)
  })

  it('is a no-op for a service or node not currently tracked', async () => {
    const o = useOrchestrationManagement()
    await o.fetchFleetServices()

    expect(() =>
      o.applyServiceStatusUpdate('node-z', { service_name: 'unknown-service', status: 'failed' })
    ).not.toThrow()

    const svc = o.fleetServices.find((s) => s.service_name === 'autobot-backend')
    expect(svc?.running_count).toBe(1)
    expect(svc?.stopped_count).toBe(1)
  })
})

describe('initializeWebSocket — wires the shared socket to applyServiceStatusUpdate (#15224)', () => {
  it('connects, subscribes, and registers a handler that updates state before the caller callback runs', async () => {
    const o = useOrchestrationManagement()
    await o.fetchFleetServices()

    const externalCallback = vi.fn()
    o.initializeWebSocket(externalCallback)

    expect(connectMock).toHaveBeenCalled()
    expect(subscribeAllMock).toHaveBeenCalled()
    expect(registeredStatusHandler).toBeTypeOf('function')

    registeredStatusHandler!('node-b', { service_name: 'autobot-backend', status: 'failed' })

    const svc = o.fleetServices.find((s) => s.service_name === 'autobot-backend')
    expect(svc?.nodes.find((n) => n.node_id === 'node-b')?.status).toBe('failed')
    expect(svc?.failed_count).toBe(1)
    expect(externalCallback).toHaveBeenCalledWith('node-b', {
      service_name: 'autobot-backend',
      status: 'failed',
    })
  })

  it('still registers a handler (that keeps applying updates) with no caller callback at all', () => {
    const o = useOrchestrationManagement()

    expect(() => o.initializeWebSocket()).not.toThrow()
    expect(registeredStatusHandler).toBeTypeOf('function')
  })
})

describe('restartAllNodeServices — single progress-tracked call, not a client-side loop (#15224)', () => {
  it('POSTs the existing per-node restart-all endpoint with the category filter and returns totals', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        node_id: 'node-a',
        message: 'Restarted 3 services',
        success: true,
        total_services: 3,
        successful_restarts: 3,
        failed_restarts: 0,
        slm_agent_restarted: true,
      })
    )

    const o = useOrchestrationManagement()
    const result = await o.restartAllNodeServices('node-a', { category: 'autobot' })

    const [url, init] = fetchMock.mock.calls[fetchMock.mock.calls.length - 1] as [
      string,
      RequestInit,
    ]
    expect(String(url)).toBe('/api/nodes/node-a/services/restart-all')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ category: 'autobot' })

    // The response carries `{ total, completed }`-shaped progress — what
    // ServicesView.vue's serial loop never had a single source for.
    expect(result?.total_services).toBe(3)
    expect(result?.successful_restarts).toBe(3)
    expect(result?.success).toBe(true)
  })

  it('surfaces the backend error detail on a failed restart-all', async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: 'node unreachable' }, 502))

    const o = useOrchestrationManagement()
    const result = await o.restartAllNodeServices('node-a')

    expect(result).toBeNull()
    expect(o.error).toBe('node unreachable')
  })
})
