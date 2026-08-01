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
const deleteMock = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({
    get: (...args: unknown[]) => getMock(...args),
    delete: (...args: unknown[]) => deleteMock(...args),
  }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

describe('useLlcCompanyStore (GH#9627)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    getMock.mockReset()
    getMock.mockResolvedValue([mockCompany()])
    deleteMock.mockReset()
    deleteMock.mockResolvedValue(undefined)
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
    expect(store.unavailable).toBe(false)
    expect(store.isLoading).toBe(false)
    expect(store.companies).toEqual([])
  })

  it('fetchCompanies flags unavailable (not error) on HTTP 503', async () => {
    getMock.mockRejectedValue(
      new Error('HTTP 503: This feature requires PostgreSQL (single_company or multi_company mode).'),
    )
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    expect(store.unavailable).toBe(true)
    expect(store.error).toBeNull() // raw backend detail is never surfaced as an error
    expect(store.isLoading).toBe(false)
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

  // #12212: archived visibility + delete
  it('fetchCompanies(true) requests include_archived=true', async () => {
    const store = useLlcCompanyStore()
    await store.fetchCompanies(true)
    expect(getMock).toHaveBeenCalledWith('/api/llc/companies/?include_archived=true')
  })

  it('deleteCompany DELETEs with the row id as X-Organization-Id and drops it', async () => {
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    expect(store.companies).toHaveLength(1)
    await store.deleteCompany('company-1')
    expect(deleteMock).toHaveBeenCalledWith('/api/llc/companies/company-1', {
      headers: { 'X-Organization-Id': 'company-1' },
    })
    expect(store.companies).toHaveLength(0)
  })

  it('deleteCompany clears the selection when the deleted company was active', async () => {
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    store.selectCompany('company-1')
    await store.deleteCompany('company-1')
    expect(store.selectedCompanyId).toBe('')
  })

  it('deleteCompany re-throws and keeps the company on failure', async () => {
    deleteMock.mockRejectedValue(new Error('HTTP 409: has children'))
    const store = useLlcCompanyStore()
    await store.fetchCompanies()
    await expect(store.deleteCompany('company-1')).rejects.toThrow('409')
    expect(store.companies).toHaveLength(1)
  })
})
