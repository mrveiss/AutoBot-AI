// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// #14556: "no company resolved" and "an empty company" used to render the same empty chart.
// An unresolved company now says so and offers a retry; a resolved company with no people
// still shows the empty state. Each half fails if the other's rendering is put back.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import { ref } from 'vue'
import en from '@/i18n/locales/en.json'

const get = vi.fn()
const post = vi.fn()

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get, post }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

const companyRef = ref<string | null>('c1')
const resolveCompanyId = vi.fn(() => Promise.resolve(companyRef.value))

vi.mock('@/composables/llc/useLlcCompanyContext', () => ({
  useLlcCompanyContext: () => ({ companyId: companyRef, resolveCompanyId }),
}))

import OrgChart from '../OrgChart.vue'

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

async function mountChart() {
  const wrapper = mount(OrgChart, {
    global: { plugins: [i18n], stubs: { HireAgentModal: true, Teleport: true } },
  })
  await flushPromises()
  return wrapper
}

const UNRESOLVED = '[data-testid="org-chart-company-unresolved"]'

beforeEach(() => {
  get.mockReset()
  post.mockReset()
  resolveCompanyId.mockClear()
  get.mockResolvedValue({ nodes: [] })
  post.mockResolvedValue({})
})

describe('OrgChart: an unresolved company is not an empty company (#14556)', () => {
  it('an unresolved company says so instead of rendering the empty chart', async () => {
    companyRef.value = null
    const wrapper = await mountChart()
    const state = wrapper.find(UNRESOLVED)
    expect(state.exists()).toBe(true)
    expect(state.text()).toContain(en.llc.orgChart.companyUnresolved)
    expect(wrapper.text()).not.toContain(en.llc.orgChart.empty)
    expect(get).not.toHaveBeenCalledWith(expect.stringContaining('/org-chart'))
  })

  it('a resolved company with no people still shows the empty state', async () => {
    companyRef.value = 'c1'
    const wrapper = await mountChart()
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/org-chart')
    expect(wrapper.find(UNRESOLVED).exists()).toBe(false)
    expect(wrapper.text()).toContain(en.llc.orgChart.empty)
  })

  it('retry re-resolves the company and loads the chart once it resolves', async () => {
    companyRef.value = null
    const wrapper = await mountChart()
    companyRef.value = 'c1'
    await wrapper.find(`${UNRESOLVED} button`).trigger('click')
    await flushPromises()
    expect(get).toHaveBeenCalledWith('/api/llc/companies/c1/org-chart')
    expect(wrapper.find(UNRESOLVED).exists()).toBe(false)
    expect(wrapper.text()).toContain(en.llc.orgChart.empty)
  })
})
