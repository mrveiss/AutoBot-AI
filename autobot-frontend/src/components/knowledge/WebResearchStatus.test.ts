// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * #19217: web research has ONE editor, in the SLM admin console. The main app shows a
 * read-only status with a link to it. These tests pin that the status renders the backend
 * values, links to the SLM page, says so honestly when the researcher is unavailable,
 * and that no main-app source file can write web research settings again.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { HttpError } from '@autobot/ui'
import { mount, flushPromises } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createI18n } from 'vue-i18n'
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, relative, sep } from 'node:path'
import en from '@/i18n/locales/en.json'

const { apiGet } = vi.hoisted(() => ({ apiGet: vi.fn() }))

vi.mock('@/utils/ApiClient', () => ({ default: { get: apiGet } }))
vi.mock('@/config/ssot-config', () => ({
  getApiBase: () => '/api',
  getSLMAdminUrl: () => 'https://slm.example',
}))

import WebResearchStatus from './WebResearchStatus.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en } })
const copy = en.knowledge.webResearch.status

const SETTINGS = { settings: { enabled: true, preferred_method: 'advanced' } }
const STATUS = {
  enabled: true,
  preferred_method: 'advanced',
  cache_stats: { cache_size: 12 },
  circuit_breakers: {},
}

function routeGets(statusResult: unknown) {
  apiGet.mockImplementation(async (url: string) => {
    if (url.endsWith('/web-research/settings')) return SETTINGS
    if (url.endsWith('/web-research/status')) {
      if (statusResult instanceof Error) throw statusResult
      return statusResult
    }
    throw new Error(`unexpected ${url}`)
  })
}

async function mountStatus() {
  const wrapper = mount(WebResearchStatus, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper
}

describe('WebResearchStatus', () => {
  beforeEach(() => {
    localStorage.clear()
    setActivePinia(createPinia())
    apiGet.mockReset()
  })

  it('renders the backend values read-only', async () => {
    routeGets(STATUS)
    const wrapper = await mountStatus()
    expect(wrapper.get('[data-testid="status-enabled"]').text()).toBe(copy.yes)
    expect(wrapper.get('[data-testid="status-method"]').text()).toBe(en.settings.webResearch.methodAdvanced)
    expect(wrapper.get('[data-testid="status-cache"]').text()).toBe('12')
    expect(wrapper.get('[data-testid="status-availability"]').text()).toBe(copy.available)
    expect(wrapper.find('input, select, button, textarea').exists()).toBe(false)
  })

  it('links to the SLM web research page in a new tab, safely', async () => {
    routeGets(STATUS)
    const link = (await mountStatus()).get('[data-testid="web-research-slm-link"]')
    expect(link.attributes('href')).toBe('https://slm.example/settings/admin/web-research')
    expect(link.attributes('target')).toBe('_blank')
    expect(link.attributes('rel')).toContain('noopener')
    expect(link.text()).toBe(copy.configureLink)
  })

  it('shows the not-available state when the researcher answers 503', async () => {
    routeGets(new HttpError(503, 'researcher unavailable'))
    const wrapper = await mountStatus()
    expect(wrapper.get('[data-testid="status-availability"]').text()).toBe(copy.notAvailable)
  })
})

// A write route in the main app would re-open the second editor the decision on #19217 retired.
// vitest runs from the app root (autobot-frontend), so `src` is the tree under test.
const SRC = join(process.cwd(), 'src')
const WRITE_ROUTE = /web-research\/(enable|disable|clear-cache|reset-circuit-breakers)/
const SETTINGS_PUT = /\bput\b[^\n]*(web-research\/settings|WEB_RESEARCH_API\.settings)/i

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name)
    if (statSync(path).isDirectory()) return name === 'node_modules' ? [] : sources(path)
    return /\.(vue|ts|js)$/.test(name) ? [path] : []
  })
}

describe('no main-app web research write route (#19217)', () => {
  it('the scan finds source files to look in', () => {
    expect(sources(SRC).length).toBeGreaterThan(100)
  })

  it('no source file names a web research write route', () => {
    const generated = ['types', 'generated'].join(sep)
    const offenders = sources(SRC)
      .filter((f) => !relative(SRC, f).startsWith(generated) && !f.endsWith('WebResearchStatus.test.ts'))
      .filter((f) => {
        const text = readFileSync(f, 'utf-8')
        return WRITE_ROUTE.test(text) || SETTINGS_PUT.test(text)
      })
      .map((f) => relative(SRC, f))
    expect(offenders).toEqual([])
  })
})
