// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#13939: Company OS absorbed the automation module. Every /automation/*
// route moved onto /llc/companies/:companyId/automation/*; the legacy paths
// keep resolving so bookmarks, the main-nav item and the #2367 redirect are
// preserved. These tests are the "no automation functionality is lost" proof.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { createRouter, createMemoryHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get: vi.fn().mockResolvedValue([]) }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ error: vi.fn(), info: vi.fn(), warn: vi.fn(), debug: vi.fn() }),
}))

import { routes } from '@/router'

function makeRouter() {
  return createRouter({ history: createMemoryHistory(), routes })
}

/** Depth-first lookup of a route record by name. */
function findRecord(name: string, list: RouteRecordRaw[] = routes): RouteRecordRaw | undefined {
  for (const record of list) {
    if (record.name === name) return record
    const found = record.children ? findRecord(name, record.children) : undefined
    if (found) return found
  }
  return undefined
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('automation routes under Company OS (#13939)', () => {
  it('keeps every automation route name resolvable', () => {
    for (const name of ['automation', 'browser-automation', 'vision-automation', 'automation-section']) {
      expect(findRecord(name), name).toBeDefined()
    }
  })

  it('mounts the workflow builder under the company scope', () => {
    const record = findRecord('llc-company-automation')

    expect(record?.path).toBe('automation')
    expect(findRecord('browser-automation', record?.children ?? [])).toBeDefined()
    expect(findRecord('vision-automation', record?.children ?? [])).toBeDefined()
    expect(findRecord('automation-section', record?.children ?? [])).toBeDefined()
  })

  it.each([
    ['canvas', 'automation-section'],
    ['overview', 'automation-section'],
    ['templates', 'automation-section'],
    ['natural-language', 'automation-section'],
    ['runner', 'automation-section'],
    ['history', 'automation-section'],
    ['notifications', 'automation-section'],
    ['gui-automation', 'automation-section'],
    ['screen-analysis', 'automation-section'],
    ['video-processing', 'automation-section'],
    ['media-gallery', 'automation-section'],
    ['orchestration', 'automation-section'],
    ['agents', 'automation-section'],
    ['live-dashboard', 'automation-section'],
    ['browser-automation', 'browser-automation'],
    ['vision-automation', 'vision-automation'],
  ])('resolves the %s section inside the company scope', (section, expectedName) => {
    const resolved = makeRouter().resolve(`/llc/companies/c1/automation/${section}`)

    expect(resolved.name).toBe(expectedName)
    expect(resolved.params.companyId).toBe('c1')
    expect(resolved.matched.some((m) => m.name === 'llc-company-automation')).toBe(true)
  })

  it('marks only the generic section route as a section route', () => {
    const router = makeRouter()

    expect(router.resolve('/llc/companies/c1/automation/canvas').meta.sectionRoute).toBe(true)
    expect(
      router.resolve('/llc/companies/c1/automation/browser-automation').meta.sectionRoute,
    ).toBeUndefined()
  })

  it('sends the bare company automation path to the overview section', () => {
    const record = findRecord('llc-company-automation')
    const index = record?.children?.find((child) => child.path === '')
    const redirect = index?.redirect as (to: { params: Record<string, string> }) => string

    expect(redirect({ params: { companyId: 'c1' } })).toBe('/llc/companies/c1/automation/overview')
  })
})

describe('legacy /automation entry points still resolve (#13939)', () => {
  it('keeps /automation as a real top-level nav target', () => {
    const resolved = makeRouter().resolve('/automation')

    expect(resolved.name).toBe('automation')
    expect(resolved.meta.requiresAuth).toBe(true)
  })

  it('forwards a legacy deep link through the company resolver', () => {
    const resolved = makeRouter().resolve('/automation/canvas')

    expect(resolved.name).toBe('automation-legacy')
    expect(resolved.params.pathMatch).toEqual(['canvas'])
  })

  it('keeps the #2367 /browser-automation redirect intact', () => {
    const record = routes.find((r) => r.path === '/browser-automation')

    expect(record?.redirect).toBe('/automation/browser-automation')
  })
})
