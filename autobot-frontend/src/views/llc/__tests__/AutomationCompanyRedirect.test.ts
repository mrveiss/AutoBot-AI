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
let currentRoute = { params: {} as Record<string, unknown>, fullPath: '/automation' }

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

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountView(route: { params: Record<string, unknown>; fullPath: string }) {
  currentRoute = route
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

    expect(replace).toHaveBeenCalledWith('/llc/companies/c1/automation/overview')
  })

  it('preserves the requested section of a deep link', async () => {
    await mountView({ params: { pathMatch: ['canvas'] }, fullPath: '/automation/canvas' })

    expect(replace).toHaveBeenCalledWith('/llc/companies/c1/automation/canvas')
  })

  it('preserves a multi-segment path', async () => {
    await mountView({
      params: { pathMatch: ['browser-automation', 'sessions'] },
      fullPath: '/automation/browser-automation/sessions',
    })

    expect(replace).toHaveBeenCalledWith(
      '/llc/companies/c1/automation/browser-automation/sessions',
    )
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

  it('shows a localised holding message while resolving', () => {
    currentRoute = { params: {}, fullPath: '/automation' }
    const wrapper = mount(AutomationCompanyRedirectView, { global: { plugins: [i18n] } })

    expect(wrapper.text()).toBe(en.workflow.views.resolvingCompany)
  })
})
