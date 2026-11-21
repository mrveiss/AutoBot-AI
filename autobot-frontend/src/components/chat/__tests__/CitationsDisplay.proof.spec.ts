// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss

/** #21976 — the existing citation display shows a tool step as a source, linked to its step. */

import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createI18n } from 'vue-i18n'
import en from '@/i18n/locales/en.json'
import CitationsDisplay from '../CitationsDisplay.vue'

const i18n = createI18n({ legacy: false, locale: 'en', messages: { en }, missingWarn: false, fallbackWarn: false })

const webSearch = {
  type: 'web_search',
  reliability: 'medium',
  title: 'web_search: weather in Riga',
  url: 'https://weather.example/riga',
  step_id: 'step-1',
  metadata: { tool: 'web_search', args: { query: 'weather in Riga' }, origin: { urls: ['https://weather.example/riga'] } },
}
const command = {
  type: 'system_state',
  reliability: 'verified',
  title: 'execute_command: uname -r',
  step_id: 'step-2',
  metadata: { tool: 'execute_command', args: { command: 'uname -r' }, origin: { host: 'main', return_code: 0 } },
}
const legacyKb = { id: 'c1', type: 'knowledge_base', title: 'Runbook', source: 'kb/runbook.md', score: 0.9, content: 'text' }

const mountList = (citations: unknown[], unproven: string[] = []) =>
  mount(CitationsDisplay, {
    props: { citations: citations as never[], unproven, initiallyExpanded: true },
    global: { plugins: [i18n] },
  })

describe('CitationsDisplay with tool steps (#21976)', () => {
  it('renders a tool source with its tool, arguments, host and exit code', () => {
    const text = mountList([webSearch, command]).text()
    expect(text).toContain('web_search')
    expect(text).toContain('weather in Riga')
    expect(text).toContain('Host: main')
    expect(text).toContain('Exit code: 0')
  })

  it('links a safe result URL and not an unsafe one', () => {
    const link = mountList([webSearch]).find('a.citation-link')
    expect(link.attributes('href')).toBe('https://weather.example/riga')
    expect(mountList([{ ...webSearch, url: 'javascript:alert(1)' }]).find('a.citation-link').exists()).toBe(false)
  })

  it('emits the clicked citation with its step id', async () => {
    const wrapper = mountList([webSearch])
    await wrapper.get('.citation-item').trigger('click')
    expect((wrapper.emitted('citation-click')![0][0] as { step_id: string }).step_id).toBe('step-1')
  })

  it('still renders a knowledge-base source', () => {
    const wrapper = mountList([legacyKb])
    expect(wrapper.text()).toContain('Runbook')
    expect(wrapper.text()).toContain('runbook.md')
  })

  it('lists unproven values under their own label, and nothing when there are none', () => {
    expect(mountList([command], ['5.18.33.2']).get('.citation-unproven').text()).toContain('5.18.33.2')
    expect(mountList([command]).find('.citation-unproven').exists()).toBe(false)
  })
})
