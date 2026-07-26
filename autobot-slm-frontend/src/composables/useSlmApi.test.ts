// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 batch 5 — proves the core useSlmApi composable is migrated onto
 * the canonical `slmApiClient`.
 *
 * useSlmApi historically owned its own `axios.create()` instance (base URL from
 * getSlmApiBase(), a request interceptor injecting the SLM bearer token). It now
 * routes every call through `slmApiClient.rawRequest` via a thin axios-compatible
 * adapter. These tests assert the migration preserves the behaviour the ~26
 * consumers depend on:
 *
 *   * every verb routes through slmApiClient.rawRequest with the correct
 *     method + endpoint (+ serialised query) and body — so the client's auth
 *     token / base URL / 401 handling apply (those are covered by ApiClient.test.ts);
 *   * success returns the parsed JSON body (the historical `response.data`);
 *   * a non-2xx rejection carries the axios-shaped `err.response.status` /
 *     `err.response.data` consumers read (SetupWizardView, SecretsSettings);
 *   * a 401 surfaces `err.response.status === 401` (session handling is the
 *     client's central concern, exercised inside rawRequest);
 *   * upsertSecret's load-bearing 409 → PUT fallback still works end-to-end.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { jsonResponse, errorResponse } from './useSlmApi.testHelper'

const mockRaw = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  slmApiClient: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
  default: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
}))

import { useSlmApi } from './useSlmApi'

type RawCall = [string, { method: string; body?: unknown }]

describe('useSlmApi — migrated onto slmApiClient (#12420 Phase 2 batch 5)', () => {
  beforeEach(() => {
    mockRaw.mockReset()
  })

  describe('routing + response.data unwrap', () => {
    it('getNodes GETs /nodes and maps the backend nodes payload', async () => {
      mockRaw.mockResolvedValue(
        jsonResponse({
          nodes: [
            {
              id: 1,
              node_id: 'n1',
              hostname: 'h1',
              ip_address: '10.0.0.1',
              status: 'online',
              roles: [],
              cpu_percent: 1,
              memory_percent: 2,
              disk_percent: 3,
              last_heartbeat: null,
              agent_version: null,
              os_info: null,
              created_at: 'c',
              updated_at: 'u',
            },
          ],
          total: 1,
        })
      )

      const result = await useSlmApi().getNodes()

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes')
      expect(opts.method).toBe('GET')
      expect(result).toHaveLength(1)
      expect(result[0]!.node_id).toBe('n1')
      // health.status derived from status === 'online'
      expect(result[0]!.health?.status).toBe('healthy')
    })

    it('registerNode POSTs the node body to /nodes', async () => {
      mockRaw.mockResolvedValue(
        jsonResponse({
          id: 1,
          node_id: 'n2',
          hostname: 'h2',
          ip_address: '10.0.0.2',
          status: 'online',
          roles: [],
          cpu_percent: 0,
          memory_percent: 0,
          disk_percent: 0,
          last_heartbeat: null,
          agent_version: null,
          os_info: null,
          created_at: 'c',
          updated_at: 'u',
        })
      )

      const payload = { hostname: 'h2', ip_address: '10.0.0.2' } as never
      await useSlmApi().registerNode(payload)

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes')
      expect(opts.method).toBe('POST')
      expect(opts.body).toEqual({ hostname: 'h2', ip_address: '10.0.0.2' })
    })

    it('updateNode PATCHes /nodes/:id with the update body', async () => {
      mockRaw.mockResolvedValue(
        jsonResponse({
          id: 1,
          node_id: 'n1',
          hostname: 'h1',
          ip_address: '10.0.0.1',
          status: 'online',
          roles: [],
          cpu_percent: 0,
          memory_percent: 0,
          disk_percent: 0,
          last_heartbeat: null,
          agent_version: null,
          os_info: null,
          created_at: 'c',
          updated_at: 'u',
        })
      )

      await useSlmApi().updateNode('n1', { ssh_port: 2222 } as never)

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes/n1')
      expect(opts.method).toBe('PATCH')
      expect(opts.body).toEqual({ ssh_port: 2222 })
    })

    it('deleteNode DELETEs /nodes/:id (204 handled gracefully)', async () => {
      mockRaw.mockResolvedValue(jsonResponse({}, 204))

      await expect(useSlmApi().deleteNode('n1')).resolves.toBeUndefined()

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes/n1')
      expect(opts.method).toBe('DELETE')
    })

    it('getFleetMetrics returns the parsed body directly', async () => {
      const body = { nodes: [], totals: { cpu: 0 } }
      mockRaw.mockResolvedValue(jsonResponse(body))

      const result = await useSlmApi().getFleetMetrics()

      expect((mockRaw.mock.calls[0] as RawCall)[0]).toBe('/monitoring/metrics/fleet')
      expect(result).toEqual(body)
    })
  })

  describe('query-param serialisation', () => {
    it('getProvisionStatus serialises the axios params object onto the endpoint', async () => {
      mockRaw.mockResolvedValue(
        jsonResponse({ status: 'running', lines: [], total_lines: 0, error: null })
      )

      await useSlmApi().getProvisionStatus(7)

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/setup/provision-status?since_line=7')
      expect(opts.method).toBe('GET')
    })

    it('getAlerts serialises inline query params', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ alerts: [] }))

      await useSlmApi().getAlerts({ severity: 'critical', hours: 12 })

      const [url] = mockRaw.mock.calls[0] as RawCall
      expect(url).toContain('/monitoring/alerts?')
      expect(url).toContain('severity=critical')
      expect(url).toContain('hours=12')
    })
  })

  describe('error shape parity (axios-compatible err.response)', () => {
    it('surfaces err.response.status and err.response.data on a non-2xx', async () => {
      mockRaw.mockResolvedValue(errorResponse(400, { detail: 'bad node id' }))

      await expect(useSlmApi().getNode('nope')).rejects.toMatchObject({
        response: { status: 400, data: { detail: 'bad node id' } },
      })
    })

    it('surfaces err.response.status === 401 (client 401 handling runs in rawRequest)', async () => {
      mockRaw.mockResolvedValue(errorResponse(401, { detail: 'expired' }))

      await expect(useSlmApi().getNodes()).rejects.toMatchObject({
        response: { status: 401 },
      })
    })
  })

  describe('upsertSecret 409 → PUT fallback (load-bearing error-shape contract)', () => {
    it('POSTs first, then PUTs on a 409 conflict', async () => {
      mockRaw
        .mockResolvedValueOnce(errorResponse(409, { detail: 'exists' }))
        .mockResolvedValueOnce(jsonResponse({}, 204))

      await useSlmApi().upsertSecret('API_KEY', 'v', 'api_key', 'desc')

      expect(mockRaw).toHaveBeenCalledTimes(2)
      const post = mockRaw.mock.calls[0] as RawCall
      const put = mockRaw.mock.calls[1] as RawCall
      expect(post[0]).toBe('/secrets')
      expect(post[1].method).toBe('POST')
      expect(put[0]).toBe('/secrets/API_KEY')
      expect(put[1].method).toBe('PUT')
      expect(put[1].body).toEqual({ value: 'v', description: 'desc' })
    })

    it('re-throws non-409 errors from the initial POST (no PUT fallback)', async () => {
      mockRaw.mockResolvedValueOnce(errorResponse(500, { detail: 'boom' }))

      await expect(useSlmApi().upsertSecret('API_KEY', 'v')).rejects.toMatchObject({
        response: { status: 500 },
      })
      expect(mockRaw).toHaveBeenCalledTimes(1)
    })
  })

  describe('getSecretValue null-on-error contract', () => {
    it('returns the value on success', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ key: 'K', value: 'secret' }))
      await expect(useSlmApi().getSecretValue('K')).resolves.toBe('secret')
    })

    it('returns null when the request fails', async () => {
      mockRaw.mockResolvedValue(errorResponse(404, { detail: 'missing' }))
      await expect(useSlmApi().getSecretValue('K')).resolves.toBeNull()
    })
  })
})
