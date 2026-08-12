// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

// GH#13996 (H1): the first-run Automation entry point sends the user here with
// `?redirect=/automation/...`. The selector honoured only `/llc/...`, so the
// destination was silently dropped and the user landed on the company backlog
// instead of automation. These tests drive the selector itself — asserting the
// forwarder's query alone is what let the defect ship green.

import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'

const push = vi.fn()
const get = vi.fn()
let currentQuery: Record<string, unknown> = {}

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
  useRoute: () => ({ query: currentQuery }),
  RouterLink: { name: 'RouterLink', template: '<a><slot /></a>' },
}))

vi.mock('@/plugins/api', () => ({
  useApiClient: () => ({ get }),
}))

vi.mock('@/utils/debugUtils', () => ({
  createLogger: () => ({ warn: vi.fn(), error: vi.fn(), info: vi.fn(), debug: vi.fn() }),
}))

import CompanySelectorView from '../CompanySelectorView.vue'
import { useRuntimeFeaturesStore } from '@/stores/useRuntimeFeaturesStore'

const COMPANIES = [{ id: 'c1', name: 'Acme', description: '', llc_status: 'active' }]

const i18n = createI18n({ legacy: false, locale: 'en', fallbackLocale: 'en', messages: { en } })

/** Mount the selector with a `?redirect=` value and pick the first company. */
async function selectFirstCompany(redirect?: unknown) {
  currentQuery = redirect === undefined ? {} : { redirect }
  const wrapper = mount(CompanySelectorView, {
    global: {
      plugins: [i18n],
      stubs: { CompanyStatusControl: true, RouterLink: true },
    },
  })
  await flushPromises()
  await wrapper.get('.company-card').trigger('click')
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  setActivePinia(createPinia())
  // Company mode on, already loaded, so `load()` short-circuits.
  const features = useRuntimeFeaturesStore()
  features.features = { company_os_enabled: true }
  features.isLoaded = true
  push.mockReset()
  get.mockReset().mockResolvedValue(COMPANIES)
})

describe('CompanySelectorView honours the redirect it was given (#13996)', () => {
  it('returns to the automation destination the first-run entry carried', async () => {
    await selectFirstCompany('/automation/canvas')

    expect(push).toHaveBeenCalledWith('/automation/canvas')
  })

  it('returns to a bare /automation entry', async () => {
    await selectFirstCompany('/automation')

    expect(push).toHaveBeenCalledWith('/automation')
  })

  it('keeps a query string on the destination', async () => {
    await selectFirstCompany('/automation?workflow=wf-1')

    expect(push).toHaveBeenCalledWith('/automation?workflow=wf-1')
  })

  it('still honours the /llc destination the company guard sets', async () => {
    await selectFirstCompany('/llc/companies/c1/backlog')

    expect(push).toHaveBeenCalledWith('/llc/companies/c1/backlog')
  })

  it('enters the company workspace when no redirect was carried', async () => {
    await selectFirstCompany()

    expect(push).toHaveBeenCalledWith('/llc/companies/c1')
  })
})

describe('CompanySelectorView stays closed to open redirects (#13996)', () => {
  it.each([
    ['an absolute URL', 'https://evil.example/steal'],
    ['a protocol-relative URL', '//evil.example/steal'],
    ['a backslash-escaped host', '/\\evil.example/steal'],
    ['a javascript: URL', 'javascript:alert(1)'],
    ['a path outside the allowlist', '/settings'],
    ['a prefix look-alike', '/automation-evil.example'],
    ['a repeated query param', ['/automation', 'https://evil.example']],
  ])('ignores %s and enters the company workspace', async (_label, redirect) => {
    await selectFirstCompany(redirect)

    expect(push).toHaveBeenCalledWith('/llc/companies/c1')
  })
})
