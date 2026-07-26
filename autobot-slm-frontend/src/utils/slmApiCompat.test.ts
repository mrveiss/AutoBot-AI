// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #12654 — focused tests for the shared axios-compat adapter extracted from the
 * duplicated per-composable copies. Asserts the two behaviour flags that were the
 * ONLY differences between the useSlmApi and useRoles copies (`textFallback` and
 * `arrays`) plus the invariant `{ data }` envelope and axios-shaped error.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { makeResponse } from '@/composables/slmApiClient.testHelper'

const mockRaw = vi.fn()

vi.mock('@/utils/ApiClient', () => ({
  slmApiClient: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
  default: { rawRequest: (...args: unknown[]) => mockRaw(...args) },
}))

import { makeAxiosCompatClient, withParams } from './slmApiCompat'

describe('withParams', () => {
  it('serialises scalars as key=value and leaves the endpoint alone with no params', () => {
    expect(withParams('/x')).toBe('/x')
    expect(withParams('/x', { a: 1, b: 'two' })).toBe('/x?a=1&b=two')
  })

  it('appends with & when the endpoint already has a query string', () => {
    expect(withParams('/x?z=0', { a: 1 })).toBe('/x?z=0&a=1')
  })

  it('skips null/undefined values', () => {
    expect(withParams('/x', { a: undefined, b: null, c: 3 })).toBe('/x?c=3')
  })

  it('with arrays:false stringifies an array via String() (scalar path)', () => {
    expect(withParams('/x', { ids: ['a', 'b'] })).toBe('/x?ids=a%2Cb')
  })

  it('with arrays:true serialises arrays as repeated key[]=value', () => {
    expect(withParams('/x', { ids: ['a', 'b'] }, { arrays: true })).toBe(
      '/x?ids%5B%5D=a&ids%5B%5D=b'
    )
  })
})

describe('makeAxiosCompatClient — envelope + routing', () => {
  beforeEach(() => mockRaw.mockReset())

  it('unwraps a 2xx JSON body into { data } and routes verb + endpoint + body', async () => {
    mockRaw.mockResolvedValue(makeResponse(200, { ok: true }))
    const client = makeAxiosCompatClient()

    const res = await client.post('/nodes', { a: 1 })

    expect(mockRaw).toHaveBeenCalledWith('/nodes', { method: 'POST', body: { a: 1 } })
    expect(res.data).toEqual({ ok: true })
  })

  it('returns { data: {} } for a 204 No Content', async () => {
    mockRaw.mockResolvedValue(makeResponse(204, null))
    const res = await makeAxiosCompatClient().delete('/nodes/1')
    expect(res.data).toEqual({})
  })

  it('throws an axios-shaped error carrying response.status + response.data on non-2xx', async () => {
    mockRaw.mockResolvedValue(makeResponse(409, { detail: 'conflict' }))
    await expect(makeAxiosCompatClient().post('/secrets')).rejects.toMatchObject({
      message: 'HTTP 409',
      response: { status: 409, data: { detail: 'conflict' } },
    })
  })

  it('serialises get params through withParams (arrays flag honoured)', async () => {
    mockRaw.mockResolvedValue(makeResponse(200, {}))
    const client = makeAxiosCompatClient({ arrays: true })
    await client.get('/roles', { params: { node_ids: ['n1', 'n2'] } })
    expect(mockRaw).toHaveBeenCalledWith('/roles?node_ids%5B%5D=n1&node_ids%5B%5D=n2', {
      method: 'GET',
      body: undefined,
    })
  })
})

describe('makeAxiosCompatClient — textFallback for non-JSON 2xx', () => {
  beforeEach(() => mockRaw.mockReset())

  it('with textFallback:true returns response.text() for a non-JSON 2xx (PEM download)', async () => {
    mockRaw.mockResolvedValue(makeResponse(200, '-----BEGIN CERT-----', 'application/x-pem-file'))
    const res = await makeAxiosCompatClient({ textFallback: true }).get('/tls/credentials/1/ca-cert')
    expect(res.data).toBe('-----BEGIN CERT-----')
  })

  it('without textFallback returns {} for a non-JSON 2xx', async () => {
    mockRaw.mockResolvedValue(makeResponse(200, 'ignored', 'text/plain'))
    const res = await makeAxiosCompatClient().get('/roles')
    expect(res.data).toEqual({})
  })
})
