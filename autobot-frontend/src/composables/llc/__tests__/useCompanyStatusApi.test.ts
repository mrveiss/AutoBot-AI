// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * AutoBot - AI-Powered Automation Platform
 * Author: mrveiss
 *
 * GH#12231: unit tests for the LLC company status-transition composable.
 * Asserts each transition POSTs the right endpoint, that the valid-transition
 * map mirrors the backend guards, and that a rejected (409) transition
 * propagates the error.
 *
 * GH#12368: each transition must send the TARGET row's id as the
 * ``X-Organization-Id`` header so the backend authorises the target company
 * regardless of the currently-selected tenant.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'

const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import {
  useCompanyStatusApi,
  transitionsFor,
  VALID_TRANSITIONS,
  DESTRUCTIVE_ACTIONS,
} from '../useCompanyStatusApi'

/** #12368: the per-request options that scope the call to the target row. */
const orgHeader = (id: string) => ({ headers: { 'X-Organization-Id': id } })

describe('useCompanyStatusApi', () => {
  beforeEach(() => {
    post.mockReset()
  })

  it('activate() POSTs /activate and returns the parsed company', async () => {
    const company = { id: 'c1', name: 'Acme', llc_status: 'active' }
    post.mockResolvedValueOnce(company)
    const result = await useCompanyStatusApi().activate('c1')
    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/activate', undefined, orgHeader('c1'))
    expect(result).toEqual(company)
  })

  it('suspend() POSTs /suspend, omitting the body when no reason given', async () => {
    post.mockResolvedValueOnce({ id: 'c1', name: 'Acme', llc_status: 'paused' })
    await useCompanyStatusApi().suspend('c1')
    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/suspend', undefined, orgHeader('c1'))
  })

  it('suspend() forwards the reason as the request body', async () => {
    post.mockResolvedValueOnce({ id: 'c1', name: 'Acme', llc_status: 'paused' })
    await useCompanyStatusApi().suspend('c1', 'budget freeze')
    expect(post).toHaveBeenCalledWith(
      '/api/llc/companies/c1/suspend',
      { reason: 'budget freeze' },
      orgHeader('c1'),
    )
  })

  it('offboard() POSTs /offboard', async () => {
    post.mockResolvedValueOnce({ id: 'c1', name: 'Acme', llc_status: 'offboarding' })
    await useCompanyStatusApi().offboard('c1')
    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/offboard', undefined, orgHeader('c1'))
  })

  it('archive() POSTs /archive', async () => {
    post.mockResolvedValueOnce({ id: 'c1', name: 'Acme', llc_status: 'archived' })
    await useCompanyStatusApi().archive('c1')
    expect(post).toHaveBeenCalledWith('/api/llc/companies/c1/archive', undefined, orgHeader('c1'))
  })

  it('sends the TARGET row id as X-Organization-Id, not the selected tenant (#12368)', async () => {
    post.mockResolvedValueOnce({ id: 'other-co', name: 'Other', llc_status: 'archived' })
    await useCompanyStatusApi().archive('other-co')
    expect(post).toHaveBeenCalledWith(
      '/api/llc/companies/other-co/archive',
      undefined,
      { headers: { 'X-Organization-Id': 'other-co' } },
    )
  })

  it('propagates a rejected (e.g. HTTP 409) transition', async () => {
    post.mockRejectedValueOnce(new Error('HTTP 409'))
    await expect(useCompanyStatusApi().archive('c1')).rejects.toThrow('HTTP 409')
  })

  it('valid-transition map mirrors the backend guards', () => {
    expect(VALID_TRANSITIONS).toEqual({
      onboarding: ['activate', 'suspend'],
      active: ['suspend', 'offboard'],
      paused: ['activate', 'archive'],
      offboarding: ['archive'],
      archived: [],
    })
    expect(DESTRUCTIVE_ACTIONS.has('archive')).toBe(true)
    expect(DESTRUCTIVE_ACTIONS.has('offboard')).toBe(true)
    expect(DESTRUCTIVE_ACTIONS.has('activate')).toBe(false)
  })

  it('transitionsFor() returns valid actions and [] for unknown/terminal states', () => {
    expect(transitionsFor('active')).toEqual(['suspend', 'offboard'])
    expect(transitionsFor('archived')).toEqual([])
    expect(transitionsFor(undefined)).toEqual([])
    expect(transitionsFor('bogus')).toEqual([])
  })
})
