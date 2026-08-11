// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// GH#13939: /automation/* moved under Company OS. This view is the bridge that
// keeps the main-nav item and every legacy bookmark working — it resolves the
// active company and forwards, preserving the requested section.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const replace = vi.fn()
const resolveCompanyId = vi.fn()
interface TestRoute {
  params: Record<string, unknown>
  fullPath: string
  query?: Record<string, unknown>
  hash?: string
}
let currentRoute: TestRoute = { params: {}, fullPath: '/automation', query: {}, hash: '' }

vi.mock('vue-router', () => ({
  useRouter: () => ({ replace }),
  useRoute: () => currentRoute,
}))

vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({ companyId: { value: '' }, resolveCompanyId }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import AutomationCompanyRedirectView from '../AutomationCompanyRedirectView.vue'
import { safeRedirectTarget } from '@/router/redirectTarget'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView(route: TestRoute) {
  currentRoute = { query: {}, hash: '', ...route }
  const wrapper = mount(AutomationCompanyRedirectView, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  replace.mockReset()
  resolveCompanyId.mockReset().mockResolvedValue('c1')
})

describe('AutomationCompanyRedirectView (#13939)', () => {
  it('forwards a bare /automation to the company overview section', async () => {
    await mountView({ params: {}, fullPath: '/automation' })

    expect(replace).toHaveBeenCalledWith({
      path: '/llc/companies/c1/automation/overview',
      query: {},
      hash: '',
    })
  })

  it('preserves the requested section of a deep link', async () => {
    await mountView({ params: { pathMatch: ['canvas'] }, fullPath: '/automation/canvas' })

    expect(replace).toHaveBeenCalledWith({
      path: '/llc/companies/c1/automation/canvas',
      query: {},
      hash: '',
    })
  })

  it('preserves a multi-segment path', async () => {
    await mountView({
      params: { pathMatch: ['browser-automation', 'sessions'] },
      fullPath: '/automation/browser-automation/sessions',
    })

    expect(replace).toHaveBeenCalledWith({
      path: '/llc/companies/c1/automation/browser-automation/sessions',
      query: {},
      hash: '',
    })
  })

  it('sends the user to the company selector when no company exists', async () => {
    resolveCompanyId.mockResolvedValue('')
    const wrapper = await mountView({ params: {}, fullPath: '/automation/canvas' })

    expect(replace).toHaveBeenCalledWith({
      name: 'llc-company-select',
      query: { redirect: '/automation/canvas' },
    })
    expect(wrapper.text()).toBe(en.workflow.views.companyRequired)
  })

  // #13996 (M4): `resolveEntityRoute` deep-links here as
  // `/automation?workflow=<id>`; a bare path dropped the anchor.
  it('carries the query and hash of the deep link across', async () => {
    await mountView({
      params: {},
      fullPath: '/automation?workflow=wf-1#step-3',
      query: { workflow: 'wf-1' },
      hash: '#step-3',
    })

    expect(replace).toHaveBeenCalledWith({
      path: '/llc/companies/c1/automation/overview',
      query: { workflow: 'wf-1' },
      hash: '#step-3',
    })
  })

  // #13996 (H1): the two ends of the first-run path, joined by the real
  // validator — the selector used to drop this destination on the floor.
  it('emits a selector redirect the selector actually honours', async () => {
    resolveCompanyId.mockResolvedValue('')
    await mountView({ params: { pathMatch: ['canvas'] }, fullPath: '/automation/canvas' })

    const { query } = replace.mock.calls[0][0] as { query: { redirect: string } }
    expect(safeRedirectTarget(query.redirect)).toBe('/automation/canvas')
  })

  it('shows a localised holding message while resolving', () => {
    currentRoute = { params: {}, fullPath: '/automation', query: {}, hash: '' }
    const wrapper = mount(AutomationCompanyRedirectView, { global: { plugins: [i18n] } })

    expect(wrapper.text()).toBe(en.workflow.views.resolvingCompany)
  })
})
