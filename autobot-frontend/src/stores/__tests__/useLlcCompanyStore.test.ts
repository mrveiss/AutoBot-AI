// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#9627: tests for the LLC company selector store.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useLlcCompanyStore, type LlcCompany } from '../useLlcCompanyStore'

const mockCompany = (overrides: Partial<LlcCompany> = {}): LlcCompany => ({
  id: 'company-1',
  name: 'Acme LLC',
  slug: 'acme',
  description: 'Test company',
  llc_status: 'active',
  ...overrides,
})

const getMock = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: (...args: unknown[]) => getMock(...args) }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

describe('useLlcCompanyStore (GH#9627)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getMock.mockReset()
    getMock.mockResolvedValue([mockCompany()])
  })

  it('starts with no companies and no selection', () => {
    const store = useLlcCompanyStore()
    expect(store.companies).toEqual([])
    expect(store.selectedCompanyId).toBe('')
    expect(store.selectedCompany).toBeNull()
    expect(store.hasCompanies).toBe(false)
  })

  it('fetchCompanies populates companies from GET /api/llc/companies/', async () => {
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    expect(getMock).toHaveBeenCalledWith('/api/llc/companies/')
    expect(store.companies).toHaveLength(1)
    expect(store.companies[0].name).toBe('Acme LLC')
    expect(store.error).toBeNull()
  })

  it('fetchCompanies tolerates a non-array response', async () => {
    getMock.mockResolvedValue({ unexpected: true })
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    expect(store.companies).toEqual([])
  })

  it('fetchCompanies records error and clears loading on failure', async () => {
    getMock.mockRejectedValue(new Error('boom'))
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    expect(store.error).toBe('boom')
    expect(store.isLoading).toBe(false)
    expect(store.companies).toEqual([])
  })

  it('selectCompany sets the active id and selectedCompany resolves it', async () => {
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    store.selectCompany('company-1')
    expect(store.selectedCompanyId).toBe('company-1')
    expect(store.selectedCompany?.name).toBe('Acme LLC')
  })

  it('selectedCompany is null for an id not in the list', () => {
    const store = useLlcCompanyStore()
    store.selectCompany('ghost')
    expect(store.selectedCompany).toBeNull()
  })

  it('fetchCompanies drops a persisted selection that no longer exists', async () => {
    const store = useLlcCompanyStore()
    store.selectCompany('deleted-company')
    await store.fetchCompanies()
    expect(store.selectedCompanyId).toBe('')
  })

  it('fetchCompanies keeps a selection that still exists', async () => {
    const store = useLlcCompanyStore()
    store.selectCompany('company-1')
    await store.fetchCompanies()
    expect(store.selectedCompanyId).toBe('company-1')
  })

  it('clearSelection resets the active id', () => {
    const store = useLlcCompanyStore()
    store.selectCompany('company-1')
    store.clearSelection()
    expect(store.selectedCompanyId).toBe('')
  })
})
