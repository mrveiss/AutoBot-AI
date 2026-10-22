// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/**
 * #19217 — web research settings are saved to the backend from every surface.
 * The Settings panel used to patch the browser-persisted store only, so a change there
 * never reached the backend. Now one component, mounted by both screens, writes through
 * store actions only.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const { get, post, put } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }))
vi.mock('@/utils/ApiClient', () => ({ default: { get, post, put } }))

import WebResearchSettings from '../WebResearchSettings.vue'
import { useWebResearchStore } from '@/stores/useWebResearchStore'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

async function mountSettings() {
  const wrapper = mount(WebResearchSettings, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

const sw = (wrapper: ReturnType<typeof mount>, id: string) => wrapper.get(`button[role="switch"]#${id}`)

beforeEach(() => {
  setActivePinia(createPinia())
  get.mockReset().mockImplementation(async (url: string) =>
    url.endsWith('/settings') ? { settings: { enabled: false } } : { enabled: false })
  post.mockReset().mockResolvedValue({})
  put.mockReset().mockResolvedValue({})
})

describe('web research settings reach the backend (#19217)', () => {
  it('the enable switch posts /web-research/enable and only then shows it on', async () => {
    const wrapper = await mountSettings()
    await sw(wrapper, 'wr-enabled').trigger('click')
    await flushPromises()
    expect(post).toHaveBeenCalledWith(expect.stringMatching(/\/web-research\/enable$/), {})
    expect(sw(wrapper, 'wr-enabled').attributes('aria-checked')).toBe('true')
  })

  it('a failed enable leaves the switch off and says why', async () => {
    post.mockRejectedValue(new Error('HTTP 500'))
    const wrapper = await mountSettings()
    await sw(wrapper, 'wr-enabled').trigger('click')
    await flushPromises()
    expect(sw(wrapper, 'wr-enabled').attributes('aria-checked')).toBe('false')
    expect(wrapper.get('[role="alert"]').text()).toContain('Failed to enable web research: HTTP 500')
  })

  it('Save puts the whole settings set, including a switched privacy setting', async () => {
    const wrapper = await mountSettings()
    await sw(wrapper, 'wr-anonymize').trigger('click')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(put).toHaveBeenCalledTimes(1)
    const [url, body] = put.mock.calls[0]
    expect(url).toMatch(/\/web-research\/settings$/)
    expect(body).toEqual({ ...useWebResearchStore().settings, anonymize_requests: false })
    expect(wrapper.text()).toContain(en.settings.webResearch.saved)
  })

  it('a typed number is clamped to the range its hint states', async () => {
    const wrapper = await mountSettings()
    await wrapper.get('#wr-timeout').setValue('999')
    expect(useWebResearchStore().settings.timeout_seconds).toBe(120)
  })
})

describe('one component, one writer (#19217)', () => {
  const sources = import.meta.glob(['/src/**/*.vue', '/src/**/*.ts', '!/src/**/__tests__/**', '!/src/**/*.{spec,test}.ts'],
    { query: '?raw', import: 'default', eager: true }) as Record<string, string>

  it('no file but the store names a web research route', () => {
    const writers = Object.entries(sources).filter(([, src]) => src.includes('WEB_RESEARCH_API.')).map(([path]) => path)
    expect(writers).toEqual(['/src/stores/useWebResearchStore.ts'])
  })

  it('both screens mount the one settings component', () => {
    const mounts = Object.entries(sources)
      .filter(([path, src]) => path.endsWith('.vue') && /<WebResearchSettings[\s/>]/.test(src))
      .map(([path]) => path).sort()
    expect(mounts).toEqual(['/src/components/knowledge/KnowledgeResearchTabs.vue', '/src/views/SettingsView.vue'])
  })
})
