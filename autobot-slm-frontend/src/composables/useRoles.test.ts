// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12420 Phase 2 batch 7 — proves the useRoles composable is migrated onto the
 * canonical `slmApiClient`.
 *
 * useRoles historically owned its own `axios.create()` instance (base URL from
 * getSlmApiBase(), a request interceptor injecting the SLM bearer token). It now
 * routes every call through `slmApiClient.rawRequest` via a thin axios-compatible
 * adapter. These tests assert the migration preserves the behaviour the consumers
 * (FleetOverview, RoleManagementModal, ScheduleModal, DecommissionModal,
 * OrchestrationView, useCodeSync) depend on:
 *
 *   * every verb routes through slmApiClient.rawRequest with the correct
 *     method + endpoint (+ serialised query) and body — so the client's auth
 *     token / base URL / 401 handling apply (covered by ApiClient.test.ts);
 *   * endpoints are RELATIVE (no getSlmApiBase() prefix) — the client prepends it;
 *   * success returns the parsed JSON body (the historical `response.data`);
 *   * a non-2xx surfaces `err.response.data.detail` into the reactive `error`
 *     (or the graceful null / {success:false} return each method contracts);
 *   * a network/timeout rejection falls back to `err.message`;
 *   * array query params serialise as axios did (`node_ids[]=...`).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { jsonResponse, errorResponse } from './useSlmApi.testHelper'

const mockRaw = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  slmApiClient: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
  default: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
}))

import { useRoles } from './useRoles'

type RawCall = [string, { method: string; body?: unknown }]

describe('useRoles — migrated onto slmApiClient (#12420 Phase 2 batch 7)', () => {
  beforeEach(() => {
    mockRaw.mockReset()
  })

  describe('routing + response.data unwrap (relative endpoints)', () => {
    it('fetchRoles GETs /roles and stores the parsed body', async () => {
      const body = [{ name: 'backend', required: true }]
      mockRaw.mockResolvedValue(jsonResponse(body))

      const r = useRoles()
      await r.fetchRoles()

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/roles')
      expect(opts.method).toBe('GET')
      expect(r.roles).toEqual(body)
      expect(r.error).toBeNull()
      expect(r.isLoading).toBe(false)
    })

    it('getNodeRoles GETs /nodes/:id/detected-roles', async () => {
      const body = { node_id: 'n1', detected_roles: [], role_versions: {}, listening_ports: [], roles: [] }
      mockRaw.mockResolvedValue(jsonResponse(body))

      const result = await useRoles().getNodeRoles('n1')

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes/n1/detected-roles')
      expect(opts.method).toBe('GET')
      expect(result).toEqual(body)
    })

    it('assignRole POSTs the role body to /nodes/:id/detected-roles', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ role_name: 'backend' }))

      await useRoles().assignRole('n1', 'backend', 'auto')

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes/n1/detected-roles')
      expect(opts.method).toBe('POST')
      expect(opts.body).toEqual({ role_name: 'backend', assignment_type: 'auto' })
    })

    it('createRole POSTs to /roles and updateRole PUTs to /roles/:name', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ name: 'x' }))
      await useRoles().createRole({ name: 'x' } as never)
      let [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/roles')
      expect(opts.method).toBe('POST')

      mockRaw.mockReset()
      mockRaw.mockResolvedValue(jsonResponse({ name: 'x' }))
      await useRoles().updateRole('x', { display_name: 'X' } as never)
      ;[url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/roles/x')
      expect(opts.method).toBe('PUT')
      expect(opts.body).toEqual({ display_name: 'X' })
    })

    it('deleteRole DELETEs /roles/:name and returns true (204 handled)', async () => {
      mockRaw.mockResolvedValue(jsonResponse({}, 204))

      await expect(useRoles().deleteRole('x')).resolves.toBe(true)

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/roles/x')
      expect(opts.method).toBe('DELETE')
    })

    it('pullFromSource POSTs /code-sync/pull with no body', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ success: true, message: 'ok', commit: 'abc' }))

      const res = await useRoles().pullFromSource()

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/code-sync/pull')
      expect(opts.method).toBe('POST')
      expect(opts.body).toBeUndefined()
      expect(res).toEqual({ success: true, message: 'ok', commit: 'abc' })
    })

    it('decommissionNode POSTs the confirmation body to /nodes/:id/decommission', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ success: true, message: 'done' }))

      await useRoles().decommissionNode('n1', true, 'n1')

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes/n1/decommission')
      expect(opts.method).toBe('POST')
      expect(opts.body).toEqual({ backup: true, confirm_node_id: 'n1' })
    })
  })

  describe('query-param serialisation (axios-compatible)', () => {
    it('removeRole serialises the scalar `backup` param onto the DELETE endpoint', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ success: true, message: 'removed' }))

      await useRoles().removeRole('n1', 'backend', true)

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/nodes/n1/detected-roles/backend?backup=true')
      expect(opts.method).toBe('DELETE')
    })

    it('syncRole serialises node_ids as repeated array params (node_ids[]) with null body', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ success: true, message: 'synced', nodes_synced: 2 }))

      await useRoles().syncRole('backend', ['n1', 'n2'], false)

      const [url, opts] = mockRaw.mock.calls[0] as RawCall
      expect(url).toContain('/code-sync/roles/backend/sync?')
      expect(url).toContain('restart=false')
      // axios serialises arrays as key[]=v (URLSearchParams encodes the brackets).
      expect(url).toContain('node_ids%5B%5D=n1')
      expect(url).toContain('node_ids%5B%5D=n2')
      expect(opts.method).toBe('POST')
      expect(opts.body).toBeUndefined()
    })

    it('syncRole omits node_ids when none are supplied', async () => {
      mockRaw.mockResolvedValue(jsonResponse({ success: true, message: 'synced' }))

      await useRoles().syncRole('backend')

      const [url] = mockRaw.mock.calls[0] as RawCall
      expect(url).toBe('/code-sync/roles/backend/sync?restart=true')
    })
  })

  describe('error-shape parity (err.response.data.detail → reactive error / graceful returns)', () => {
    it('fetchRoles surfaces err.response.data.detail into the reactive error', async () => {
      mockRaw.mockResolvedValue(errorResponse(500, { detail: 'roles table missing' }))

      const r = useRoles()
      await r.fetchRoles()

      expect(r.error).toBe('roles table missing')
      expect(r.isLoading).toBe(false)
    })

    it('getNodeRoles returns null and records the detail on failure', async () => {
      mockRaw.mockResolvedValue(errorResponse(404, { detail: 'no such node' }))

      const r = useRoles()
      const result = await r.getNodeRoles('nope')

      expect(result).toBeNull()
      expect(r.error).toBe('no such node')
    })

    it('removeRole returns {success:false, message:detail} on failure', async () => {
      mockRaw.mockResolvedValue(errorResponse(409, { detail: 'role in use' }))

      const r = useRoles()
      const result = await r.removeRole('n1', 'backend')

      expect(result).toEqual({ success: false, message: 'role in use' })
      expect(r.error).toBe('role in use')
    })

    it('syncRole returns a failed SyncResult carrying the detail', async () => {
      mockRaw.mockResolvedValue(errorResponse(500, { detail: 'sync exploded' }))

      const result = await useRoles().syncRole('backend', ['n1'])

      expect(result).toEqual({ success: false, message: 'sync exploded', nodes_synced: 0 })
    })

    it('falls back to err.message when a network error carries no response', async () => {
      mockRaw.mockRejectedValue(new Error('Request timeout after 30000ms'))

      const r = useRoles()
      await r.fetchRoles()

      expect(r.error).toBe('Request timeout after 30000ms')
    })

    it('uses the hard-coded fallback when neither detail nor message is present', async () => {
      // Non-JSON error body → adapter leaves response.data null → no detail;
      // the thrown Error still carries `message` = "HTTP 502", the secondary fallback.
      mockRaw.mockResolvedValue({
        ok: false,
        status: 502,
        headers: { get: () => null },
        json: async () => {
          throw new Error('not json')
        },
        text: async () => 'Bad Gateway',
      } as unknown as Response)

      const r = useRoles()
      await r.fetchRoles()

      expect(r.error).toBe('HTTP 502')
    })
  })
})
