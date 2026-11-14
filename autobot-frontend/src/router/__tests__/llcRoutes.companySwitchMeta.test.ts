// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// #21502: the company layout remounts the routed view on a company switch unless the matched route
// opts out with meta.keepOnCompanySwitch. The workflow builder keeps an unsaved draft in component
// state, so the automation record and every child must resolve with the flag; the org chart must not.

import { describe, it, expect, vi } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'

vi.mock('@/views/WorkflowBuilderView.vue', () => ({ default: { render: () => null } }))

import { llcCompanyChildren } from '@/router/llcRoutes'

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{ path: '/llc/companies/:companyId', component: { render: () => null }, children: llcCompanyChildren }],
})

function metaOf(path: string): Record<string, unknown> {
  return router.resolve(path).meta
}

describe('keepOnCompanySwitch on the company routes (#21502)', () => {
  it.each([
    '/llc/companies/c1/automation/overview',
    '/llc/companies/c1/automation/browser-automation',
    '/llc/companies/c1/automation/vision-automation',
  ])('opts %s out of the remount', (path) => {
    expect(metaOf(path).keepOnCompanySwitch).toBe(true)
  })

  it('the section child resolves through the parent flag', () => {
    const resolved = router.resolve('/llc/companies/c1/automation/overview')
    expect(resolved.name).toBe('automation-section')
    expect(resolved.meta.keepOnCompanySwitch).toBe(true)
  })

  it('keeps the CEO chat opted out and remounts the org chart', () => {
    expect(metaOf('/llc/companies/c1/ceo-chat').keepOnCompanySwitch).toBe(true)
    expect(metaOf('/llc/companies/c1/org-chart').keepOnCompanySwitch).toBeUndefined()
  })
})
