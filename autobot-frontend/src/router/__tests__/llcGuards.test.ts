// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#9627: tests for the company-scoped LLC route guard.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import type { RouteLocationNormalized } from 'vue-router'
import { llcCompanyParamGuard } from '../llcGuards'
import { useLlcCompanyStore } from '@/stores/useLlcCompanyStore'

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: vi.fn().mockResolvedValue([]) }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

function makeRoute(
  companyId: string | string[] | undefined,
  fullPath = '/llc/companies/x/backlog',
): RouteLocationNormalized {
  return {
    params: companyId === undefined ? {} : { companyId },
    fullPath,
    path: fullPath,
    query: {},
    hash: '',
    name: 'llc-backlog',
    matched: [],
    meta: {},
    redirectedFrom: undefined,
  } as unknown as RouteLocationNormalized
}

describe('llcCompanyParamGuard (GH#9627)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('redirects to the company selector when companyId is missing', () => {
    const result = llcCompanyParamGuard(makeRoute(undefined))
    expect(result).toEqual({
      name: 'llc-company-select',
      query: { redirect: '/llc/companies/x/backlog' },
    })
  })

  it('redirects when companyId is an empty string', () => {
    const result = llcCompanyParamGuard(makeRoute(''))
    expect(result).toMatchObject({ name: 'llc-company-select' })
  })

  it.each(['undefined', 'null'])(
    'redirects when companyId is the literal placeholder "%s"',
    (placeholder) => {
      const result = llcCompanyParamGuard(makeRoute(placeholder))
      expect(result).toMatchObject({ name: 'llc-company-select' })
    },
  )

  it('allows navigation and syncs the store for a valid companyId', () => {
    const result = llcCompanyParamGuard(makeRoute('company-42'))
    expect(result).toBe(true)
    expect(useLlcCompanyStore().selectedCompanyId).toBe('company-42')
  })

  it('uses the first element when companyId is a repeated param array', () => {
    const result = llcCompanyParamGuard(makeRoute(['company-a', 'company-b']))
    expect(result).toBe(true)
    expect(useLlcCompanyStore().selectedCompanyId).toBe('company-a')
  })

  it('carries the intended destination in the redirect query', () => {
    const result = llcCompanyParamGuard(makeRoute('', '/llc/companies//costs'))
    expect(result).toEqual({
      name: 'llc-company-select',
      query: { redirect: '/llc/companies//costs' },
    })
  })
})
